"""Cuentas de usuario: autorregistro y preguntas de seguridad.

Reglas:
- El autorregistro exige correo corporativo y teléfono WhatsApp válido.
- El usuario nace sin roles: queda pendiente hasta que un administrador los asigne.
- Las respuestas de seguridad se guardan hasheadas y normalizadas.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MIN_PASSWORD_LENGTH, settings
from app.constants import (
    SECURITY_ANSWER_MAX_LENGTH,
    SECURITY_ANSWER_MIN_LENGTH,
    SECURITY_QUESTION_MAP,
    SECURITY_QUESTIONS_REQUIRED,
)
from app.models import User, UserSecurityAnswer
from app.security import (
    hash_answer,
    hash_password,
    is_valid_email,
    normalize_answer,
    normalize_phone,
    verify_answer,
    verify_password,
)


class AccountError(Exception):
    """Error de validación mostrable al usuario."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def is_corporate_email(value: str) -> bool:
    """Valida que el correo pertenezca a un dominio corporativo permitido."""
    email = (value or "").strip().lower()
    if not is_valid_email(email):
        return False
    domain = email.rsplit("@", 1)[1]
    return any(
        domain == allowed or domain.endswith("." + allowed)
        for allowed in settings.corporate_email_domains
    )


def validate_new_password(password: str, confirm_password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(
            f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
        )
    if password != confirm_password:
        raise AccountError("La confirmación no coincide con la nueva contraseña.")


def validate_security_answers(
    question_keys: list[str] | None,
    answers: list[str] | None,
) -> list[tuple[str, str]]:
    """Valida las tres preguntas y devuelve pares (clave, respuesta) limpios."""
    keys = list(question_keys or [])
    values = list(answers or [])
    if len(keys) != SECURITY_QUESTIONS_REQUIRED or len(values) != SECURITY_QUESTIONS_REQUIRED:
        raise AccountError(
            f"Debes seleccionar y responder {SECURITY_QUESTIONS_REQUIRED} preguntas de seguridad."
        )

    pairs: list[tuple[str, str]] = []
    used: set[str] = set()
    for index, (raw_key, raw_answer) in enumerate(zip(keys, values), start=1):
        key = (raw_key or "").strip()
        if key not in SECURITY_QUESTION_MAP:
            raise AccountError(f"Selecciona la pregunta de seguridad {index}.")
        if key in used:
            raise AccountError("No puedes repetir la misma pregunta de seguridad.")
        used.add(key)

        answer = (raw_answer or "").strip()
        if len(answer) > SECURITY_ANSWER_MAX_LENGTH:
            raise AccountError(
                f"La respuesta a «{SECURITY_QUESTION_MAP[key]}» no puede superar "
                f"{SECURITY_ANSWER_MAX_LENGTH} caracteres."
            )
        if len(normalize_answer(answer)) < SECURITY_ANSWER_MIN_LENGTH:
            raise AccountError(
                f"La respuesta a «{SECURITY_QUESTION_MAP[key]}» es demasiado corta."
            )
        pairs.append((key, answer))

    return pairs


def register_user(
    db: Session,
    *,
    full_name: str,
    email: str,
    phone_whatsapp: str,
    department: str,
    password: str,
    confirm_password: str,
    question_keys: list[str] | None,
    answers: list[str] | None,
) -> User:
    """Crea una cuenta pendiente de roles a partir del formulario público."""
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    department = (department or "").strip()

    if len(full_name) < 3:
        raise AccountError("Escribe tu nombre y apellido completos.")
    if not is_valid_email(email):
        raise AccountError("El correo electrónico no es válido.")
    if not is_corporate_email(email):
        allowed = ", ".join(f"@{domain}" for domain in settings.corporate_email_domains)
        raise AccountError(f"Debes registrarte con tu correo corporativo ({allowed}).")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise AccountError(
            "Ese correo ya está registrado. Si es tuyo, usa «¿Olvidaste tu contraseña?»."
        )

    phone = normalize_phone(phone_whatsapp)
    if not phone:
        raise AccountError(
            "El número de WhatsApp es obligatorio y debe incluir el código de país. "
            "Ejemplo: +584121234567."
        )

    validate_new_password(password, confirm_password)
    pairs = validate_security_answers(question_keys, answers)

    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        phone_whatsapp=phone,
        department=department,
        position_title="",
        is_active=True,
        must_change_password=False,
    )
    user.security_answers = [
        UserSecurityAnswer(question_key=key, answer_hash=hash_answer(answer))
        for key, answer in pairs
    ]
    db.add(user)
    db.flush()
    return user


def set_security_answers(
    db: Session,
    user: User,
    *,
    question_keys: list[str] | None,
    answers: list[str] | None,
    current_password: str | None = None,
) -> None:
    """Reemplaza las preguntas de seguridad de una cuenta existente.

    Si se indica ``current_password``, se exige que coincida con la actual.
    """
    if current_password is not None and not verify_password(current_password, user.password_hash):
        raise AccountError("La contraseña actual no es correcta.")

    pairs = validate_security_answers(question_keys, answers)

    # Se eliminan y vuelven a crear para evitar chocar con la restricción única
    # cuando el usuario conserva algunas de sus preguntas anteriores.
    for row in list(user.security_answers):
        user.security_answers.remove(row)
    db.flush()
    for key, answer in pairs:
        user.security_answers.append(
            UserSecurityAnswer(question_key=key, answer_hash=hash_answer(answer))
        )
    db.flush()


def verify_security_answers(user: User, answers: dict[str, str]) -> bool:
    """Comprueba todas las respuestas configuradas sin cortar en la primera."""
    if len(user.security_answers) < SECURITY_QUESTIONS_REQUIRED:
        return False
    valid = True
    for stored in user.security_answers:
        if not verify_answer(answers.get(stored.question_key, ""), stored.answer_hash):
            valid = False
    return valid


def user_security_questions(user: User) -> list[tuple[str, str]]:
    """Preguntas configuradas por el usuario, en el orden en que las guardó."""
    return [
        (row.question_key, SECURITY_QUESTION_MAP.get(row.question_key, row.question_key))
        for row in user.security_answers
    ]
