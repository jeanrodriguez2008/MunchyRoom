"""Seed idempotente de MunchyRoom.

Al arrancar por primera vez (o al ejecutar ``python seed.py``) garantiza:
- 3 salas corporativas de Alimentos Munchy.
- Catálogo inicial de cargos con jerarquía.
- Usuario administrador inicial (admin@munchy.com).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import MeetingRoom, Position, User, UserRole
from app.security import hash_password
from app.constants import Role

DEFAULT_ROOMS = [
    {
        "name": "Sala Azul",
        "location": "Sede Principal · Piso 3",
        "capacity": 12,
        "equipment": "Videobeam, Pantalla TV 65\", Videoconferencia, Pizarra acrílica, Wi-Fi",
        "is_active": True,
    },
    {
        "name": "Sala Roja",
        "location": "Sede Principal · Piso 2",
        "capacity": 8,
        "equipment": "Pantalla TV 55\", Videoconferencia, Pizarra acrílica, Wi-Fi",
        "is_active": True,
    },
    {
        "name": "Sala Blanca",
        "location": "Sede Principal · Piso 1",
        "capacity": 6,
        "equipment": "Pantalla TV 43\", Wi-Fi, Teléfono de conferencia",
        "is_active": True,
    },
]

DEFAULT_POSITIONS = [
    ("Gerente General", 5),
    ("Gerente de Área", 4),
    ("Jefe de Departamento", 3),
    ("Coordinador", 2),
    ("Analista", 1),
    ("Asistente Administrativo", 1),
]


def seed_database(db: Session) -> dict[str, int]:
    """Crea los registros base si no existen. Devuelve un resumen."""
    summary = {"rooms": 0, "positions": 0, "admin": 0}

    # --- Salas -------------------------------------------------------------
    existing_room_names = set(db.scalars(select(MeetingRoom.name)).all())
    for data in DEFAULT_ROOMS:
        if data["name"] not in existing_room_names:
            db.add(MeetingRoom(**data))
            summary["rooms"] += 1

    # --- Cargos ------------------------------------------------------------
    existing_positions = set(db.scalars(select(Position.name)).all())
    for name, level in DEFAULT_POSITIONS:
        if name not in existing_positions:
            db.add(Position(name=name, hierarchy_level=level))
            summary["positions"] += 1

    # --- Administrador inicial --------------------------------------------
    admin = db.scalar(select(User).where(User.email == settings.seed_admin_email.lower()))
    if admin is None:
        admin = User(
            full_name=settings.seed_admin_name,
            email=settings.seed_admin_email.lower(),
            password_hash=hash_password(settings.seed_admin_password),
            phone_whatsapp="",
            department="Tecnología / Administración",
            position_title="Administrador de Aplicación",
            is_active=True,
            must_change_password=True,
        )
        admin.roles = [
            UserRole(role_name=Role.ADMIN),
            UserRole(role_name=Role.REQUESTER),
        ]
        db.add(admin)
        summary["admin"] = 1

    db.commit()
    return summary


def ensure_general_roles(db: Session) -> None:
    """Respaldo: asegura que el admin sembrado conserve sus roles."""
    admin = db.scalar(select(User).where(User.email == settings.seed_admin_email.lower()))
    if admin and not admin.has_role(Role.ADMIN):
        db.add(UserRole(user_id=admin.id, role_name=Role.ADMIN))
        db.commit()
