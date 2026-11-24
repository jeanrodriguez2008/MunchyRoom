"""Consultas de disponibilidad y detección de solapamientos."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import STATUS_META, ReservationStatus
from app.formatting import fmt_time, fmt_time_range
from app.models import Reservation
from app.timeutils import add_minutes, combine_caracas, now_caracas


def find_conflicts(
    db: Session,
    *,
    room_id: int,
    meeting_date: date,
    start_time: time,
    end_time: time,
    statuses: tuple[str, ...] = ReservationStatus.BLOCKING,
    exclude_id: int | None = None,
) -> list[Reservation]:
    """Devuelve reservas que se solapan con el rango indicado.

    Condición de solapamiento: ``start < otro.end AND end > otro.start`` para
    la misma sala y fecha. Se filtra por los estados solicitados.
    """
    stmt = (
        select(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.meeting_date == meeting_date,
            Reservation.status.in_(tuple(statuses)),
            Reservation.start_time < end_time,
            Reservation.end_time > start_time,
        )
        .order_by(Reservation.start_time)
    )
    if exclude_id is not None:
        stmt = stmt.where(Reservation.id != exclude_id)
    return list(db.scalars(stmt).all())


def describe_conflicts(conflicts: list[Reservation]) -> str:
    """Mensaje legible con el primer conflicto encontrado."""
    if not conflicts:
        return ""
    conflict = conflicts[0]
    status = STATUS_META.get(conflict.status, {}).get("short", conflict.status)
    return (
        f"Ya existe una reunión {status.lower()} en {conflict.room.name} "
        f"de {fmt_time_range(conflict.start_time, conflict.end_time)} "
        f"({conflict.purpose[:60]})."
    )


def check_slot(
    db: Session,
    *,
    room_id: int,
    meeting_date: date,
    start_time: time,
    duration_minutes: int,
    exclude_id: int | None = None,
) -> dict:
    """Valida un bloque horario y devuelve un payload para la API/UI.

    ``hard_conflict`` = solapamiento con reunión autorizada o en autorización
    final (bloqueo estricto). ``pending_warning`` = otra solicitud aún en
    revisión del administrador (el backend permite crearla, pero avisa).
    """
    try:
        end_time = add_minutes(start_time, duration_minutes)
    except ValueError as exc:
        return {"ok": False, "hard_conflict": True, "message": str(exc), "end_time": None}

    if combine_caracas(meeting_date, start_time) <= now_caracas():
        return {
            "ok": False,
            "hard_conflict": True,
            "message": "La fecha y hora de inicio debe ser futura.",
            "end_time": fmt_time(end_time),
        }

    blocking = find_conflicts(
        db,
        room_id=room_id,
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        statuses=ReservationStatus.BLOCKING,
        exclude_id=exclude_id,
    )
    pending = find_conflicts(
        db,
        room_id=room_id,
        meeting_date=meeting_date,
        start_time=start_time,
        end_time=end_time,
        statuses=(ReservationStatus.PENDING_ADMIN,),
        exclude_id=exclude_id,
    )

    payload = {
        "ok": not blocking,
        "hard_conflict": bool(blocking),
        "end_time": fmt_time(end_time),
        "conflicts": [
            {
                "id": item.id,
                "time": fmt_time_range(item.start_time, item.end_time),
                "status": item.status,
                "purpose": item.purpose,
            }
            for item in blocking
        ],
        "pending": [
            {
                "id": item.id,
                "time": fmt_time_range(item.start_time, item.end_time),
                "purpose": item.purpose,
            }
            for item in pending
        ],
    }
    if blocking:
        payload["message"] = describe_conflicts(blocking)
    elif pending:
        payload["message"] = (
            "Hay otra solicitud pendiente de administración en ese horario. "
            "Puedes enviarla, pero el administrador deberá resolver el cruce."
        )
    else:
        payload["message"] = "Horario disponible."
    return payload
