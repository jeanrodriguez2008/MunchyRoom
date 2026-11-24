"""Reglas de negocio de reservas: creación, doble validación, cancelación y WhatsApp.

Todas las validaciones críticas viven aquí (no solo en la interfaz), de modo
que cualquier intento directo a la API quede protegido.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    CANCELLATION_MIN_HOURS,
    MAX_DURATION_MINUTES,
    MIN_DURATION_MINUTES,
    ReservationStatus,
    Role,
)
from app.models import MeetingRoom, Reservation, ReservationParticipant, User
from app.services.availability import describe_conflicts, find_conflicts
from app.timeutils import add_minutes, combine_caracas, now_caracas, utc_now


class BusinessRuleError(Exception):
    """Error de negocio con mensaje listo para mostrar al usuario."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _validate_room(room: MeetingRoom) -> None:
    if not room.is_active:
        raise BusinessRuleError(f"La sala «{room.name}» está desactivada y no admite reservas.")


def _validate_datetime(meeting_date: date, start_time: time, duration_minutes: int) -> time:
    if duration_minutes < MIN_DURATION_MINUTES or duration_minutes > MAX_DURATION_MINUTES:
        raise BusinessRuleError(
            f"La duración debe estar entre {MIN_DURATION_MINUTES} minutos y "
            f"{MAX_DURATION_MINUTES // 60} horas."
        )
    try:
        end_time = add_minutes(start_time, duration_minutes)
    except ValueError as exc:
        raise BusinessRuleError(str(exc)) from exc

    start_dt = combine_caracas(meeting_date, start_time)
    if start_dt <= now_caracas():
        raise BusinessRuleError("La fecha y hora de inicio debe ser futura (hora de Caracas).")
    if meeting_date > now_caracas().date() + timedelta(days=365):
        raise BusinessRuleError("No se pueden crear reservas con más de un año de anticipación.")
    return end_time


def _load_participants(db: Session, participant_ids: list[int]) -> list[User]:
    unique_ids = list(dict.fromkeys(int(pid) for pid in participant_ids if pid))
    if not unique_ids:
        raise BusinessRuleError("Selecciona al menos un participante para la reunión.")

    users = list(
        db.scalars(
            select(User).where(User.id.in_(unique_ids), User.is_active.is_(True)).order_by(User.full_name)
        ).all()
    )
    if len(users) != len(unique_ids):
        raise BusinessRuleError("Uno o más participantes no existen o están desactivados.")

    for user in users:
        if not user.has_role(Role.PARTICIPANT):
            raise BusinessRuleError(f"{user.full_name} no tiene el rol de participante.")
    return users


def create_reservation(
    db: Session,
    *,
    requester: User,
    room: MeetingRoom,
    meeting_date: date,
    start_time: time,
    duration_minutes: int,
    purpose: str,
    expected_participants_count: int,
    participant_ids: list[int],
) -> tuple[Reservation, list[str]]:
    """Crea una solicitud en estado PENDIENTE_ADMIN.

    Devuelve la reserva y una lista de advertencias no bloqueantes.
    """
    _validate_room(room)
    end_time = _validate_datetime(meeting_date, start_time, duration_minutes)

    purpose = (purpose or "").strip()
    if len(purpose) < 5:
        raise BusinessRuleError("Describe el motivo de la reunión (mínimo 5 caracteres).")

    participants = _load_participants(db, participant_ids)

    if expected_participants_count < 1:
        raise BusinessRuleError("Indica la cantidad esperada de participantes.")
    if expected_participants_count < len(participants):
        raise BusinessRuleError(
            "La cantidad esperada de participantes no puede ser menor que los participantes seleccionados."
        )
    if expected_participants_count > room.capacity:
        raise BusinessRuleError(
            f"La sala «{room.name}» tiene capacidad para {room.capacity} personas."
        )

    conflicts = find_conflicts(
        db,
        room_id=room.id,
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        statuses=ReservationStatus.BLOCKING,
    )
    if conflicts:
        raise BusinessRuleError(
            "Horario no disponible. " + describe_conflicts(conflicts)
        )

    pending = find_conflicts(
        db,
        room_id=room.id,
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        statuses=(ReservationStatus.PENDING_ADMIN,),
    )
    warnings: list[str] = []
    if pending:
        warnings.append(
            "Existe otra solicitud pendiente de administración en el mismo horario. "
            "El administrador deberá resolver cuál se autoriza."
        )

    reservation = Reservation(
        room_id=room.id,
        requester_id=requester.id,
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        purpose=purpose,
        expected_participants_count=expected_participants_count,
        status=ReservationStatus.PENDING_ADMIN,
    )
    for participant in participants:
        reservation.participants.append(ReservationParticipant(user_id=participant.id))

    db.add(reservation)
    db.flush()
    return reservation, warnings


def send_to_authorizer(
    db: Session,
    *,
    reservation: Reservation,
    admin: User,
    authorizer: User,
    note: str = "",
) -> None:
    """Paso 2: el administrador valida el horario y escala al jefe autorizador."""
    if reservation.status != ReservationStatus.PENDING_ADMIN:
        raise BusinessRuleError("Solo se pueden enviar solicitudes pendientes de administración.")

    if not authorizer.is_active or not authorizer.has_role(Role.AUTHORIZER):
        raise BusinessRuleError("El usuario seleccionado no es un jefe autorizador activo.")

    # Bloqueo estricto también contra otras solicitudes pendientes de admin:
    # evita que dos solicitudes del mismo horario lleguen a autorización final.
    conflicts = find_conflicts(
        db,
        room_id=reservation.room_id,
        meeting_date=reservation.meeting_date,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        statuses=ReservationStatus.BLOCKING + (ReservationStatus.PENDING_ADMIN,),
        exclude_id=reservation.id,
    )
    if conflicts:
        raise BusinessRuleError(
            "No se puede enviar: hay otra solicitud en el mismo horario. "
            + describe_conflicts(conflicts)
        )

    reservation.status = ReservationStatus.PENDING_AUTHORIZER
    reservation.admin_validator_id = admin.id
    reservation.authorizer_id = authorizer.id
    reservation.admin_note = (note or "").strip()
    reservation.rejection_reason = ""


def reassign_authorizer(reservation: Reservation, authorizer: User) -> None:
    """Permite al administrador cambiar el jefe autorizador mientras está pendiente."""
    if reservation.status != ReservationStatus.PENDING_AUTHORIZER:
        raise BusinessRuleError("Solo se puede reasignar una solicitud pendiente de autorización.")
    if not authorizer.is_active or not authorizer.has_role(Role.AUTHORIZER):
        raise BusinessRuleError("El usuario seleccionado no es un jefe autorizador activo.")
    reservation.authorizer_id = authorizer.id


def authorize_reservation(
    db: Session,
    *,
    reservation: Reservation,
    authorizer: User,
    comment: str = "",
) -> None:
    """Paso 3: aprobación final del jefe autorizador (bloquea el horario)."""
    if reservation.status != ReservationStatus.PENDING_AUTHORIZER:
        raise BusinessRuleError("La solicitud no está pendiente de autorización.")
    if reservation.authorizer_id != authorizer.id:
        raise BusinessRuleError("Esta solicitud está asignada a otro jefe autorizador.")

    conflicts = find_conflicts(
        db,
        room_id=reservation.room_id,
        meeting_date=reservation.meeting_date,
        start_time=reservation.start_time,
        end_time=reservation.end_time,
        statuses=ReservationStatus.BLOCKING,
        exclude_id=reservation.id,
    )
    if conflicts:
        raise BusinessRuleError("No se puede autorizar. " + describe_conflicts(conflicts))

    reservation.status = ReservationStatus.AUTHORIZED
    reservation.authorizer_comment = (comment or "").strip()
    reservation.rejection_reason = ""


def reject_by_authorizer(
    reservation: Reservation,
    *,
    authorizer: User,
    comment: str = "",
) -> None:
    if reservation.status != ReservationStatus.PENDING_AUTHORIZER:
        raise BusinessRuleError("La solicitud no está pendiente de autorización.")
    if reservation.authorizer_id != authorizer.id:
        raise BusinessRuleError("Esta solicitud está asignada a otro jefe autorizador.")

    comment = (comment or "").strip()
    reservation.status = ReservationStatus.REJECTED
    reservation.authorizer_comment = comment
    reservation.rejection_reason = comment or "Rechazada por el jefe autorizador."


def reject_by_admin(reservation: Reservation, *, admin: User, reason: str = "") -> None:
    if reservation.status != ReservationStatus.PENDING_ADMIN:
        raise BusinessRuleError("Solo el administrador puede rechazar solicitudes pendientes de su revisión.")
    reason = (reason or "").strip()
    reservation.status = ReservationStatus.REJECTED
    reservation.admin_validator_id = admin.id
    reservation.rejection_reason = reason or "Rechazada por el administrador."
    reservation.authorizer_comment = ""


def cancel_reservation(
    reservation: Reservation,
    *,
    actor: User,
    reason: str = "",
) -> None:
    """Cancela una reserva respetando la regla estricta de 24 horas."""
    if reservation.status not in ReservationStatus.CANCELLABLE:
        raise BusinessRuleError("Esta solicitud ya no se puede cancelar.")
    if reservation.requester_id != actor.id and not actor.is_admin:
        raise BusinessRuleError("Solo el solicitante o un administrador pueden cancelar la reunión.")

    if not reservation.can_be_cancelled:
        raise BusinessRuleError("No es posible cancelar con menos de 24 horas de anticipación.")

    note = (reason or "").strip()
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = utc_now()
    reservation.cancelled_by_id = actor.id
    if note:
        reservation.admin_note = (
            (reservation.admin_note + "\n" if reservation.admin_note else "") + f"Cancelación: {note}"
        )


def mark_whatsapp_notified(
    reservation: Reservation,
    *,
    participant_row_id: int,
    actor: User,
    notified: bool = True,
) -> ReservationParticipant:
    """Marca/desmarca a un participante como convocado por WhatsApp."""
    if reservation.status != ReservationStatus.AUTHORIZED:
        raise BusinessRuleError("Solo se pueden convocar participantes de reuniones autorizadas.")
    if reservation.requester_id != actor.id and not actor.is_admin:
        raise BusinessRuleError("Solo el anfitrión de la reunión puede gestionar la convocatoria.")

    row = next((p for p in reservation.participants if p.id == participant_row_id), None)
    if row is None:
        raise BusinessRuleError("Participante no encontrado en esta reunión.")

    row.whatsapp_notified = notified
    row.notified_at = utc_now() if notified else None
    return row


# ---------------------------------------------------------------------------
# Utilidades de consulta usadas por los paneles
# ---------------------------------------------------------------------------
def upcoming_for_user(db: Session, user: User, limit: int = 5) -> list[Reservation]:
    """Próximas reuniones autorizadas donde el usuario es anfitrión o invitado."""
    today = now_caracas().date()
    stmt = (
        select(Reservation)
        .outerjoin(ReservationParticipant, ReservationParticipant.reservation_id == Reservation.id)
        .where(
            Reservation.status == ReservationStatus.AUTHORIZED,
            Reservation.meeting_date >= today,
        )
        .where(
            (Reservation.requester_id == user.id) | (ReservationParticipant.user_id == user.id)
        )
        .distinct()
        .order_by(Reservation.meeting_date, Reservation.start_time)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
