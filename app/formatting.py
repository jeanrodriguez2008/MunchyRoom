"""Formateo de fechas, horas y textos en español (zona horaria de Caracas)."""

from __future__ import annotations

from datetime import date, datetime, time

from app.timeutils import to_caracas

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fmt_date_long(value: date | None) -> str:
    if value is None:
        return ""
    text = f"{DIAS[value.weekday()]} {value.day} de {MESES[value.month - 1]} de {value.year}"
    return text.capitalize()


def fmt_date_medium(value: date | None) -> str:
    if value is None:
        return ""
    return f"{DIAS_CORTOS[value.weekday()]} {value.day} {MESES_CORTOS[value.month - 1]} {value.year}"


def fmt_date_short(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value.day:02d}/{value.month:02d}/{value.year}"


def fmt_weekday(value: date | None) -> str:
    if value is None:
        return ""
    return f"{DIAS[value.weekday()].capitalize()} {value.day}"


def fmt_time(value: time | None) -> str:
    """Hora en formato 12 h: '7:00 AM'."""
    if value is None:
        return ""
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def fmt_time_range(start: time | None, end: time | None) -> str:
    return f"{fmt_time(start)} – {fmt_time(end)}"


def fmt_duration(minutes: int | None) -> str:
    if not minutes:
        return ""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h" if hours > 1 else "1 hora"
    return f"{mins} min"


def fmt_datetime(value: datetime | None, with_time: bool = True) -> str:
    if value is None:
        return ""
    local = to_caracas(value)
    base = fmt_date_medium(local.date())
    if not with_time:
        return base
    return f"{base} · {fmt_time(local.time())}"


def pluralize(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"
