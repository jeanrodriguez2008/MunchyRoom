"""Pruebas del autorregistro y las preguntas de seguridad."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.constants import Role
from app.models import User, UserSecurityAnswer, WebmasterAccount
from app.security import verify_password
from app.seed import seed_webmaster
from app.services.accounts import (
    AccountError,
    is_corporate_email,
    register_user,
    set_security_answers,
    validate_security_answers,
    verify_security_answers,
)


def registration_payload(**overrides):
    data = {
        "full_name": "Ana Pérez",
        "email": "ana@munchy.com",
        "phone_whatsapp": "+58 412-123 4567",
        "department": "Ventas",
        "password": "ClaveSegura1*",
        "confirm_password": "ClaveSegura1*",
        "question_keys": ["mascota", "ciudad_madre", "escuela"],
        "answers": ["Firulais", "Valencia", "San José"],
    }
    data.update(overrides)
    return data


def test_corporate_email_domain():
    assert is_corporate_email("ana@munchy.com")
    assert is_corporate_email("ana@ventas.munchy.com")
    assert not is_corporate_email("ana@gmail.com")
    assert not is_corporate_email("ana@munchy.com.evil.io")
    assert not is_corporate_email("correo-invalido")


def test_registration_is_pending_until_roles_are_assigned(db):
    user = register_user(db, **registration_payload())
    db.commit()

    stored = db.scalar(select(User).where(User.email == "ana@munchy.com"))
    assert stored is not None
    assert stored.phone_whatsapp == "+584121234567"
    assert stored.is_active is True
    assert stored.is_pending_roles is True
    assert stored.roles == []
    assert stored.has_security_questions is True
    assert stored.must_change_password is False
    assert stored.password_hash != "ClaveSegura1*"

    answers = db.scalars(
        select(UserSecurityAnswer).where(UserSecurityAnswer.user_id == stored.id)
    ).all()
    assert len(answers) == 3
    assert all(answer.answer_hash and "Firulais" not in answer.answer_hash for answer in answers)


def test_registration_rejects_non_corporate_email(db):
    with pytest.raises(AccountError, match="correo corporativo"):
        register_user(db, **registration_payload(email="ana@gmail.com"))


def test_registration_rejects_duplicate_email(db):
    register_user(db, **registration_payload())
    db.commit()
    with pytest.raises(AccountError, match="ya está registrado"):
        register_user(db, **registration_payload())


def test_registration_requires_whatsapp_phone(db):
    with pytest.raises(AccountError, match="WhatsApp es obligatorio"):
        register_user(db, **registration_payload(phone_whatsapp=""))


def test_registration_requires_department(db):
    with pytest.raises(AccountError, match="departamento"):
        register_user(db, **registration_payload(department=""))


def test_registration_rejects_mismatched_passwords(db):
    with pytest.raises(AccountError, match="confirmación"):
        register_user(db, **registration_payload(confirm_password="OtraClave1*"))


def test_security_questions_must_be_distinct(db):
    with pytest.raises(AccountError, match="repetir"):
        validate_security_answers(
            ["mascota", "mascota", "escuela"],
            ["Firulais", "Firulais", "San José"],
        )


def test_security_answers_are_case_and_accent_insensitive(db):
    user = register_user(db, **registration_payload())
    db.commit()

    assert verify_security_answers(
        user,
        {"mascota": "  FIRULAIS ", "ciudad_madre": "valencia", "escuela": "SAN JOSE"},
    )
    assert not verify_security_answers(
        user,
        {"mascota": "Firulais", "ciudad_madre": "Caracas", "escuela": "San José"},
    )
    assert not verify_security_answers(user, {"mascota": "Firulais"})


def test_set_security_answers_requires_current_password_and_replaces_questions(db):
    user = register_user(db, **registration_payload())
    db.commit()

    with pytest.raises(AccountError, match="contraseña actual"):
        set_security_answers(
            db,
            user,
            question_keys=["mascota", "ciudad_madre", "escuela"],
            answers=["Firulais", "Valencia", "San José"],
            current_password="Incorrecta1*",
        )

    set_security_answers(
        db,
        user,
        question_keys=["primer_vehiculo", "comida_favorita", "equipo"],
        answers=["Toyota", "Pizza", "Caracas FC"],
        current_password="ClaveSegura1*",
    )
    db.commit()

    keys = {row.question_key for row in user.security_answers}
    assert keys == {"primer_vehiculo", "comida_favorita", "equipo"}
    assert verify_security_answers(
        user,
        {"primer_vehiculo": "toyota", "comida_favorita": "pizza", "equipo": "caracas fc"},
    )


def test_set_security_answers_can_keep_the_same_questions(db):
    user = register_user(db, **registration_payload())
    db.commit()

    set_security_answers(
        db,
        user,
        question_keys=["mascota", "ciudad_madre", "escuela"],
        answers=["NuevoPerro", "Maracaibo", "Andrés Bello"],
        current_password="ClaveSegura1*",
    )
    db.commit()

    assert len(user.security_answers) == 3
    assert verify_security_answers(
        user,
        {"mascota": "nuevoperro", "ciudad_madre": "maracaibo", "escuela": "andres bello"},
    )


def test_seed_webmaster_creates_hidden_superuser(db):
    created = seed_webmaster(
        db,
        email="webmaster@munchy.com",
        password="Webmaster2026*",
        name="Webmaster MunchyRoom",
    )
    assert created is True

    webmaster = db.scalar(select(User).where(User.email == "webmaster@munchy.com"))
    assert webmaster is not None
    assert webmaster.is_webmaster is True
    assert webmaster.is_active is True
    assert webmaster.must_change_password is False
    assert webmaster.has_role(Role.ADMIN)
    assert webmaster.has_role(Role.REQUESTER)
    assert verify_password("Webmaster2026*", webmaster.password_hash)
    assert db.scalar(select(func.count()).select_from(WebmasterAccount)) == 1

    # Es idempotente: no crea una segunda cuenta ni cambia la contraseña.
    assert (
        seed_webmaster(
            db,
            email="webmaster@munchy.com",
            password="OtraClave2026*",
            name="Webmaster MunchyRoom",
        )
        is False
    )
    db.refresh(webmaster)
    assert verify_password("Webmaster2026*", webmaster.password_hash)
