"""Catálogo de departamentos: consultas y validación."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Department


def all_departments(db: Session) -> list[Department]:
    """Todos los departamentos, activos e inactivos, ordenados por nombre."""
    return list(
        db.scalars(select(Department).order_by(Department.name)).all()
    )


def active_departments(db: Session) -> list[Department]:
    """Departamentos disponibles para nuevas asignaciones."""
    return list(
        db.scalars(
            select(Department)
            .where(Department.is_active.is_(True))
            .order_by(Department.name)
        ).all()
    )


def find_department(db: Session, name: str | None) -> Department | None:
    """Busca un departamento por nombre sin distinguir mayúsculas."""
    value = (name or "").strip()
    if not value:
        return None
    return db.scalar(
        select(Department).where(func.lower(Department.name) == value.lower())
    )
