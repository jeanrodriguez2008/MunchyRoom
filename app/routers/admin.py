"""Panel de administración: solicitudes, salas, usuarios y cargos."""

from __future__ import annotations

import math
from datetime import date as date_cls

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.constants import ROLE_LABELS, ReservationStatus, Role
from app.database import get_db
from app.dependencies import require_roles
from app.models import MeetingRoom, Position, Reservation, User, UserRole
from app.security import hash_password, is_valid_email, normalize_phone
from app.services.reservations import (
    BusinessRuleError,
    reject_by_admin,
    reassign_authorizer,
    send_to_authorizer,
)
from app.templating import flash, render
from app.timeutils import today_caracas

router = APIRouter(prefix="/admin", tags=["Administración"])

PAGE_SIZE = 15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _active_authorizers(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_name == Role.AUTHORIZER, User.is_active.is_(True))
            .order_by(User.full_name)
            .distinct()
        ).all()
    )


def _departments(db: Session) -> list[str]:
    rows = db.scalars(
        select(User.department).where(User.department != "").distinct().order_by(User.department)
    ).all()
    return [row for row in rows if row]


def _positions(db: Session) -> list[Position]:
    return list(
        db.scalars(
            select(Position).where(Position.is_active.is_(True)).order_by(Position.hierarchy_level.desc(), Position.name)
        ).all()
    )


def _active_admin_count(db: Session) -> int:
    return (
        db.scalar(
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.role_name == Role.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


def _user_form_context(db: Session, form_data: dict, target: User | None = None) -> dict:
    return {
        "form_data": form_data,
        "target": target,
        "positions": _positions(db),
        "departments": _departments(db),
        "all_roles": [(role, ROLE_LABELS[role]) for role in Role.ALL],
    }


def _user_form_data_from(user: User) -> dict:
    return {
        "full_name": user.full_name,
        "email": user.email,
        "phone_whatsapp": user.phone_whatsapp,
        "department": user.department,
        "position_id": str(user.position_id) if user.position_id else "",
        "position_title": user.position_title,
        "roles": list(user.role_names),
        "is_active": user.is_active,
    }


def _validate_user_payload(
    db: Session,
    *,
    current_id: int | None,
    full_name: str,
    email: str,
    phone_whatsapp: str,
    department: str,
    position_id: str,
    position_title: str,
    roles: list[str] | None,
) -> tuple[dict | None, str | None]:
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    department = (department or "").strip()

    if len(full_name) < 3:
        return None, "Escribe el nombre completo del usuario."
    if not is_valid_email(email):
        return None, "El correo electrónico no es válido."

    duplicate = db.scalar(
        select(User).where(User.email == email, User.id != (current_id or 0))
    )
    if duplicate:
        return None, "Ya existe un usuario registrado con ese correo."

    raw_phone = (phone_whatsapp or "").strip()
    phone = ""
    if raw_phone:
        phone = normalize_phone(raw_phone)
        if not phone:
            return None, "El teléfono debe tener formato internacional, por ejemplo +584121234567."

    valid_roles = [role for role in (roles or []) if role in Role.ALL]
    if not valid_roles:
        return None, "Asigna al menos un rol al usuario."

    position = None
    if position_id:
        try:
            position = db.get(Position, int(position_id))
        except (TypeError, ValueError):
            position = None
        if position is None:
            return None, "El cargo seleccionado no existe."
        position_title = position.name

    return (
        {
            "full_name": full_name,
            "email": email,
            "phone_whatsapp": phone,
            "department": department,
            "position": position,
            "position_title": (position_title or "").strip(),
            "roles": valid_roles,
        },
        None,
    )


def _sync_roles(user: User, role_names: list[str]) -> None:
    existing = {role.role_name: role for role in user.roles}
    for role_name in role_names:
        if role_name not in existing:
            user.roles.append(UserRole(role_name=role_name))
    for role_name, row in existing.items():
        if role_name not in role_names:
            user.roles.remove(row)


# ---------------------------------------------------------------------------
# Solicitudes
# ---------------------------------------------------------------------------
@router.get("", name="admin_home")
def admin_home(user: User = Depends(require_roles(Role.ADMIN))):
    return RedirectResponse("/admin/requests", status_code=303)


@router.get("/requests", name="admin_requests")
def admin_requests(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    status: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
):
    q = q.strip()
    stmt = select(Reservation)
    count_stmt = select(func.count(func.distinct(Reservation.id))).select_from(Reservation)

    if q:
        stmt = stmt.join(User, User.id == Reservation.requester_id)
        count_stmt = count_stmt.join(User, User.id == Reservation.requester_id)

    filters = []
    if status in ReservationStatus.ALL:
        filters.append(Reservation.status == status)
    if q:
        filters.append(
            or_(
                Reservation.purpose.ilike(f"%{q}%"),
                User.full_name.ilike(f"%{q}%"),
                User.email.ilike(f"%{q}%"),
            )
        )
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = db.scalar(count_stmt) or 0
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, pages)
    reservations = list(
        db.scalars(
            stmt.order_by(Reservation.created_at.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        ).all()
    )

    return render(
        request,
        "admin/requests.html",
        {
            "user": admin,
            "reservations": reservations,
            "selected_status": status,
            "q": q,
            "page": page,
            "pages": pages,
            "total": total,
            "authorizers": _active_authorizers(db),
        },
    )


@router.post("/requests/{reservation_id}/send", name="admin_send_to_authorizer")
def admin_send_to_authorizer(
    request: Request,
    reservation_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    authorizer_id: str = Form(...),
    note: str = Form(""),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe.")
    try:
        authorizer = db.get(User, int(authorizer_id))
    except (TypeError, ValueError):
        authorizer = None
    if authorizer is None:
        flash(request, "Selecciona un jefe autorizador válido.", "error")
        return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)

    try:
        send_to_authorizer(db, reservation=reservation, admin=admin, authorizer=authorizer, note=note)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, f"Solicitud enviada a {authorizer.full_name} para autorización final.", "success")
    return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)


@router.post("/requests/{reservation_id}/reassign", name="admin_reassign_authorizer")
def admin_reassign_authorizer(
    request: Request,
    reservation_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    authorizer_id: str = Form(...),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe.")
    try:
        authorizer = db.get(User, int(authorizer_id))
    except (TypeError, ValueError):
        authorizer = None
    if authorizer is None:
        flash(request, "Selecciona un jefe autorizador válido.", "error")
        return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)

    try:
        reassign_authorizer(reservation, authorizer)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, f"Solicitud reasignada a {authorizer.full_name}.", "success")
    return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)


@router.post("/requests/{reservation_id}/reject", name="admin_reject_request")
def admin_reject_request(
    request: Request,
    reservation_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    reason: str = Form(""),
):
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="La solicitud no existe.")
    try:
        reject_by_admin(reservation, admin=admin, reason=reason)
    except BusinessRuleError as exc:
        flash(request, exc.message, "error")
    else:
        flash(request, "La solicitud fue rechazada.", "success")
    return RedirectResponse(f"/reservations/{reservation.id}", status_code=303)


# ---------------------------------------------------------------------------
# Salas
# ---------------------------------------------------------------------------
@router.get("/rooms", name="admin_rooms")
def admin_rooms(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    rooms = list(db.scalars(select(MeetingRoom).order_by(MeetingRoom.name)).all())
    return render(request, "admin/rooms.html", {"user": admin, "rooms": rooms})


@router.get("/rooms/new", name="admin_room_new")
def admin_room_new(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
):
    return render(
        request,
        "admin/room_form.html",
        {
            "user": admin,
            "room": None,
            "form_data": {"name": "", "location": "", "capacity": "8", "equipment": "", "is_active": True},
        },
    )


@router.post("/rooms", name="admin_room_create")
def admin_room_create(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    name: str = Form(""),
    location: str = Form(""),
    capacity: str = Form("8"),
    equipment: str = Form(""),
    is_active: str | None = Form(None),
):
    form_data = {
        "name": name,
        "location": location,
        "capacity": capacity,
        "equipment": equipment,
        "is_active": is_active is not None,
    }
    name = name.strip()
    try:
        capacity_value = int(capacity)
    except (TypeError, ValueError):
        capacity_value = 0

    error = None
    if len(name) < 2:
        error = "Escribe el nombre de la sala."
    elif capacity_value < 1 or capacity_value > 200:
        error = "La capacidad debe estar entre 1 y 200 personas."
    elif db.scalar(select(MeetingRoom).where(func.lower(MeetingRoom.name) == name.lower())):
        error = "Ya existe una sala con ese nombre."

    if error:
        flash(request, error, "error")
        return render(request, "admin/room_form.html", {"user": admin, "room": None, "form_data": form_data}, status_code=400)

    db.add(
        MeetingRoom(
            name=name,
            location=location.strip(),
            capacity=capacity_value,
            equipment=equipment.strip(),
            is_active=is_active is not None,
        )
    )
    flash(request, f"Sala «{name}» creada correctamente.", "success")
    return RedirectResponse("/admin/rooms", status_code=303)


@router.get("/rooms/{room_id}/edit", name="admin_room_edit")
def admin_room_edit(
    request: Request,
    room_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    room = db.get(MeetingRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="La sala no existe.")
    return render(
        request,
        "admin/room_form.html",
        {
            "user": admin,
            "room": room,
            "form_data": {
                "name": room.name,
                "location": room.location,
                "capacity": str(room.capacity),
                "equipment": room.equipment,
                "is_active": room.is_active,
            },
        },
    )


@router.post("/rooms/{room_id}", name="admin_room_update")
def admin_room_update(
    request: Request,
    room_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    name: str = Form(""),
    location: str = Form(""),
    capacity: str = Form("8"),
    equipment: str = Form(""),
    is_active: str | None = Form(None),
):
    room = db.get(MeetingRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="La sala no existe.")

    form_data = {
        "name": name,
        "location": location,
        "capacity": capacity,
        "equipment": equipment,
        "is_active": is_active is not None,
    }
    name = name.strip()
    try:
        capacity_value = int(capacity)
    except (TypeError, ValueError):
        capacity_value = 0

    error = None
    if len(name) < 2:
        error = "Escribe el nombre de la sala."
    elif capacity_value < 1 or capacity_value > 200:
        error = "La capacidad debe estar entre 1 y 200 personas."
    elif db.scalar(
        select(MeetingRoom).where(
            func.lower(MeetingRoom.name) == name.lower(), MeetingRoom.id != room.id
        )
    ):
        error = "Ya existe otra sala con ese nombre."

    if error:
        flash(request, error, "error")
        return render(request, "admin/room_form.html", {"user": admin, "room": room, "form_data": form_data}, status_code=400)

    room.name = name
    room.location = location.strip()
    room.capacity = capacity_value
    room.equipment = equipment.strip()
    room.is_active = is_active is not None
    flash(request, "Sala actualizada correctamente.", "success")
    return RedirectResponse("/admin/rooms", status_code=303)


@router.post("/rooms/{room_id}/toggle", name="admin_room_toggle")
def admin_room_toggle(
    request: Request,
    room_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    room = db.get(MeetingRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="La sala no existe.")
    room.is_active = not room.is_active
    flash(
        request,
        f"Sala «{room.name}» {'activada' if room.is_active else 'desactivada'}.",
        "success",
    )
    return RedirectResponse("/admin/rooms", status_code=303)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
@router.get("/users", name="admin_users")
def admin_users(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    q: str = Query(""),
    role: str = Query(""),
    page: int = Query(1, ge=1),
):
    q = q.strip()
    stmt = select(User)
    count_stmt = select(func.count(func.distinct(User.id))).select_from(User)

    filters = []
    if q:
        filters.append(
            or_(
                User.full_name.ilike(f"%{q}%"),
                User.email.ilike(f"%{q}%"),
                User.department.ilike(f"%{q}%"),
            )
        )
    if role in Role.ALL:
        stmt = stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_name == role)
        count_stmt = count_stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_name == role)
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    total = db.scalar(count_stmt) or 0
    pages = max(1, math.ceil(total / 20))
    page = min(page, pages)
    users = list(
        db.scalars(
            stmt.order_by(User.full_name).offset((page - 1) * 20).limit(20)
        ).all()
    )

    return render(
        request,
        "admin/users.html",
        {
            "user": admin,
            "users": users,
            "q": q,
            "selected_role": role,
            "page": page,
            "pages": pages,
            "total": total,
        },
    )


@router.get("/users/new", name="admin_user_new")
def admin_user_new(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    form_data = {
        "full_name": "",
        "email": "",
        "phone_whatsapp": "",
        "department": "",
        "position_id": "",
        "position_title": "",
        "roles": [Role.PARTICIPANT],
        "is_active": True,
    }
    return render(request, "admin/user_form.html", _user_form_context(db, form_data))


@router.post("/users", name="admin_user_create")
def admin_user_create(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    full_name: str = Form(""),
    email: str = Form(""),
    phone_whatsapp: str = Form(""),
    department: str = Form(""),
    position_id: str = Form(""),
    position_title: str = Form(""),
    roles: list[str] | None = Form(None),
    is_active: str | None = Form(None),
    password: str = Form(""),
):
    form_data = {
        "full_name": full_name,
        "email": email,
        "phone_whatsapp": phone_whatsapp,
        "department": department,
        "position_id": position_id,
        "position_title": position_title,
        "roles": roles or [],
        "is_active": is_active is not None,
    }
    payload, error = _validate_user_payload(
        db,
        current_id=None,
        full_name=full_name,
        email=email,
        phone_whatsapp=phone_whatsapp,
        department=department,
        position_id=position_id,
        position_title=position_title,
        roles=roles,
    )
    if error is None and len(password) < 8:
        error = "La contraseña inicial debe tener al menos 8 caracteres."

    if error or payload is None:
        flash(request, error or "Revisa los datos del usuario.", "error")
        return render(
            request,
            "admin/user_form.html",
            _user_form_context(db, form_data),
            status_code=400,
        )

    user = User(
        full_name=payload["full_name"],
        email=payload["email"],
        password_hash=hash_password(password),
        phone_whatsapp=payload["phone_whatsapp"],
        department=payload["department"],
        position=payload["position"],
        position_title=payload["position_title"],
        is_active=is_active is not None,
        must_change_password=True,
    )
    user.roles = [UserRole(role_name=role) for role in payload["roles"]]
    db.add(user)
    flash(request, f"Usuario {user.full_name} creado correctamente.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", name="admin_user_edit")
def admin_user_edit(
    request: Request,
    user_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="El usuario no existe.")
    return render(request, "admin/user_form.html", _user_form_context(db, _user_form_data_from(target), target))


@router.post("/users/{user_id}", name="admin_user_update")
def admin_user_update(
    request: Request,
    user_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    full_name: str = Form(""),
    email: str = Form(""),
    phone_whatsapp: str = Form(""),
    department: str = Form(""),
    position_id: str = Form(""),
    position_title: str = Form(""),
    roles: list[str] | None = Form(None),
    is_active: str | None = Form(None),
    password: str = Form(""),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="El usuario no existe.")

    form_data = {
        "full_name": full_name,
        "email": email,
        "phone_whatsapp": phone_whatsapp,
        "department": department,
        "position_id": position_id,
        "position_title": position_title,
        "roles": roles or [],
        "is_active": is_active is not None,
    }
    payload, error = _validate_user_payload(
        db,
        current_id=target.id,
        full_name=full_name,
        email=email,
        phone_whatsapp=phone_whatsapp,
        department=department,
        position_id=position_id,
        position_title=position_title,
        roles=roles,
    )

    active = is_active is not None
    if error is None:
        if target.id == admin.id and not active:
            error = "No puedes desactivar tu propio usuario."
        elif target.id == admin.id and Role.ADMIN not in (roles or []):
            error = "No puedes quitarte a ti mismo el rol de administrador."
        elif (
            target.is_admin
            and target.is_active
            and (not active or Role.ADMIN not in (roles or []))
            and _active_admin_count(db) <= 1
        ):
            error = "Debe existir al menos un administrador activo en el sistema."
    if error is None and password and len(password) < 8:
        error = "La nueva contraseña debe tener al menos 8 caracteres."

    if error or payload is None:
        flash(request, error or "Revisa los datos del usuario.", "error")
        return render(
            request,
            "admin/user_form.html",
            _user_form_context(db, form_data, target),
            status_code=400,
        )

    target.full_name = payload["full_name"]
    target.email = payload["email"]
    target.phone_whatsapp = payload["phone_whatsapp"]
    target.department = payload["department"]
    target.position = payload["position"]
    target.position_title = payload["position_title"]
    target.is_active = active
    if password:
        target.password_hash = hash_password(password)
        target.must_change_password = False
    _sync_roles(target, payload["roles"])

    flash(request, "Usuario actualizado correctamente.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle", name="admin_user_toggle")
def admin_user_toggle(
    request: Request,
    user_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="El usuario no existe.")
    if target.id == admin.id:
        flash(request, "No puedes desactivar tu propio usuario.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if target.is_active and target.is_admin and _active_admin_count(db) <= 1:
        flash(request, "Debe existir al menos un administrador activo.", "error")
        return RedirectResponse("/admin/users", status_code=303)

    target.is_active = not target.is_active
    flash(
        request,
        f"Usuario {target.full_name} {'activado' if target.is_active else 'desactivado'}.",
        "success",
    )
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Catálogo de cargos
# ---------------------------------------------------------------------------
@router.get("/positions", name="admin_positions")
def admin_positions(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    positions = list(
        db.scalars(select(Position).order_by(Position.hierarchy_level.desc(), Position.name)).all()
    )
    return render(request, "admin/positions.html", {"user": admin, "positions": positions})


@router.post("/positions", name="admin_position_create")
def admin_position_create(
    request: Request,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    name: str = Form(""),
    hierarchy_level: str = Form("1"),
):
    name = name.strip()
    try:
        level = int(hierarchy_level)
    except (TypeError, ValueError):
        level = 0

    if len(name) < 2:
        flash(request, "Escribe el nombre del cargo.", "error")
    elif level < 1 or level > 10:
        flash(request, "El nivel jerárquico debe estar entre 1 y 10.", "error")
    elif db.scalar(select(Position).where(func.lower(Position.name) == name.lower())):
        flash(request, "Ya existe un cargo con ese nombre.", "error")
    else:
        db.add(Position(name=name, hierarchy_level=level))
        flash(request, f"Cargo «{name}» creado.", "success")
    return RedirectResponse("/admin/positions", status_code=303)


@router.post("/positions/{position_id}", name="admin_position_update")
def admin_position_update(
    request: Request,
    position_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
    name: str = Form(""),
    hierarchy_level: str = Form("1"),
):
    position = db.get(Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="El cargo no existe.")

    name = name.strip()
    try:
        level = int(hierarchy_level)
    except (TypeError, ValueError):
        level = 0

    if len(name) < 2:
        flash(request, "Escribe el nombre del cargo.", "error")
    elif level < 1 or level > 10:
        flash(request, "El nivel jerárquico debe estar entre 1 y 10.", "error")
    elif db.scalar(
        select(Position).where(func.lower(Position.name) == name.lower(), Position.id != position.id)
    ):
        flash(request, "Ya existe otro cargo con ese nombre.", "error")
    else:
        position.name = name
        position.hierarchy_level = level
        # Mantiene sincronizado el cargo mostrado en los usuarios.
        for linked_user in db.scalars(select(User).where(User.position_id == position.id)).all():
            linked_user.position_title = name
        flash(request, "Cargo actualizado.", "success")
    return RedirectResponse("/admin/positions", status_code=303)


@router.post("/positions/{position_id}/toggle", name="admin_position_toggle")
def admin_position_toggle(
    request: Request,
    position_id: int,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    position = db.get(Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="El cargo no existe.")
    position.is_active = not position.is_active
    flash(
        request,
        f"Cargo «{position.name}» {'activado' if position.is_active else 'desactivado'}.",
        "success",
    )
    return RedirectResponse("/admin/positions", status_code=303)
