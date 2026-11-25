"""Configuración de pruebas: SQLite en memoria y datos base.

Se define DATABASE_URL antes de importar la app para no tocar Neon Tech.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ENV"] = "test"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SEED_ADMIN_EMAIL"] = "admin@munchy.com"
os.environ["SEED_ADMIN_PASSWORD"] = "MunchyAdmin2026*"

from datetime import date, time, timedelta

import pytest

from app.constants import Role
from app.database import Base, SessionLocal, engine
from app.models import MeetingRoom, User, UserRole
from app.security import hash_password
from app.seed import seed_departments
from app.timeutils import now_caracas


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        seed_departments(session)
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_user(db, email: str, roles: tuple[str, ...], full_name: str | None = None, phone: str = "+584121234567") -> User:
    user = User(
        full_name=full_name or email.split("@")[0].replace(".", " ").title(),
        email=email,
        password_hash=hash_password("Secret123*"),
        phone_whatsapp=phone,
        department="Operaciones",
        position_title="Analista",
        is_active=True,
    )
    user.roles = [UserRole(role_name=role) for role in roles]
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def people(db):
    return {
        "admin": create_user(db, "admin@test.com", (Role.ADMIN, Role.REQUESTER), "Admin Test"),
        "requester": create_user(db, "host@test.com", (Role.REQUESTER, Role.PARTICIPANT), "Host Test"),
        "authorizer": create_user(db, "boss@test.com", (Role.AUTHORIZER, Role.REQUESTER), "Boss Test"),
        "authorizer2": create_user(db, "boss2@test.com", (Role.AUTHORIZER,), "Boss Two"),
        "participant": create_user(db, "guest@test.com", (Role.PARTICIPANT,), "Guest Test", "+584129998877"),
        "participant2": create_user(db, "guest2@test.com", (Role.PARTICIPANT,), "Guest Two", "+584127776655"),
    }


@pytest.fixture()
def room(db):
    meeting_room = MeetingRoom(
        name="Sala Test",
        location="Piso 1",
        capacity=8,
        equipment="TV, Videobeam",
        is_active=True,
    )
    db.add(meeting_room)
    db.commit()
    db.refresh(meeting_room)
    return meeting_room


def future_slot(days: int = 3, hour: int = 10) -> tuple[date, time]:
    target = now_caracas() + timedelta(days=days)
    return target.date(), time(hour=hour, minute=0)
