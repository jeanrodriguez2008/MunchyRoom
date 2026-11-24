"""Script CLI de inicialización de la base de datos.

Uso:
    python seed.py

Crea las tablas (si no existen), las 3 salas iniciales, el catálogo de cargos y
el administrador admin@munchy.com. Es idempotente: puede ejecutarse varias veces.
"""

from __future__ import annotations

import sys

from app import models  # noqa: F401  (registra las tablas)
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.seed import seed_database


def main() -> int:
    print("MunchyRoom · inicialización de base de datos")
    print(f"Motor: {'SQLite' if settings.is_sqlite else 'PostgreSQL'}")
    if settings.is_sqlite:
        print(f"Archivo: {settings.database_url}")
    else:
        host = settings.database_url.split("@")[-1].split("/")[0]
        print(f"Servidor: {host}")

    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            summary = seed_database(db)
    except Exception as exc:
        print(f"\n[ERROR] No se pudo inicializar la base de datos: {exc}", file=sys.stderr)
        print("Verifica DATABASE_URL y la conectividad con Neon Tech.", file=sys.stderr)
        return 1

    print("\n[OK] Base de datos inicializada.")
    print(f"  Salas creadas:    {summary['rooms']}")
    print(f"  Cargos creados:   {summary['positions']}")
    print(f"  Admin creado:     {summary['admin']}")
    print(f"\n  Usuario:          {settings.seed_admin_email}")
    print(f"  Contraseña:       {settings.seed_admin_password}")
    print("  (El sistema pedirá cambiarla en el primer ingreso).")
    print("\nSiguiente paso: uvicorn app.main:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
