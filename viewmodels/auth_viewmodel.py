"""ViewModel authentification JWT (validation, tokens, format réponse)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from flask_jwt_extended import create_access_token, create_refresh_token
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from models.user_roles import (
    DEFAULT_USER_ROLE,
    ROLE_LABELS_FR,
    VALID_USER_ROLES,
    parse_role,
    role_or_default,
)
from repositories.user_repository import UserRepository

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def _jwt_user_claims(email: str, role: str) -> dict[str, str]:
    return {"email": email, "role": role}


class AuthViewModel:
    """Logique métier auth ; les routes ne font qu’appeler ces méthodes."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    @staticmethod
    def _validate_email(email: str) -> bool:
        return bool(email and _EMAIL_RE.match(email.strip()))

    @staticmethod
    def _validate_password(password: str) -> str | None:
        if not password or len(password) < 8:
            return "Le mot de passe doit contenir au moins 8 caractères."
        return None

    @staticmethod
    def _created_at_iso(doc: dict[str, Any]) -> str:
        dt = doc.get("created_at")
        if isinstance(dt, datetime):
            return dt.isoformat()
        return ""

    @staticmethod
    def _resolve_register_role(role_raw: str | None) -> tuple[str | None, str | None]:
        """Retourne ``(rôle, erreur)`` ; erreur non vide → HTTP 400."""
        if role_raw is None or str(role_raw).strip() == "":
            return DEFAULT_USER_ROLE, None
        p = parse_role(role_raw)
        if p is None:
            joined = ", ".join(sorted(VALID_USER_ROLES))
            return None, f"Rôle invalide. Utilisez l'un de : {joined}."
        return p, None

    def register(self, email: str, password: str, role_raw: str | None) -> tuple[dict[str, Any], int]:
        email = email.strip().lower()
        if not self._validate_email(email):
            return {"ok": False, "error": "Adresse e-mail invalide."}, 400
        pwd_err = self._validate_password(password)
        if pwd_err:
            return {"ok": False, "error": pwd_err}, 400
        role, role_err = self._resolve_register_role(role_raw)
        if role_err or role is None:
            return {"ok": False, "error": role_err or "Rôle invalide."}, 400
        try:
            user = self._users.create(email, generate_password_hash(password), role=role)
        except DuplicateKeyError:
            return {"ok": False, "error": "Cette adresse e-mail est déjà enregistrée."}, 409

        uid = UserRepository.user_id_str(user)
        claims = _jwt_user_claims(email, role)
        access = create_access_token(identity=uid, additional_claims=claims)
        refresh = create_refresh_token(identity=uid, additional_claims=claims)
        return {
            "ok": True,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "user": {
                "id": uid,
                "email": email,
                "role": role,
                "role_label": ROLE_LABELS_FR.get(role, role),
            },
        }, 201

    def login(self, email: str, password: str) -> tuple[dict[str, Any], int]:
        email = email.strip().lower()
        if not email or not password:
            return {"ok": False, "error": "E-mail et mot de passe requis."}, 400

        user = self._users.find_by_email(email)
        if user is None or not check_password_hash(str(user.get("password_hash", "")), password):
            return {"ok": False, "error": "Identifiants incorrects."}, 401

        uid = UserRepository.user_id_str(user)
        role = role_or_default(user)
        claims = _jwt_user_claims(email, role)
        access = create_access_token(identity=uid, additional_claims=claims)
        refresh = create_refresh_token(identity=uid, additional_claims=claims)
        return {
            "ok": True,
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "user": {
                "id": uid,
                "email": email,
                "role": role,
                "role_label": ROLE_LABELS_FR.get(role, role),
            },
        }, 200

    def refresh(self, user_id: str) -> tuple[dict[str, Any], int]:
        user = self._users.find_by_id_str(user_id)
        if user is None:
            return {"ok": False, "error": "Utilisateur introuvable."}, 401
        email = str(user.get("email", ""))
        role = role_or_default(user)
        access = create_access_token(
            identity=UserRepository.user_id_str(user),
            additional_claims=_jwt_user_claims(email, role),
        )
        return {"ok": True, "access_token": access, "token_type": "Bearer"}, 200

    def me(self, user_id: str) -> tuple[dict[str, Any], int]:
        user = self._users.find_by_id_str(user_id)
        if user is None:
            return {"ok": False, "error": "Utilisateur introuvable."}, 404
        role = role_or_default(user)
        return {
            "ok": True,
            "user": {
                "id": UserRepository.user_id_str(user),
                "email": str(user.get("email", "")),
                "role": role,
                "role_label": ROLE_LABELS_FR.get(role, role),
                "created_at": self._created_at_iso(user),
            },
        }, 200
