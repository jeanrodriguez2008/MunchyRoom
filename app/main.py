"""Punto de entrada de MunchyRoom (FastAPI).

- Renderiza vistas Jinja2 con sesiones firmadas.
- Inicializa la base de datos y el seed en el arranque (Neon Tech / PostgreSQL).
- Expone /healthz para el health check de Render y endpoints PWA.
"""

from __future__ import annotations

import logging
import time as time_module
from contextlib import asynccontextmanager
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.config import BASE_DIR, settings
from app.database import Base, SessionLocal, engine
from app.dependencies import Forbidden, LoginRequired, PasswordChangeRequired
from app.routers import admin, api, auth, authorizations, calendar, dashboard, reservations
from app.seed import seed_database, seed_webmaster
from app.templating import render
from app.timeutils import now_caracas

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("munchyroom")


def initialize_database(max_attempts: int = 5) -> None:
    """Crea tablas y ejecuta el seed idempotente.

    Reintenta para tolerar el arranque en frío de Neon Tech.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            with SessionLocal() as db:
                summary = seed_database(db)
                webmaster_created = seed_webmaster(db)
            logger.info(
                "Base de datos lista. Seed: %s salas, %s cargos, %s admin, webmaster nuevo: %s.",
                summary["rooms"],
                summary["positions"],
                summary["admin"],
                webmaster_created,
            )
            return
        except Exception as exc:  # pragma: no cover - depende de la red/Neon
            last_error = exc
            logger.warning("Intento %s/%s de inicializar la BD falló: %s", attempt, max_attempts, exc)
            time_module.sleep(3)

    raise RuntimeError("No se pudo inicializar la base de datos.") from last_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key == "dev-insecure-secret-key-change-me":
        logger.warning("SECRET_KEY insegura en uso. Configura una clave fuerte en producción.")
    initialize_database()
    logger.info(
        "MunchyRoom iniciado · env=%s · tz=%s · db=%s",
        settings.env,
        settings.timezone,
        "sqlite" if settings.is_sqlite else "postgresql",
    )
    yield


app = FastAPI(
    title="MunchyRoom",
    description="Gestión de salas de reuniones de Alimentos Munchy, C.A.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "worker-src 'self'; "
            "manifest-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        if settings.is_production and settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class SameOriginMiddleware(BaseHTTPMiddleware):
    """Defensa CSRF adicional: rechaza POST de orígenes externos."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            source = request.headers.get("origin") or request.headers.get("referer")
            host = request.headers.get("host", "")
            if source and host:
                parsed = urlparse(source)
                if parsed.netloc and parsed.netloc != host:
                    return PlainTextResponse("Origen no permitido.", status_code=403)
        return await call_next(request)


# El orden importa: el último middleware agregado es el más externo.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="munchyroom_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.add_middleware(GZipMiddleware, minimum_size=800)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SameOriginMiddleware)


# ---------------------------------------------------------------------------
# Manejo de errores y redirecciones de autenticación
# ---------------------------------------------------------------------------
@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(f"/auth/login?next={quote(target, safe='')}", status_code=303)


@app.exception_handler(PasswordChangeRequired)
async def password_change_handler(request: Request, exc: PasswordChangeRequired):
    return RedirectResponse("/auth/password", status_code=303)


@app.exception_handler(Forbidden)
async def forbidden_handler(request: Request, exc: Forbidden):
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "*/*" in accept:
        return render(request, "errors/403.html", {"detail": exc.message}, status_code=403)
    return JSONResponse({"detail": exc.message}, status_code=403)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code in (403, 404) and not request.url.path.startswith("/api/"):
        accept = request.headers.get("accept", "")
        # Los navegadores envían text/html; las llamadas internas usan */*.
        if "text/html" in accept or "*/*" in accept:
            return render(
                request,
                f"errors/{exc.status_code}.html",
                {"detail": exc.detail},
                status_code=exc.status_code,
            )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


# ---------------------------------------------------------------------------
# Rutas base / PWA
# ---------------------------------------------------------------------------
@app.get("/healthz", include_in_schema=False)
def healthz():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "up", "time": now_caracas().isoformat()}
    except Exception as exc:  # pragma: no cover
        logger.error("Health check falló: %s", exc)
        return JSONResponse({"status": "error", "database": "down"}, status_code=503)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(
        BASE_DIR / "app" / "static" / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(
        BASE_DIR / "app" / "static" / "icons" / "favicon.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return FileResponse(
        BASE_DIR / "app" / "static" / "icons" / "apple-touch-icon.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon_precomposed():
    return FileResponse(
        BASE_DIR / "app" / "static" / "icons" / "apple-touch-icon.png",
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        BASE_DIR / "app" / "static" / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/offline", include_in_schema=False)
def offline(request: Request):
    return render(request, "offline.html")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(calendar.router)
app.include_router(reservations.router)
app.include_router(authorizations.router)
app.include_router(admin.router)
app.include_router(api.router)
