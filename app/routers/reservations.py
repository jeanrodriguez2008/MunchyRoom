"""Rutas de reservas: listado, creación, detalle, cancelación y convocatoria."""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import time as time_cls
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import ReservationStatus, Role
from app.database import get_db
from app.dependencies import current_user, require_roles
from app.models import MeetingRoom, Reservation, ReservationParticipant, User, UserRole
from app.services.reservations import (
    BusinessRuleError,
    cancel_reservation,
    create_reservation,
    mark_whatsapp_notified,
)
from app.services.whatsapp import build_generic_message, build_message, build_share_text, build_wa_link
from app.templating import flash, render
from app.timeutils import today_caracas

router = APIRouter(tags=["Reservas"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _active_participants(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_name == Role.PARTICIPANT, User.is_active.is_(True))
            .order_by(User.full_name)
            .distinct()
        ).all()
    )


def _new_form_context(db: Session, form_data: dict) -> dict:
    rooms = list(
        db.scalars(select(MeetingRoom).where(MeetingRoom.is_active.is_(True)).order_by(MeetingRoom.name)).all()
    )
    rooms_json = [{"id": room.id, "name": room.name, "capacity": room.capacity} for room in rooms]
    try:
        duration = int(form_data.get("duration_minutes") or 60)
    except (TypeError, ValueError):
        duration = 60
    try:
        expected = int(form_data.get("expected_participants_count") or 1)
    except (TypeError, ValueError):
        expected = 1
    return {
        "rooms": rooms,
        "participants": _active_participants(db),
        "form_data": form_data,
        "rooms_json": rooms_json,
        "form_config": {
            "roomId": str(form_data.get("room_id") or ""),
            "date": form_data.get("meeting_date") or "",
            "start": form_data.get("start_time") or "",
            "duration": duration,
            "expected": expected,
            "rooms": rooms_json,
            "selected": [str(pid) for pid in form_data.get("participant_ids", [])],
        },
    }


def _default_form() -> dict:
    return {
        "room_id": "",
        "meeting_date": (today_caracas() + timedelta(days=1)).isoformat(),
        "start_time": "09:00",
        "duration_minutes": "60",
        "purpose": "",
        "expected_participants_count": "2",
        "participant_ids": [],
    }


def _get_reservation(db: Session, reservation_id: int) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La reunión no existe.")
    return reservation


def _authorizers(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_name == Role.AUTHORIZER, User.is_active.is_(True))
            .order_by(User.full_name)
            .distinct()
        ).all()
    )


# ---------------------------------------------------------------------------
# Listado y creación
# ---------------------------------------------------------------------------
@router.get("/reservations", name="reservations_list")
def reservations_list(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    status: str = Query(""),
):
    stmt = select(Reservation).where(Reservation.requester_id == user.id)
    if status in ReservationStatus.ALL:
        stmt = stmt.where(Reservation.status == status)
    reservations = list(
        db.scalars(stmt.order_by(Reservation.meeting_date.desc(), Reservation.start_time.desc()).limit(200)).all()
    )
    invited = list(
        db.scalars(
            select(Reservation)
            .join(ReservationParticipant, ReservationParticipant.reservation_id == Reservation.id)
            .where(
                ReservationParticipant.user_id == user.id,
                Reservation.status.in_((ReservationStatus.AUTHORIZED, ReservationStatus.PENDING_AUTHORIZER)),
            )
            .order_by(Reservation.meeting_date, Reservation.start_time)
            .limit(50)
        ).all()
    )
    return render(
        request,
        "reservations/list.html",
        {
            "user": user,
            "reservations": reservations,
            "invited": invited,
            "selected_status": status,
        },
    )


@router.get("/reservations/new", name="reservation_new")
def reservation_new(
    request: Request,
    user: User = Depends(require_roles(Role.REQUESTER, Role.ADMIN)),
    db: Session = Depends(get_db),
    date: str | None = Query(None),
    room_id: int | None = Query(None),
    start: str | None = Query(None),
):
    if not db.scalar(select(MeetingRoom.id).where(MeetingRoom.is_active.is_(True))):
        flash(request, "No hay salas activas. Pide al administrador que configure al menos una.", "warning")
        return RedirectResponse("/reservations", status_code=303)

    form_data = _default_form()
    if room_id:
        room = db.get(MeetingRoom, room_id)
        if room is not None and room.is_active:
            form_data["room_id"] = str(room.id)
    if date:
        try:
            parsed = date_cls.fromisoformat(date)
            if parsed >= today_caracas():
                form_data["meeting_date"] = parsed.isoformat()
        except ValueError:
            pass
    if start:
        try:
            parsed_start = time_cls.fromisoformat(start)
            form_data["start_time"] = parsed_start.strftime("%H:%M")
        except ValueError:
            pass

    return render(request, "reservations/new.html", _new_form_context(db, form_data))


@router.post("/reservations", name="reservation_create")
def reservation_create(
    request: Request,
    user: User = Depends(require_roles(Role.REQUESTER, Role.ADMIN)),
    db: Session = Depends(get_db),
    room_id: str = Form(...),
    meeting_date: str = Form(...),
    start_time: str = Form(...),
    duration_minutes: str = Form("60"),
    purpose: str = Form(""),
    expected_participants_count: str = Form("1"),
    participant_ids: list[int] | None = Form(None),
):
    form_data = {
        "room_id": room_id,
        "meeting_date": meeting_date,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "purpose": purpose,
        "expected_participants_count": expected_participants_count,
        "participant_ids": [str(pid) for pid in (participant_ids or [])],
    }

    def fail(message: str, status_code: int = 400):
        flash(request, message, "error")
        return render(
            request,
            "reservations/new.html",
            _new_form_context(db, form_data),
            status_code=status_code,
        )

    try:
        parsed_room_id = int(room_id)
    except (TypeError, ValueError):
        return fail("Selecciona una sala válida.")
    room = db.get(MeetingRoom, parsed_room_id)
    if room is None:
        return fail("La sala seleccionada no existe.")

    try:
        parsed_date = date_cls.fromisoformat(meeting_date)
    except ValueError:
        return fail("Selecciona una fecha válida.")
    try:
        parsed_start = time_cls.fromisoformat(start_time)
    except ValueError:
        return fail("Selecciona una hora de inicio válida.")
    try:
        parsed_duration = int(duration_minutes)
    except (TypeError, ValueError):
        return fail("Selecciona una duración válida.")
    try:
        parsed_expected = int(expected_participants_count)
    except (TypeError, ValueError):
        return fail("Indica la cantidad esperada de participantes.")
    # La cantidad esperada nunca puede ser menor que los invitados seleccionados.
    parsed_expected = max(parsed_expected, len(participant_ids or []))

    try:
        reservation, warnings = create_reservation(
            db,
            requester=user,
            room=room,
            meeting_date=parsed_date,
            start_time=parsed_start,
            duration_minutes=parsed_duration,
            purpose=purpose,
            expected_participants_count=parsed_expected,
            participant_ids=participant_ids or [],
        )
    except BusinessRuleError as exc:
        return fail(exc.message)

    flash(
        request,
        f"Solicitud #{reservation.id} creada. El administrador validará la disponibilidad.",
        "success",
    )
    for warning in warnings:
        flash(request, warning, "warning")
    return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)


# ---------------------------------------------------------------------------
# Detalle y acciones del solicitante
# ---------------------------------------------------------------------------
@router.get("/reservations/{reservation_id}", name="reservation_detail")
def reservation_detail(
    request: Request,
    reservation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    reservation = _get_reservation(db, reservation_id)
    if not reservation.user_can_view(user):
        raise HTTPException(status_code=403, detail="No tienes acceso a esta reunión.")

    can_manage = reservation.requester_id == user.id or user.is_admin
    return render(
        request,
        "reservations/detail.html",
        {
            "user": user,
            "reservation": reservation,
            "can_manage": can_manage,
            "can_cancel": can_manage and reservation.can_be_cancelled,
            "is_assigned_authorizer": reservation.authorizer_id == user.id,
            "authorizers": _authorizers(db) if user.is_admin else [],
            "whatsapp_ready": reservation.status == ReservationStatus.AUTHORIZED and can_manage,
        },
    )


@router.post("/reservations/{reservation_id}/cancel", name="reservation_cancel")
def reservation_cancel(
    request: Request,
    reservation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    reason: str = Form(""),
):
    reservation = _get_reservation(db, reservation_id)
    if not reservation.user_can_view(user):
        raise HTTPException(status_code=403, detail="No tienes acceso a esta reunión.")
    try:
        cancel_reservation(reservation, actor=user, reason=reason)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, "La reunión fue cancelada y el horario quedó libre.", "success")
    return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)


@router.get("/my-meetings", name="my_meetings")
def my_meetings(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    today = today_caracas()
    meetings = list(
        db.scalars(
            select(Reservation)
            .join(ReservationParticipant, ReservationParticipant.reservation_id == Reservation.id)
            .where(
                ReservationParticipant.user_id == user.id,
                Reservation.status.in_((ReservationStatus.AUTHORIZED, ReservationStatus.PENDING_AUTHORIZER)),
                Reservation.meeting_date >= today,
            )
            .order_by(Reservation.meeting_date, Reservation.start_time)
        ).all()
    )
    past = list(
        db.scalars(
            select(Reservation)
            .join(ReservationParticipant, ReservationParticipant.reservation_id == Reservation.id)
            .where(
                ReservationParticipant.user_id == user.id,
                Reservation.status == ReservationStatus.AUTHORIZED,
                Reservation.meeting_date < today,
            )
            .order_by(Reservation.meeting_date.desc(), Reservation.start_time.desc())
            .limit(10)
        ).all()
    )
    return render(request, "meetings/mine.html", {"user": user, "meetings": meetings, "past": past})


# ---------------------------------------------------------------------------
# Convocatoria por WhatsApp
# ---------------------------------------------------------------------------
@router.get("/reservations/{reservation_id}/whatsapp", name="reservation_whatsapp")
def reservation_whatsapp(
    request: Request,
    reservation_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    reservation = _get_reservation(db, reservation_id)
    if reservation.requester_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Solo el anfitrión o un administrador pueden convocar.")
    if reservation.status != ReservationStatus.AUTHORIZED:
        flash(request, "La convocatoria se habilita cuando la reunión está autorizada.", "warning")
        return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)

    participants_data = []
    for row in reservation.participants:
        participant = row.user
        if participant is None:
            continue
        message = build_message(reservation, participant, reservation.requester.full_name)
        participants_data.append(
            {
                "row_id": row.id,
                "user_id": participant.id,
                "name": participant.full_name,
                "initials": participant.initials,
                "department": participant.department or "Sin departamento",
                "position": participant.position_title or "",
                "phone": participant.phone_whatsapp or "",
                "link": build_wa_link(participant.phone_whatsapp, message) if participant.phone_whatsapp else "",
                "message": message,
                "notified": row.whatsapp_notified,
            }
        )

    generic_message = build_generic_message(reservation)
    return render(
        request,
        "reservations/whatsapp.html",
        {
            "user": user,
            "reservation": reservation,
            "participants_data": participants_data,
            "generic_message": generic_message,
            "share_text": build_share_text(reservation, generic_message),
            "notified_count": reservation.participants_notified_count,
            "wa_json": json.dumps(participants_data, ensure_ascii=False),
        },
    )


@router.post("/reservations/{reservation_id}/whatsapp/{participant_row_id}/mark", name="reservation_whatsapp_mark")
def reservation_whatsapp_mark(
    request: Request,
    reservation_id: int,
    participant_row_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    notified: str = Form("true"),
):
    reservation = _get_reservation(db, reservation_id)
    wants_notified = notified.lower() in {"1", "true", "yes", "on"}
    try:
        row = mark_whatsapp_notified(
            reservation,
            participant_row_id=participant_row_id,
            actor=user,
            notified=wants_notified,
        )
    except BusinessRuleError as exc:
        if request.headers.get("x-requested-with") == "fetch":
            return JSONResponse({"ok": False, "message": exc.message}, status_code=400)
        flash(request, exc.message, "error")
    else:
        if request.headers.get("x-requested-with") == "fetch":
            return JSONResponse({"ok": True, "notified": row.whatsapp_notified})
        flash(
            request,
            "Participante marcado como enviado." if row.whatsapp_notified else "Marca de envío retirada.",
            "success",
        )
    return RedirectResponse(f"/reservations/{reservation.id}/whatsapp", status_code=303)
