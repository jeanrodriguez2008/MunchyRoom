"""Autenticación: login, autorregistro, recuperación y cambio de contraseña."""

from __future__ import annotations

import time as time_module

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MIN_PASSWORD_LENGTH, settings
from app.database import get_db
from app.dependencies import current_user
from app.models import User
from app.security import LoginRateLimiter, hash_password, login_limiter, verify_password
from app.services.accounts import (
    AccountError,
    register_user,
    set_security_answers,
    user_security_questions,
    validate_new_password,
    verify_security_answers,
)
from app.services.directory import active_departments
from app.templating import flash, render

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Límites en memoria por proceso (suficiente para una instancia de Render).
recovery_limiter = LoginRateLimiter(
    settings.recovery_max_attempts, settings.recovery_window_seconds
)
registration_limiter = LoginRateLimiter(
    settings.registration_max_attempts, settings.registration_window_seconds
)

RECOVERY_SESSION_SECONDS = 15 * 60


def _safe_next(value: str | None) -> str:
    """Evita redirecciones abiertas: solo rutas internas."""
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"


def _client_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "desconocido"
    return f"{host}:{email.lower().strip()}"


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "desconocido"


def _password_context(user: User) -> dict:
    return {"user": user, "current_questions": user_security_questions(user)}


def _clear_recovery(request: Request) -> None:
    for key in ("recover_uid", "recover_started", "recover_email"):
        request.session.pop(key, None)


def _recovery_user(request: Request, db: Session) -> User | None:
    """Usuario en proceso de recuperación, si la sesión sigue vigente."""
    raw_uid = request.session.get("recover_uid")
    started = request.session.get("recover_started") or 0
    if not raw_uid or not started:
        return None
    try:
        if time_module.time() - int(started) > RECOVERY_SESSION_SECONDS:
            return None
        user = db.get(User, int(raw_uid))
    except (TypeError, ValueError):
        return None
    if user is None or not user.is_active or not user.has_security_questions:
        return None
    return user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
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

    # Los autorregistros nacen sin roles y quedan a la espera del administrador.
    if user.is_pending_roles:
        flash(
            request,
            "Tu registro fue recibido. Un administrador debe asignarte al menos un rol "
            "antes de que puedas ingresar.",
            "warning",
        )
        return render(
            request,
            "auth/login.html",
            {"next": next_url, "email": email, "show_seed_hint": False},
            status_code=403,
        )

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


# ---------------------------------------------------------------------------
# Autorregistro
# ---------------------------------------------------------------------------
@router.get("/register", name="register_page")
def register_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("uid"):
        return RedirectResponse("/", status_code=303)
    return render(
        request,
        "auth/register.html",
        {
            "form_data": {
                "full_name": "",
                "email": "",
                "phone_whatsapp": "",
                "department": "",
                "questions": ["", "", ""],
            },
            "departments": active_departments(db),
        },
    )


@router.post("/register", name="register_submit")
def register_submit(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    phone_whatsapp: str = Form(""),
    department: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    question: list[str] | None = Form(None),
    answer: list[str] | None = Form(None),
    db: Session = Depends(get_db),
):
    if request.session.get("uid"):
        return RedirectResponse("/", status_code=303)

    host = _client_host(request)
    form_data = {
        "full_name": full_name,
        "email": email,
        "phone_whatsapp": phone_whatsapp,
        "department": department,
        "questions": (question or [])[:3],
    }

    if registration_limiter.is_blocked(host):
        flash(
            request,
            "Se alcanzó el límite de registros desde esta conexión. Inténtalo más tarde.",
            "error",
        )
        return render(
            request,
            "auth/register.html",
            {"form_data": form_data, "departments": active_departments(db)},
            status_code=429,
        )

    try:
        user = register_user(
            db,
            full_name=full_name,
            email=email,
            phone_whatsapp=phone_whatsapp,
            department=department,
            password=password,
            confirm_password=confirm_password,
            question_keys=question,
            answers=answer,
        )
    except AccountError as exc:
        flash(request, exc.message, "error")
        return render(
            request,
            "auth/register.html",
            {"form_data": form_data, "departments": active_departments(db)},
            status_code=400,
        )

    registration_limiter.register_failure(host)
    flash(
        request,
        f"Registro enviado para {user.email}. Un administrador revisará tu cuenta y te "
        "asignará los roles necesarios; después podrás iniciar sesión.",
        "success",
    )
    return RedirectResponse("/auth/login", status_code=303)


# ---------------------------------------------------------------------------
# Recuperación de contraseña con preguntas de seguridad
# ---------------------------------------------------------------------------
@router.get("/recover", name="recover_page")
def recover_page(request: Request):
    _clear_recovery(request)
    return render(request, "auth/recover.html", {"email": ""})


@router.post("/recover", name="recover_submit")
def recover_submit(
    request: Request,
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    email = (email or "").strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.is_active and user.has_security_questions:
        request.session["recover_uid"] = user.id
        request.session["recover_started"] = int(time_module.time())
        request.session["recover_email"] = user.email
        return RedirectResponse("/auth/recover/reset", status_code=303)

    # Respuesta genérica: no revela si el correo existe o tiene preguntas.
    flash(
        request,
        "Si el correo pertenece a una cuenta activa con preguntas de seguridad configuradas, "
        "podrás continuar. Si aún no las has configurado, inicia sesión y hazlo en "
        "«Cambiar contraseña».",
        "info",
    )
    return render(request, "auth/recover.html", {"email": email})


@router.get("/recover/reset", name="recover_reset_page")
def recover_reset_page(
    request: Request,
    db: Session = Depends(get_db),
):
    user = _recovery_user(request, db)
    if user is None:
        _clear_recovery(request)
        flash(request, "Inicia el proceso de recuperación nuevamente.", "info")
        return RedirectResponse("/auth/recover", status_code=303)

    return render(
        request,
        "auth/recover_reset.html",
        {
            "email": request.session.get("recover_email", user.email),
            "questions": user_security_questions(user),
        },
    )


@router.post("/recover/reset", name="recover_reset_submit")
def recover_reset_submit(
    request: Request,
    new_password: str = Form(""),
    confirm_password: str = Form(""),
    question: list[str] | None = Form(None),
    answer: list[str] | None = Form(None),
    db: Session = Depends(get_db),
):
    email = request.session.get("recover_email", "")
    key = _client_key(request, email)

    if recovery_limiter.is_blocked(key):
        _clear_recovery(request)
        flash(
            request,
            "Demasiados intentos. Espera unos minutos e inicia la recuperación nuevamente.",
            "error",
        )
        return RedirectResponse("/auth/recover", status_code=303)

    user = _recovery_user(request, db)
    if user is None:
        _clear_recovery(request)
        flash(request, "Inicia el proceso de recuperación nuevamente.", "info")
        return RedirectResponse("/auth/recover", status_code=303)

    submitted = {
        (raw_key or "").strip(): (raw_value or "")
        for raw_key, raw_value in zip(question or [], answer or [])
    }
    if not verify_security_answers(user, submitted):
        recovery_limiter.register_failure(key)
        flash(request, "Las respuestas de seguridad no coinciden. Verifica e inténtalo de nuevo.", "error")
        return render(
            request,
            "auth/recover_reset.html",
            {
                "email": request.session.get("recover_email", user.email),
                "questions": user_security_questions(user),
            },
            status_code=400,
        )

    try:
        validate_new_password(new_password, confirm_password)
    except AccountError as exc:
        flash(request, exc.message, "error")
        return render(
            request,
            "auth/recover_reset.html",
            {
                "email": request.session.get("recover_email", user.email),
                "questions": user_security_questions(user),
            },
            status_code=400,
        )

    recovery_limiter.reset(key)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.add(user)

    request.session.clear()
    flash(request, "Contraseña restablecida correctamente. Ya puedes iniciar sesión.", "success")
    return RedirectResponse("/auth/login", status_code=303)


# ---------------------------------------------------------------------------
# Cambio de contraseña y preguntas de seguridad
# ---------------------------------------------------------------------------
@router.get("/password", name="password_page")
def password_page(request: Request, user: User = Depends(current_user)):
    return render(request, "auth/password.html", _password_context(user))


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
        return render(request, "auth/password.html", _password_context(user), status_code=400)

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


@router.post("/security-questions", name="security_questions_submit")
def security_questions_submit(
    request: Request,
    current_password: str = Form(""),
    question: list[str] | None = Form(None),
    answer: list[str] | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        set_security_answers(
            db,
            user,
            question_keys=question,
            answers=answer,
            current_password=current_password,
        )
    except AccountError as exc:
        flash(request, exc.message, "error")
        return render(request, "auth/password.html", _password_context(user), status_code=400)

    flash(
        request,
        "Preguntas de seguridad actualizadas. Guárdalas muy bien: son la llave para "
        "recuperar tu contraseña.",
        "success",
    )
    return RedirectResponse("/auth/password", status_code=303)
