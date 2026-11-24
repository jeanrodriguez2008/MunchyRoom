"""Catálogo de apoyo para departamentos.

No existe una tabla de departamentos: se combinan los valores ya usados por
los usuarios con una lista base, para ofrecer sugerencias consistentes sin
impedir que se registre un departamento nuevo.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import DEFAULT_DEPARTMENTS
from app.models import User


def department_options(db: Session) -> list[str]:
    """Devuelve los departamentos sugeridos, ordenados alfabéticamente."""
    stored = db.scalars(
        select(User.department).where(User.department != "").distinct()
    ).all()
    options = {value.strip() for value in stored if value and value.strip()}
    options.update(DEFAULT_DEPARTMENTS)
    return sorted(options, key=str.casefold)
