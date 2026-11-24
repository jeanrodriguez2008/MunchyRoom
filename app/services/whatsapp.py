"""Generación de mensajes y enlaces de WhatsApp para la convocatoria."""

from __future__ import annotations

from urllib.parse import quote

from app.formatting import fmt_date_long, fmt_duration, fmt_time
from app.models import Reservation, User
from app.security import whatsapp_digits


def build_message(reservation: Reservation, participant: User, requester_name: str | None = None) -> str:
    """Plantilla corporativa de convocatoria (formato WhatsApp)."""
    organizer = requester_name or reservation.requester.full_name
    lines = [
        f"Hola {participant.full_name}, te informamos que has sido convocado(a) a una reunión en Alimentos Munchy.",
        "",
        f"📌 *Motivo:* {reservation.purpose}",
        f"🏢 *Sala:* {reservation.room.name}",
        f"📅 *Fecha:* {fmt_date_long(reservation.meeting_date)}",
        (
            f"⏰ *Hora:* {fmt_time(reservation.start_time)} - {fmt_time(reservation.end_time)} "
            f"({fmt_duration(reservation.duration_minutes)})"
        ),
        f"👤 *Organiza:* {organizer}",
    ]
    if reservation.room.location:
        lines.append(f"📍 *Ubicación:* {reservation.room.location}")
    return "\n".join(lines)


def build_generic_message(reservation: Reservation) -> str:
    """Mensaje sin nombre para difusión masiva / copiar y pegar."""
    organizer = reservation.requester.full_name
    lines = [
        "Hola, te informamos que has sido convocado(a) a una reunión en Alimentos Munchy.",
        "",
        f"📌 *Motivo:* {reservation.purpose}",
        f"🏢 *Sala:* {reservation.room.name}",
        f"📅 *Fecha:* {fmt_date_long(reservation.meeting_date)}",
        (
            f"⏰ *Hora:* {fmt_time(reservation.start_time)} - {fmt_time(reservation.end_time)} "
            f"({fmt_duration(reservation.duration_minutes)})"
        ),
        f"👤 *Organiza:* {organizer}",
    ]
    if reservation.room.location:
        lines.append(f"📍 *Ubicación:* {reservation.room.location}")
    return "\n".join(lines)


def build_wa_link(phone: str, message: str) -> str:
    """Enlace wa.me con el mensaje codificado (sin '+' y solo dígitos)."""
    digits = whatsapp_digits(phone)
    return f"https://wa.me/{digits}?text={quote(message, safe='')}"


def build_contact_list(reservation: Reservation) -> str:
    """Lista de números para pegar en una lista de difusión de WhatsApp."""
    blocks = []
    for row in reservation.participants:
        user = row.user
        if user is None:
            continue
        phone = user.phone_whatsapp or "sin teléfono"
        blocks.append(f"{user.full_name} — {phone}")
    return "\n".join(blocks)


def build_share_text(reservation: Reservation, message: str) -> str:
    """Mensaje + números, ideal para copiar y pegar en difusión."""
    return f"{message}\n\n*Invitados:*\n{build_contact_list(reservation)}"
