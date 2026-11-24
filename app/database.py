"""Motor y sesiones de base de datos.

- PostgreSQL (Neon Tech) en producción con ``sslmode=require``.
- SQLite como respaldo local/pruebas (misma lógica de negocio).
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    """Clase base declarativa de todos los modelos."""


def _build_engine():
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if settings.is_sqlite:
        # SQLite en memoria (pruebas) requiere StaticPool para compartir conexión.
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in settings.database_url:
            kwargs["poolclass"] = StaticPool
    else:
        # Neon cierra conexiones inactivas: pool_pre_ping + reciclaje evitan
        # errores "server closed the connection unexpectedly".
        kwargs.update({"pool_size": 5, "max_overflow": 5, "pool_recycle": 280, "pool_timeout": 30})
    return create_engine(settings.database_url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: abre una sesión y hace commit al finalizar.

    Si la petición lanza una excepción se revierte la transacción completa.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
