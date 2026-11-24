"""API JSON interna: verificación de disponibilidad en tiempo real."""

from __future__ import annotations

from datetime import date as date_cls
from datetime import time as time_cls

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.constants import MAX_DURATION_MINUTES, MIN_DURATION_MINUTES
from app.database import get_db
from app.dependencies import current_user
from app.models import MeetingRoom
from app.services.availability import check_slot

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/availability", name="api_availability")
def availability(
    room_id: int = Query(...),
    date: str = Query(...),
    start: str = Query(...),
    duration: int = Query(...),
    db: Session = Depends(get_db),
    user=Depends(current_user),
):
    """Valida fecha/hora/duración y devuelve conflictos con la sala."""
    try:
        meeting_date = date_cls.fromisoformat(date)
        start_time = time_cls.fromisoformat(start)
    except ValueError:
        return JSONResponse(
            {"ok": False, "hard_conflict": True, "message": "Fecha u hora inválidas."},
            status_code=400,
        )

    if duration < MIN_DURATION_MINUTES or duration > MAX_DURATION_MINUTES:
        return JSONResponse(
            {
                "ok": False,
                "hard_conflict": True,
                "message": f"La duración debe estar entre {MIN_DURATION_MINUTES} y {MAX_DURATION_MINUTES} minutos.",
            },
            status_code=400,
        )

    room = db.get(MeetingRoom, room_id)
    if room is None or not room.is_active:
        return JSONResponse(
            {"ok": False, "hard_conflict": True, "message": "La sala no existe o está desactivada."},
            status_code=404,
        )

    payload = check_slot(
        db,
        room_id=room.id,
        meeting_date=meeting_date,
        start_time=start_time,
        duration_minutes=duration,
    )
    return JSONResponse(payload)
