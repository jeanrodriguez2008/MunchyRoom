"""Utilidades de fecha y hora bajo la zona horaria de Venezuela.

Toda la lógica de negocio (solapamientos, regla de 24 horas, calendario) se
calcula con ``America/Caracas`` (UTC-4, sin horario de verano).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

CARACAS_TZ = ZoneInfo("America/Caracas")
UTC = timezone.utc


def now_caracas() -> datetime:
    """Fecha/hora actual en Caracas (con tzinfo)."""
    return datetime.now(CARACAS_TZ)


def today_caracas() -> date:
    return now_caracas().date()


def utc_now() -> datetime:
    """Timestamp UTC para auditoría en base de datos."""
    return datetime.now(UTC)


def combine_caracas(day: date, hour: time) -> datetime:
    """Combina fecha + hora locales de Caracas en un datetime con tzinfo."""
    return datetime.combine(day, hour).replace(tzinfo=CARACAS_TZ)


def to_caracas(value: datetime | None) -> datetime | None:
    """Convierte un datetime (normalmente UTC de la BD) a hora de Caracas."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(CARACAS_TZ)


def add_minutes(start: time, minutes: int) -> time:
    """Suma minutos a una hora, sin permitir que cruce la medianoche.

    Lanza ``ValueError`` si el resultado cae en el día siguiente (una reserva
    debe iniciar y terminar el mismo día).
    """
    anchor = datetime(2000, 1, 1, start.hour, start.minute)
    result = anchor + timedelta(minutes=minutes)
    if result.date() != anchor.date():
        raise ValueError("La reunión no puede finalizar después de la medianoche.")
    return result.time().replace(second=0, microsecond=0)


def minutes_since_midnight(value: time) -> int:
    return value.hour * 60 + value.minute


def hours_until(day: date, start: time, reference: datetime | None = None) -> float:
    """Horas restantes hasta el inicio de la reunión (puede ser negativo)."""
    reference = reference or now_caracas()
    target = combine_caracas(day, start)
    return (target - reference).total_seconds() / 3600


def can_cancel_by_time(day: date, start: time, reference: datetime | None = None) -> bool:
    """True solo si faltan MÁS de 24 horas para el inicio."""
    return hours_until(day, start, reference) > 24


def start_of_week(day: date) -> date:
    """Lunes de la semana de ``day``."""
    return day - timedelta(days=day.weekday())


def week_days(day: date) -> list[date]:
    monday = start_of_week(day)
    return [monday + timedelta(days=i) for i in range(7)]
