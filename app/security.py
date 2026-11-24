"""Seguridad: hash de contraseñas, validación de teléfonos y rate limit de login."""

from __future__ import annotations

import re
import threading
import time as time_module
import unicodedata
from collections import defaultdict

from passlib.context import CryptContext

from app.config import settings

# pbkdf2_sha256 evita dependencias binarias frágiles (bcrypt) en Render.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto", pbkdf2_sha256__default_rounds=29000)

PHONE_RE = re.compile(r"^\+\d{8,15}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(plain_password, password_hash)
    except (ValueError, TypeError):
        return False


def normalize_phone(raw: str | None) -> str:
    """Normaliza un teléfono al formato internacional +58412...; '' si inválido.

    Acepta espacios, guiones y paréntesis. Si no trae '+', se asume que ya
    incluye el código de país (ej. 584121234567).
    """
    if not raw:
        return ""
    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    if cleaned.count("+") != 1 or not PHONE_RE.match(cleaned):
        return ""
    return cleaned


def whatsapp_digits(phone: str | None) -> str:
    """Número en formato wa.me (solo dígitos, sin '+' ni separadores)."""
    return re.sub(r"\D", "", phone or "")


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def normalize_answer(raw: str | None) -> str:
    """Normaliza una respuesta de seguridad para compararla sin distinguir
    mayúsculas, tildes, signos ni espacios repetidos."""
    text = unicodedata.normalize("NFKD", (raw or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def hash_answer(raw: str) -> str:
    return hash_password(normalize_answer(raw))


def verify_answer(raw: str | None, answer_hash: str | None) -> bool:
    normalized = normalize_answer(raw)
    if not normalized or not answer_hash:
        return False
    return verify_password(normalized, answer_hash)


class LoginRateLimiter:
    """Límite de intentos de login en memoria (por proceso).

    Suficiente para una instancia de Render; si se escala horizontalmente se
    puede sustituir por Redis sin cambiar la interfaz.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._attempts[key] = [ts for ts in self._attempts[key] if ts > cutoff]

    def is_blocked(self, key: str) -> bool:
        now = time_module.time()
        with self._lock:
            self._prune(key, now)
            return len(self._attempts[key]) >= self.max_attempts

    def register_failure(self, key: str) -> None:
        now = time_module.time()
        with self._lock:
            self._prune(key, now)
            self._attempts[key].append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def seconds_remaining(self, key: str) -> int:
        now = time_module.time()
        with self._lock:
            self._prune(key, now)
            attempts = self._attempts[key]
            if len(attempts) < self.max_attempts:
                return 0
            return max(0, int(self.window_seconds - (now - attempts[0])))


login_limiter = LoginRateLimiter(settings.login_max_attempts, settings.login_window_seconds)
