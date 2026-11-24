"""Autenticación: login, logout y cambio de contraseña."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MIN_PASSWORD_LENGTH, settings
from app.database import get_db
from app.dependencies import current_user
from app.models import User
from app.security import hash_password, login_limiter, verify_password
from app.templating import flash, render

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _safe_next(value: str | None) -> str:
    """Evita redirecciones abiertas: solo rutas internas."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def _client_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "desconocido"
    return f"{host}:{email.lower().strip()}"


@router.get("/login", name="login_page")
def login_page(request: Request, next: str = "", db: Session = Depends(get_db)):
    if request.session.get("uid"):
        return RedirectResponse("/", status_code=303)
    return render(
        request,
        "auth/login.html",
        {
            "next": _safe_next(next),
            "email": "",
            "show_seed_hint": settings.debug or not settings.is_production,
        },
    )


@router.post("/login", name="login_submit")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    key = _client_key(request, email)
    next_url = _safe_next(next)

    if login_limiter.is_blocked(key):
        seconds = login_limiter.seconds_remaining(key)
        flash(
            request,
            f"Demasiados intentos fallidos. Espera {max(1, seconds // 60)} minuto(s) e inténtalo de nuevo.",
            "error",
        )
        return render(
            request,
            "auth/login.html",
            {"next": next_url, "email": email, "show_seed_hint": False},
            status_code=429,
        )

    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        login_limiter.register_failure(key)
        # Mensaje genérico para no revelar si el correo existe.
        flash(request, "Correo o contraseña incorrectos. Verifica tus datos.", "error")
        return render(
            request,
            "auth/login.html",
            {"next": next_url, "email": email, "show_seed_hint": settings.debug},
            status_code=400,
        )

    login_limiter.reset(key)
    request.session.clear()
    request.session["uid"] = user.id
    flash(request, f"¡Bienvenido(a), {user.full_name.split()[0]}!", "success")

    if user.must_change_password:
        return RedirectResponse("/auth/password", status_code=303)
    return RedirectResponse(next_url, status_code=303)


@router.post("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/password", name="password_page")
def password_page(request: Request, user: User = Depends(current_user)):
    return render(request, "auth/password.html", {"user": user})


@router.post("/password", name="password_submit")
def password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    def error(message: str):
        flash(request, message, "error")
        return render(request, "auth/password.html", {"user": user}, status_code=400)

    if not verify_password(current_password, user.password_hash):
        return error("La contraseña actual no es correcta.")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return error(f"La nueva contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
    if new_password != confirm_password:
        return error("La confirmación no coincide con la nueva contraseña.")
    if new_password == current_password:
        return error("La nueva contraseña debe ser diferente a la actual.")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.add(user)
    flash(request, "Contraseña actualizada correctamente.", "success")
    return RedirectResponse("/", status_code=303)
