"""Modelos de datos (PostgreSQL / SQLAlchemy 2.0).

Tablas: users, user_roles, user_security_answers, positions, meeting_rooms,
reservations, reservation_participants.

Reglas de integridad relevantes:
- email único por usuario.
- un usuario no puede repetir el mismo rol (UNIQUE user_id + role_name).
- un usuario no puede repetir la misma pregunta de seguridad.
- un participante no puede repetirse dentro de la misma reserva.
- índice compuesto para consultas de solapamiento por sala/fecha/estado.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import (
    CANCELLATION_MIN_HOURS,
    ROLE_LABELS,
    SECURITY_QUESTIONS_REQUIRED,
    Role,
    ReservationStatus,
    STATUS_META,
)
from app.database import Base
from app.timeutils import combine_caracas, hours_until, utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_whatsapp: Mapped[str] = mapped_column(String(25), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    position_title: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    position: Mapped["Position | None"] = relationship(lazy="joined")
    security_answers: Mapped[list["UserSecurityAnswer"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="UserSecurityAnswer.id",
    )

    def has_role(self, role_name: str) -> bool:
        return any(role.role_name == role_name for role in self.roles)

    def has_any_role(self, *role_names: str) -> bool:
        wanted = set(role_names)
        return any(role.role_name in wanted for role in self.roles)

    @property
    def role_names(self) -> list[str]:
        return [role.role_name for role in self.roles]

    @property
    def role_labels(self) -> list[str]:
        return [ROLE_LABELS.get(role.role_name, role.role_name) for role in self.roles]

    @property
    def is_admin(self) -> bool:
        return self.has_role(Role.ADMIN)

    @property
    def has_security_questions(self) -> bool:
        return len(self.security_answers) >= SECURITY_QUESTIONS_REQUIRED

    @property
    def is_pending_roles(self) -> bool:
        """Un autorregistro queda pendiente hasta que un administrador asigne roles."""
        return not self.roles

    @property
    def initials(self) -> str:
        parts = [part for part in (self.full_name or "").split() if part]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def __repr__(self) -> str:  # pragma: no cover - solo depuración
        return f"<User {self.email}>"


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_name", name="uq_user_roles_user_role"),
        CheckConstraint(
            "role_name IN ('admin', 'solicitante', 'autorizador', 'participante')",
            name="ck_user_roles_role_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_name: Mapped[str] = mapped_column(String(20), nullable=False)

    user: Mapped[User] = relationship(back_populates="roles")


class UserSecurityAnswer(Base):
    """Respuestas de seguridad (hasheadas) para recuperar la contraseña.

    Las respuestas nunca se almacenan en texto plano. La normalización y el
    hash se realizan en ``app.security`` para compararlas sin distinguir
    mayúsculas, tildes ni signos.
    """

    __tablename__ = "user_security_answers"
    __table_args__ = (
        UniqueConstraint("user_id", "question_key", name="uq_user_security_answers_user_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(40), nullable=False)
    answer_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="security_answers")


class Position(Base):
    """Catálogo de cargos y su nivel jerárquico."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("name", name="uq_positions_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hierarchy_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class MeetingRoom(Base):
    __tablename__ = "meeting_rooms"
    __table_args__ = (UniqueConstraint("name", name="uq_meeting_rooms_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    equipment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="room")

    @property
    def equipment_items(self) -> list[str]:
        return [item.strip() for item in (self.equipment or "").split(",") if item.strip()]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MeetingRoom {self.name}>"


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("ix_reservations_room_date_status", "room_id", "meeting_date", "status"),
        Index("ix_reservations_requester_date", "requester_id", "meeting_date"),
        CheckConstraint("duration_minutes > 0", name="ck_reservations_duration_positive"),
        CheckConstraint("end_time > start_time", name="ck_reservations_time_order"),
        CheckConstraint(
            "status IN ('PENDIENTE_ADMIN', 'PENDIENTE_AUTORIZADOR', 'AUTORIZADA', 'RECHAZADA', 'CANCELADA')",
            name="ck_reservations_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("meeting_rooms.id"), index=True, nullable=False)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    admin_validator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    authorizer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expected_participants_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=ReservationStatus.PENDING_ADMIN, nullable=False)

    admin_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rejection_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    authorizer_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    room: Mapped[MeetingRoom] = relationship(back_populates="reservations", lazy="joined")
    requester: Mapped[User] = relationship(foreign_keys=[requester_id], lazy="joined")
    admin_validator: Mapped[User | None] = relationship(foreign_keys=[admin_validator_id], lazy="joined")
    authorizer: Mapped[User | None] = relationship(foreign_keys=[authorizer_id], lazy="joined")
    cancelled_by: Mapped[User | None] = relationship(foreign_keys=[cancelled_by_id], lazy="joined")
    participants: Mapped[list["ReservationParticipant"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan", lazy="selectin"
    )

    # ------------------------------------------------------------------
    # Propiedades de negocio
    # ------------------------------------------------------------------
    @property
    def start_datetime(self) -> datetime:
        return combine_caracas(self.meeting_date, self.start_time)

    @property
    def end_datetime(self) -> datetime:
        return combine_caracas(self.meeting_date, self.end_time)

    @property
    def status_label(self) -> str:
        return STATUS_META.get(self.status, {}).get("label", self.status)

    @property
    def status_short(self) -> str:
        return STATUS_META.get(self.status, {}).get("short", self.status)

    @property
    def status_meta(self) -> dict:
        return STATUS_META.get(self.status, {})

    @property
    def hours_until_start(self) -> float:
        return hours_until(self.meeting_date, self.start_time)

    @property
    def can_be_cancelled(self) -> bool:
        """Regla de negocio: solo con MÁS de 24 horas de anticipación y estado abierto."""
        if self.status not in ReservationStatus.CANCELLABLE:
            return False
        return self.hours_until_start > CANCELLATION_MIN_HOURS

    @property
    def participants_notified_count(self) -> int:
        return sum(1 for p in self.participants if p.whatsapp_notified)

    @property
    def participant_users(self) -> list[User]:
        return [p.user for p in self.participants if p.user is not None]

    def user_can_view(self, user: User | None) -> bool:
        if user is None:
            return False
        if user.is_admin:
            return True
        if self.requester_id == user.id:
            return True
        if self.authorizer_id == user.id:
            return True
        return any(p.user_id == user.id for p in self.participants)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Reservation {self.id} room={self.room_id} {self.meeting_date} {self.start_time}>"


class ReservationParticipant(Base):
    __tablename__ = "reservation_participants"
    __table_args__ = (
        UniqueConstraint("reservation_id", "user_id", name="uq_reservation_participants"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    whatsapp_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reservation: Mapped[Reservation] = relationship(back_populates="participants")
    user: Mapped[User] = relationship(lazy="joined")
