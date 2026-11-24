"""Configuración central de MunchyRoom.

Lee las variables de entorno (archivo .env en desarrollo, variables del panel de
Render en producción) y normaliza la cadena de conexión de Neon Tech para que
SQLAlchemy utilice el driver psycopg2.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env solo si existe (en Render las variables vienen del panel).
load_dotenv(BASE_DIR / ".env")


def normalize_database_url(url: str) -> str:
    """Adapta la URL de Neon/Postgres al driver psycopg2 de SQLAlchemy.

    Neon entrega URLs del tipo ``postgresql://...?sslmode=require``. SQLAlchemy
    necesita el prefijo ``postgresql+psycopg2://`` para elegir el driver.
    """
    url = (url or "").strip()
    if not url:
        # Fallback de desarrollo: SQLite local (no recomendado en producción).
        return "sqlite:///./munchyroom.db"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


class Settings:
    """Configuración inmutable de la aplicación."""

    def __init__(self) -> None:
        self.app_name: str = "MunchyRoom"
        self.company_name: str = "Alimentos Munchy, C.A."
        self.base_dir: Path = BASE_DIR
        self.env: str = os.getenv("ENV", "development").strip().lower()
        self.debug: bool = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

        self.database_url: str = normalize_database_url(os.getenv("DATABASE_URL", ""))
        self.secret_key: str = os.getenv("SECRET_KEY", "dev-insecure-secret-key-change-me")
        self.timezone: str = os.getenv("TZ", "America/Caracas")

        # Cookies: en Render (HTTPS) debe estar en true. En local, false.
        self.cookie_secure: bool = os.getenv(
            "COOKIE_SECURE", "true" if self.env == "production" else "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self.session_max_age: int = int(os.getenv("SESSION_MAX_AGE", str(8 * 60 * 60)))

        # Credenciales del administrador inicial (seed).
        self.seed_admin_email: str = os.getenv("SEED_ADMIN_EMAIL", "admin@munchy.com")
        self.seed_admin_password: str = os.getenv("SEED_ADMIN_PASSWORD", "MunchyAdmin2026*")
        self.seed_admin_name: str = os.getenv("SEED_ADMIN_NAME", "Administrador MunchyRoom")

        # Cuenta de soporte webmaster: oculta para los administradores.
        # Solo se crea automáticamente si WEBMASTER_PASSWORD tiene un valor.
        self.webmaster_email: str = os.getenv("WEBMASTER_EMAIL", "webmaster@munchy.com").strip().lower()
        self.webmaster_name: str = os.getenv("WEBMASTER_NAME", "Webmaster MunchyRoom").strip()
        self.webmaster_password: str = os.getenv("WEBMASTER_PASSWORD", "").strip()

        # Dominios corporativos permitidos para el autorregistro.
        raw_domains = os.getenv("CORPORATE_EMAIL_DOMAINS", "munchy.com")
        self.corporate_email_domains: tuple[str, ...] = tuple(
            domain.strip().lower().lstrip("@")
            for domain in raw_domains.split(",")
            if domain.strip()
        ) or ("munchy.com",)

        # Límite de intentos de login (protección básica contra fuerza bruta).
        self.login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "8"))
        self.login_window_seconds: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "300"))

        # Límite de intentos de recuperación de contraseña.
        self.recovery_max_attempts: int = int(os.getenv("RECOVERY_MAX_ATTEMPTS", "5"))
        self.recovery_window_seconds: int = int(os.getenv("RECOVERY_WINDOW_SECONDS", "900"))

        # Límite de registros por hora desde una misma IP.
        self.registration_max_attempts: int = int(os.getenv("REGISTRATION_MAX_ATTEMPTS", "20"))
        self.registration_window_seconds: int = int(os.getenv("REGISTRATION_WINDOW_SECONDS", "3600"))

    @property
    def primary_corporate_domain(self) -> str:
        return self.corporate_email_domains[0]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()

# Valores por defecto visibles en la interfaz.
MIN_PASSWORD_LENGTH = 8
