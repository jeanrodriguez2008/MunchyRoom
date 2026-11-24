"""Calendario diario y semanal por sala (hora de Caracas)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_cls
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import (
    CALENDAR_END_HOUR,
    CALENDAR_SLOT_HEIGHT,
    CALENDAR_START_HOUR,
    ReservationStatus,
)
from app.database import get_db
from app.dependencies import current_user
from app.models import MeetingRoom, Reservation, User
from app.templating import render
from app.timeutils import minutes_since_midnight, start_of_week, today_caracas, week_days

router = APIRouter(tags=["Calendario"])

WINDOW_START_MIN = CALENDAR_START_HOUR * 60
WINDOW_END_MIN = CALENDAR_END_HOUR * 60
PX_PER_MINUTE = CALENDAR_SLOT_HEIGHT / 60


def _parse_date(value: str | None) -> date_cls:
    if value:
        try:
            return date_cls.fromisoformat(value)
        except ValueError:
            pass
    return today_caracas()


def _position_events(reservations: list[Reservation]) -> list[dict]:
    """Calcula posición vertical de cada bloque dentro de la ventana visible."""
    events: list[dict] = []
    for reservation in reservations:
        start_min = minutes_since_midnight(reservation.start_time)
        end_min = minutes_since_midnight(reservation.end_time)
        visible_start = max(WINDOW_START_MIN, start_min)
        visible_end = min(WINDOW_END_MIN, end_min)
        if visible_end <= visible_start:
            continue
        events.append(
            {
                "reservation": reservation,
                "top": round((visible_start - WINDOW_START_MIN) * PX_PER_MINUTE, 1),
                "height": round(max(30.0, (visible_end - visible_start) * PX_PER_MINUTE), 1),
                "clipped_top": start_min < WINDOW_START_MIN,
                "clipped_bottom": end_min > WINDOW_END_MIN,
            }
        )
    return events


@router.get("/calendar", name="calendar_page")
def calendar_page(
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    date: str | None = Query(None),
    room_id: int | None = Query(None),
    view: str = Query("day"),
):
    selected_date = _parse_date(date)
    view = view if view in {"day", "week"} else "day"

    rooms = list(
        db.scalars(select(MeetingRoom).where(MeetingRoom.is_active.is_(True)).order_by(MeetingRoom.name)).all()
    )
    if room_id:
        rooms = [room for room in rooms if room.id == room_id]

    if view == "week":
        range_start = start_of_week(selected_date)
        range_end = range_start + timedelta(days=6)
    else:
        range_start = range_end = selected_date

    reservations = list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.meeting_date >= range_start,
                Reservation.meeting_date <= range_end,
                Reservation.status.in_(ReservationStatus.OPEN),
            )
            .order_by(Reservation.start_time)
        ).all()
    )

    hours = list(range(CALENDAR_START_HOUR, CALENDAR_END_HOUR))
    grid_height = (CALENDAR_END_HOUR - CALENDAR_START_HOUR) * CALENDAR_SLOT_HEIGHT

    day_columns: list[dict] = []
    if view == "day":
        by_room: dict[int, list[Reservation]] = defaultdict(list)
        for reservation in reservations:
            by_room[reservation.room_id].append(reservation)
        for room in rooms:
            day_columns.append({"room": room, "events": _position_events(by_room.get(room.id, []))})

    week_columns: list[dict] = []
    if view == "week":
        by_day: dict[date_cls, list[Reservation]] = defaultdict(list)
        for reservation in reservations:
            if not rooms or reservation.room_id in {room.id for room in rooms}:
                by_day[reservation.meeting_date].append(reservation)
        for day in week_days(selected_date):
            week_columns.append({"day": day, "reservations": by_day.get(day, [])})

    prev_date = selected_date - timedelta(days=7 if view == "week" else 1)
    next_date = selected_date + timedelta(days=7 if view == "week" else 1)

    return render(
        request,
        "calendar.html",
        {
            "user": user,
            "rooms": rooms,
            "selected_date": selected_date,
            "selected_room_id": room_id,
            "view": view,
            "hours": hours,
            "grid_height": grid_height,
            "day_columns": day_columns,
            "week_columns": week_columns,
            "prev_date": prev_date,
            "next_date": next_date,
            "week_end": range_end if view == "week" else selected_date,
            "today": today_caracas(),
            "window_start_hour": CALENDAR_START_HOUR,
            "window_end_hour": CALENDAR_END_HOUR,
        },
    )
