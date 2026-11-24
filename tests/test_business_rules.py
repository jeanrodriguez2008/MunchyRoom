"""Pruebas de las reglas críticas de negocio de MunchyRoom."""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from sqlalchemy import func, select

from app.constants import ReservationStatus, Role
from app.models import MeetingRoom, Position, Reservation, User
from app.security import normalize_phone
from app.seed import seed_database
from app.services.availability import check_slot
from app.services.reservations import (
    BusinessRuleError,
    authorize_reservation,
    cancel_reservation,
    create_reservation,
    reject_by_admin,
    reject_by_authorizer,
    send_to_authorizer,
)
from app.services.whatsapp import build_message, build_wa_link
from app.timeutils import now_caracas


def future_slot(days: int = 3, hour: int = 10) -> tuple[date, time]:
    target = now_caracas() + timedelta(days=days)
    return target.date(), time(hour=hour, minute=0)



def _create(db, people, room, *, days=3, hour=10, duration=60, participants=None, requester=None, expected=None):
    meeting_date, start_time = future_slot(days, hour)
    participant_ids = participants or [people["participant"].id]
    return create_reservation(
        db,
        requester=requester or people["requester"],
        room=room,
        meeting_date=meeting_date,
        start_time=start_time,
        duration_minutes=duration,
        purpose="Revisión de indicadores de producción",
        expected_participants_count=expected or len(participant_ids),
        participant_ids=[p.id if hasattr(p, "id") else p for p in participant_ids],
    )


# ---------------------------------------------------------------------------
# Seed y roles
# ---------------------------------------------------------------------------
def test_seed_creates_rooms_positions_and_admin(db):
    summary = seed_database(db)
    assert summary == {"rooms": 3, "positions": 6, "admin": 1}
    assert db.scalar(select(func.count()).select_from(MeetingRoom)) == 3
    assert db.scalar(select(func.count()).select_from(Position)) == 6

    admin = db.scalar(select(User).where(User.email == "admin@munchy.com"))
    assert admin is not None
    assert admin.has_role(Role.ADMIN)
    assert admin.must_change_password is True

    # Idempotente
    second = seed_database(db)
    assert second == {"rooms": 0, "positions": 0, "admin": 0}


def test_user_can_have_multiple_roles(people):
    requester = people["requester"]
    assert requester.has_role(Role.REQUESTER)
    assert requester.has_role(Role.PARTICIPANT)
    assert set(requester.role_names) == {Role.REQUESTER, Role.PARTICIPANT}


def test_phone_normalization():
    assert normalize_phone("+58 412-123 4567") == "+584121234567"
    assert normalize_phone("584121234567") == "+584121234567"
    assert normalize_phone("04121234567") == "+04121234567"
    assert normalize_phone("abc") == ""
    assert normalize_phone("") == ""


# ---------------------------------------------------------------------------
# Creación y solapamientos
# ---------------------------------------------------------------------------
def test_create_reservation_starts_pending_admin(db, people, room):
    reservation, warnings = _create(db, people, room)
    db.commit()
    assert reservation.status == ReservationStatus.PENDING_ADMIN
    assert reservation.end_time == time(11, 0)
    assert len(reservation.participants) == 1
    assert warnings == []
    assert reservation.room_id == room.id


def test_capacity_is_enforced(db, people, room):
    with pytest.raises(BusinessRuleError, match="capacidad"):
        _create(db, people, room, expected=20)


def test_expected_cannot_be_less_than_selected(db, people, room):
    with pytest.raises(BusinessRuleError, match="no puede ser menor"):
        _create(
            db,
            people,
            room,
            participants=[people["participant"].id, people["participant2"].id],
            expected=1,
        )


def test_authorized_reservation_blocks_same_slot(db, people, room):
    first, _ = _create(db, people, room)
    first.status = ReservationStatus.AUTHORIZED
    db.commit()

    with pytest.raises(BusinessRuleError, match="Horario no disponible"):
        _create(db, people, room)

    # Una hora distinta sí está disponible.
    second, _ = _create(db, people, room, hour=12)
    db.commit()
    assert second.id != first.id


def test_pending_admin_overlap_only_warns(db, people, room):
    first, _ = _create(db, people, room)
    second, warnings = _create(db, people, room)
    db.commit()
    assert first.id != second.id
    assert warnings and "pendiente" in warnings[0].lower()


def test_send_to_authorizer_blocks_other_pending_request(db, people, room):
    first, _ = _create(db, people, room)
    second, _ = _create(db, people, room)
    db.commit()

    # Mientras exista otra solicitud pendiente en el mismo horario, el admin
    # debe resolver el cruce (rechazar/cancelar) antes de escalar.
    with pytest.raises(BusinessRuleError, match="otra solicitud"):
        send_to_authorizer(
            db, reservation=first, admin=people["admin"], authorizer=people["authorizer"], note="Validado"
        )

    reject_by_admin(second, admin=people["admin"], reason="Duplicada")
    db.commit()

    send_to_authorizer(
        db, reservation=first, admin=people["admin"], authorizer=people["authorizer"], note="Validado"
    )
    db.commit()
    assert first.status == ReservationStatus.PENDING_AUTHORIZER
    assert first.admin_validator_id == people["admin"].id
    assert first.authorizer_id == people["authorizer"].id

    # Con la sala ya en autorización final, no se puede crear otra reserva.
    with pytest.raises(BusinessRuleError):
        _create(db, people, room)


def test_authorizer_cannot_approve_foreign_request(db, people, room):
    reservation, _ = _create(db, people, room)
    db.commit()
    send_to_authorizer(db, reservation=reservation, admin=people["admin"], authorizer=people["authorizer"])
    db.commit()

    with pytest.raises(BusinessRuleError, match="otro jefe"):
        authorize_reservation(db, reservation=reservation, authorizer=people["authorizer2"])


def test_full_approval_flow(db, people, room):
    reservation, _ = _create(db, people, room)
    db.commit()
    send_to_authorizer(
        db, reservation=reservation, admin=people["admin"], authorizer=people["authorizer"], note="OK"
    )
    db.commit()
    authorize_reservation(
        db, reservation=reservation, authorizer=people["authorizer"], comment="Aprobada"
    )
    db.commit()

    assert reservation.status == ReservationStatus.AUTHORIZED
    assert reservation.authorizer_comment == "Aprobada"
    assert reservation.admin_note == "OK"

    # El horario queda bloqueado definitivamente.
    with pytest.raises(BusinessRuleError):
        _create(db, people, room)


def test_authorizer_rejection_records_reason(db, people, room):
    reservation, _ = _create(db, people, room)
    db.commit()
    send_to_authorizer(db, reservation=reservation, admin=people["admin"], authorizer=people["authorizer"])
    db.commit()
    reject_by_authorizer(
        reservation, authorizer=people["authorizer"], comment="Conflicto con auditoría"
    )
    db.commit()
    assert reservation.status == ReservationStatus.REJECTED
    assert reservation.rejection_reason == "Conflicto con auditoría"


# ---------------------------------------------------------------------------
# Regla de cancelación de 24 horas
# ---------------------------------------------------------------------------
def test_cancel_more_than_24_hours_before(db, people, room):
    reservation, _ = _create(db, people, room, days=3)
    db.commit()
    cancel_reservation(reservation, actor=people["requester"], reason="Cambio de agenda")
    db.commit()
    assert reservation.status == ReservationStatus.CANCELLED
    assert reservation.cancelled_by_id == people["requester"].id
    assert reservation.cancelled_at is not None


def test_cancel_with_less_than_24_hours_is_blocked(db, people, room):
    now = now_caracas()
    target = None
    for offset in (2, 3, 4, 5):
        candidate = now + timedelta(hours=offset)
        if candidate.hour < 23:
            target = candidate
            break
    assert target is not None

    reservation = Reservation(
        room_id=room.id,
        requester_id=people["requester"].id,
        meeting_date=target.date(),
        start_time=target.time().replace(second=0, microsecond=0),
        end_time=(target + timedelta(minutes=30)).time().replace(second=0, microsecond=0),
        duration_minutes=30,
        purpose="Reunión urgente",
        expected_participants_count=1,
        status=ReservationStatus.AUTHORIZED,
    )
    db.add(reservation)
    db.commit()

    with pytest.raises(BusinessRuleError, match="No es posible cancelar con menos de 24 horas"):
        cancel_reservation(reservation, actor=people["requester"])


def test_only_requester_or_admin_can_cancel(db, people, room):
    reservation, _ = _create(db, people, room, days=3)
    db.commit()
    with pytest.raises(BusinessRuleError, match="Solo el solicitante"):
        cancel_reservation(reservation, actor=people["participant"])
    assert reservation.status == ReservationStatus.PENDING_ADMIN


# ---------------------------------------------------------------------------
# Disponibilidad y WhatsApp
# ---------------------------------------------------------------------------
def test_check_slot_reports_hard_conflict(db, people, room):
    reservation, _ = _create(db, people, room)
    reservation.status = ReservationStatus.AUTHORIZED
    db.commit()

    payload = check_slot(
        db,
        room_id=room.id,
        meeting_date=reservation.meeting_date,
        start_time=time(10, 30),
        duration_minutes=30,
    )
    assert payload["hard_conflict"] is True
    assert payload["ok"] is False
    assert payload["conflicts"]


def test_whatsapp_message_and_link(db, people, room):
    reservation, _ = _create(db, people, room)
    db.commit()
    message = build_message(reservation, people["participant"], reservation.requester.full_name)

    assert "Guest Test" in message
    assert "Revisión de indicadores" in message
    assert "Sala Test" in message
    assert "Organiza" in message
    assert "📌" in message

    link = build_wa_link(people["participant"].phone_whatsapp, message)
    assert link.startswith("https://wa.me/584129998877?text=")
    assert " " not in link
