"""Panel del Jefe Autorizador: aprobar o rechazar solicitudes validadas por admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import ReservationStatus, Role
from app.database import get_db
from app.dependencies import require_roles
from app.models import Reservation, User
from app.services.reservations import (
    BusinessRuleError,
    authorize_reservation,
    reject_by_authorizer,
)
from app.templating import flash, render

router = APIRouter(tags=["Autorizaciones"])


@router.get("/authorizations", name="authorizations_page")
def authorizations_page(
    request: Request,
    user: User = Depends(require_roles(Role.AUTHORIZER)),
    db: Session = Depends(get_db),
):
    pending = list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.status == ReservationStatus.PENDING_AUTHORIZER,
                Reservation.authorizer_id == user.id,
            )
            .order_by(Reservation.meeting_date, Reservation.start_time)
        ).all()
    )
    history = list(
        db.scalars(
            select(Reservation)
            .where(
                Reservation.authorizer_id == user.id,
                Reservation.status.in_((ReservationStatus.AUTHORIZED, ReservationStatus.REJECTED)),
            )
            .order_by(Reservation.updated_at.desc())
            .limit(25)
        ).all()
    )
    return render(
        request,
        "authorizations/pending.html",
        {"user": user, "pending": pending, "history": history},
    )


@router.post("/authorizations/{reservation_id}/approve", name="authorization_approve")
def authorization_approve(
    request: Request,
    reservation_id: int,
    user: User = Depends(require_roles(Role.AUTHORIZER)),
    db: Session = Depends(get_db),
    comment: str = Form(""),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe.")
    try:
        authorize_reservation(db, reservation=reservation, authorizer=user, comment=comment)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, f"Reunión autorizada. El horario de {reservation.room.name} quedó bloqueado.", "success")
    return RedirectResponse("/authorizations", status_code=303)


@router.post("/authorizations/{reservation_id}/reject", name="authorization_reject")
def authorization_reject(
    request: Request,
    reservation_id: int,
    user: User = Depends(require_roles(Role.AUTHORIZER)),
    db: Session = Depends(get_db),
    comment: str = Form(""),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe.")
    try:
        reject_by_authorizer(reservation, authorizer=user, comment=comment)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, "La solicitud fue rechazada. El solicitante podrá ver el motivo.", "success")
    return RedirectResponse("/authorizations", status_code=303)
