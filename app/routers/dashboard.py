"""Panel principal: resumen por rol y próximas reuniones."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import ReservationStatus, Role
from app.database import get_db
from app.dependencies import current_user
from app.models import MeetingRoom, Reservation, ReservationParticipant, User
from app.services.reservations import upcoming_for_user
from app.templating import render
from app.timeutils import today_caracas

router = APIRouter(tags=["Panel"])


@router.get("/", name="dashboard")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    today = today_caracas()
    stats: dict[str, int] = {}

    if user.is_admin:
        stats["pending_admin"] = db.scalar(
            select(func.count()).select_from(Reservation).where(
                Reservation.status == ReservationStatus.PENDING_ADMIN
            )
        ) or 0

    if user.has_role(Role.AUTHORIZER):
        stats["pending_authorizer"] = db.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.status == ReservationStatus.PENDING_AUTHORIZER,
                Reservation.authorizer_id == user.id,
            )
        ) or 0

    stats["my_open"] = db.scalar(
        select(func.count())
        .select_from(Reservation)
        .where(
            Reservation.requester_id == user.id,
            Reservation.status.in_(ReservationStatus.OPEN),
        )
    ) or 0

    stats["invitations"] = db.scalar(
        select(func.count())
        .select_from(ReservationParticipant)
        .join(Reservation, Reservation.id == ReservationParticipant.reservation_id)
        .where(
            ReservationParticipant.user_id == user.id,
            Reservation.status == ReservationStatus.AUTHORIZED,
            Reservation.meeting_date >= today,
        )
    ) or 0

    upcoming = upcoming_for_user(db, user, limit=4)

    # Agenda de hoy por sala (solo estados abiertos).
    rooms = list(db.scalars(select(MeetingRoom).where(MeetingRoom.is_active.is_(True)).order_by(MeetingRoom.name)).all())
    today_reservations = list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.meeting_date == today,
                Reservation.status.in_(ReservationStatus.OPEN),
            )
            .order_by(Reservation.start_time)
        ).all()
    )
    agenda: dict[int, list[Reservation]] = defaultdict(list)
    for reservation in today_reservations:
        agenda[reservation.room_id].append(reservation)

    pending_admin_list = []
    if user.is_admin:
        pending_admin_list = list(
            db.scalars(
                select(Reservation)
                .where(Reservation.status == ReservationStatus.PENDING_ADMIN)
                .order_by(Reservation.created_at)
                .limit(5)
            ).all()
        )

    pending_auth_list = []
    if user.has_role(Role.AUTHORIZER):
        pending_auth_list = list(
            db.scalars(
                select(Reservation)
                .where(
                    Reservation.status == ReservationStatus.PENDING_AUTHORIZER,
                    Reservation.authorizer_id == user.id,
                )
                .order_by(Reservation.created_at)
                .limit(5)
            ).all()
        )

    return render(
        request,
        "dashboard.html",
        {
            "user": user,
            "stats": stats,
            "upcoming": upcoming,
            "rooms": rooms,
            "agenda": agenda,
            "pending_admin_list": pending_admin_list,
            "pending_auth_list": pending_auth_list,
            "today": today,
        },
    )
