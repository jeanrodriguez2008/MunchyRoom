"""Plantillas Jinja2 y utilidades de renderizado (flash, filtros, contexto común)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings
from app.constants import (
    DURATION_OPTIONS,
    ROLE_DESCRIPTIONS,
    ROLE_LABELS,
    ROLE_SHORT,
    STATUS_META,
    Role,
    ReservationStatus,
    status_label,
)
from app.formatting import (
    fmt_date_long,
    fmt_date_medium,
    fmt_date_short,
    fmt_datetime,
    fmt_duration,
    fmt_time,
    fmt_time_range,
    fmt_weekday,
    pluralize,
)
from app.timeutils import now_caracas, today_caracas

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Filtros disponibles en todas las plantillas.
templates.env.filters.update(
    {
        "date_long": fmt_date_long,
        "date_medium": fmt_date_medium,
        "date_short": fmt_date_short,
        "datetime_local": fmt_datetime,
        "time12": fmt_time,
        "time_range": fmt_time_range,
        "duration": fmt_duration,
        "weekday": fmt_weekday,
        "pluralize": pluralize,
    }
)

# Funciones/constantes globales.
templates.env.globals.update(
    app_name=settings.app_name,
    company_name=settings.company_name,
    Role=Role,
    ReservationStatus=ReservationStatus,
    STATUS_META=STATUS_META,
    ROLE_LABELS=ROLE_LABELS,
    ROLE_DESCRIPTIONS=ROLE_DESCRIPTIONS,
    ROLE_SHORT=ROLE_SHORT,
    DURATION_OPTIONS=DURATION_OPTIONS,
    status_label=status_label,
    status_meta=lambda status: STATUS_META.get(status, {}),
    now_caracas=now_caracas,
    today_caracas=today_caracas,
)


def flash(request: Request, message: str, category: str = "success") -> None:
    """Guarda un mensaje flash en la sesión (se muestra en la siguiente página)."""
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def pop_flashes(request: Request) -> list[dict[str, str]]:
    return request.session.pop("_flashes", []) or []


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
):
    """Renderiza una plantilla inyectando el contexto común de la aplicación."""
    ctx: dict[str, Any] = {
        "user": getattr(request.state, "user", None),
        "flashes": pop_flashes(request),
        "today": today_caracas(),
        "now": now_caracas(),
        "current_path": request.url.path,
        "query_params": dict(request.query_params),
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(
        request=request, name=template_name, context=ctx, status_code=status_code
    )
