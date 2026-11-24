"""Dependencias de autenticación y autorización por roles."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    """Se lanza cuando se accede a una ruta privada sin sesión válida."""


class Forbidden(Exception):
    """Se lanza cuando el usuario no tiene el rol requerido."""

    def __init__(self, message: str = "No tienes permisos para acceder a esta sección.") -> None:
        self.message = message
        super().__init__(message)


class PasswordChangeRequired(Exception):
    """El usuario debe cambiar la contraseña antes de continuar."""


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Obtiene el usuario autenticado desde la cookie de sesión.

    Verifica que exista, esté activo y que no tenga pendiente el cambio de
    contraseña obligatorio.
    """
    user_id = request.session.get("uid")
    if not user_id:
        raise LoginRequired()

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        request.session.clear()
        raise LoginRequired()

    request.state.user = user

    if user.must_change_password and not request.url.path.startswith("/auth/"):
        raise PasswordChangeRequired()

    return user


def require_roles(*roles: str) -> Callable[..., User]:
    """Fábrica de dependencias: exige al menos uno de los roles indicados."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not user.has_any_role(*roles):
            raise Forbidden()
        return user

    return dependency
