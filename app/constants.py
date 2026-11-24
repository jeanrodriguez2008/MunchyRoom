"""Constantes de negocio, roles, estados y catálogos de la aplicación."""

from __future__ import annotations


class Role:
    """Roles del sistema. Un usuario puede tener varios simultáneamente."""

    ADMIN = "admin"
    REQUESTER = "solicitante"
    AUTHORIZER = "autorizador"
    PARTICIPANT = "participante"

    ALL = (ADMIN, REQUESTER, AUTHORIZER, PARTICIPANT)


ROLE_LABELS = {
    Role.ADMIN: "Administrador",
    Role.REQUESTER: "Solicitante / Anfitrión",
    Role.AUTHORIZER: "Jefe Autorizador",
    Role.PARTICIPANT: "Participante",
}

ROLE_DESCRIPTIONS = {
    Role.ADMIN: "Configura salas, usuarios y valida las solicitudes de reserva.",
    Role.REQUESTER: "Puede solicitar salas y convocar participantes.",
    Role.AUTHORIZER: "Da la aprobación final de las reservas asignadas.",
    Role.PARTICIPANT: "Puede ser convocado a reuniones y consultar su agenda.",
}

ROLE_SHORT = {
    Role.ADMIN: "Admin",
    Role.REQUESTER: "Solicitante",
    Role.AUTHORIZER: "Autorizador",
    Role.PARTICIPANT: "Participante",
}


class ReservationStatus:
    """Estados del flujo de doble validación."""

    PENDING_ADMIN = "PENDIENTE_ADMIN"
    PENDING_AUTHORIZER = "PENDIENTE_AUTORIZADOR"
    AUTHORIZED = "AUTORIZADA"
    REJECTED = "RECHAZADA"
    CANCELLED = "CANCELADA"

    ALL = (PENDING_ADMIN, PENDING_AUTHORIZER, AUTHORIZED, REJECTED, CANCELLED)
    OPEN = (PENDING_ADMIN, PENDING_AUTHORIZER, AUTHORIZED)

    # Estados que bloquean una sala (regla estricta de solapamiento).
    BLOCKING = (PENDING_AUTHORIZER, AUTHORIZED)

    # Estados que pueden cancelarse (con la regla de 24 horas).
    CANCELLABLE = (PENDING_ADMIN, PENDING_AUTHORIZER, AUTHORIZED)


STATUS_META = {
    ReservationStatus.PENDING_ADMIN: {
        "label": "Pendiente de administración",
        "short": "Pendiente admin",
        "description": "El administrador debe validar la disponibilidad y enviarla al jefe autorizador.",
        "badge": "border-amber-200 bg-amber-50 text-amber-800",
        "dot": "bg-amber-500",
        "block": "border-amber-400 bg-amber-50 text-amber-950 hover:bg-amber-100",
        "soft": "bg-amber-50 text-amber-800",
    },
    ReservationStatus.PENDING_AUTHORIZER: {
        "label": "Pendiente de autorización",
        "short": "Pendiente jefe",
        "description": "Validada por el administrador; espera la decisión final del jefe autorizador.",
        "badge": "border-orange-200 bg-orange-50 text-orange-800",
        "dot": "bg-orange-500",
        "block": "border-orange-400 bg-orange-50 text-orange-950 hover:bg-orange-100",
        "soft": "bg-orange-50 text-orange-800",
    },
    ReservationStatus.AUTHORIZED: {
        "label": "Autorizada",
        "short": "Autorizada",
        "description": "Sala confirmada. El horario queda bloqueado en el calendario.",
        "badge": "border-emerald-200 bg-emerald-50 text-emerald-800",
        "dot": "bg-emerald-500",
        "block": "border-emerald-500 bg-emerald-50 text-emerald-950 hover:bg-emerald-100",
        "soft": "bg-emerald-50 text-emerald-800",
    },
    ReservationStatus.REJECTED: {
        "label": "Rechazada",
        "short": "Rechazada",
        "description": "La solicitud no fue aprobada.",
        "badge": "border-red-200 bg-red-50 text-red-700",
        "dot": "bg-red-500",
        "block": "border-red-300 bg-red-50 text-red-900",
        "soft": "bg-red-50 text-red-700",
    },
    ReservationStatus.CANCELLED: {
        "label": "Cancelada",
        "short": "Cancelada",
        "description": "La reunión fue cancelada y el horario quedó libre.",
        "badge": "border-slate-200 bg-slate-100 text-slate-600",
        "dot": "bg-slate-400",
        "block": "border-slate-300 bg-slate-100 text-slate-600",
        "soft": "bg-slate-100 text-slate-600",
    },
}


def status_label(status: str) -> str:
    return STATUS_META.get(status, {}).get("label", status)


# Duración de reuniones (minutos).
DURATION_OPTIONS = [
    (30, "30 min"),
    (45, "45 min"),
    (60, "1 hora"),
    (90, "1 h 30 min"),
    (120, "2 horas"),
]
MIN_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 480  # 8 horas

# Ventana visible del calendario diario (hora local de Caracas).
CALENDAR_START_HOUR = 7
CALENDAR_END_HOUR = 20
CALENDAR_SLOT_HEIGHT = 64  # píxeles por hora en la vista diaria

# Regla de cancelación.
CANCELLATION_MIN_HOURS = 24
