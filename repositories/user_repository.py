"""Persistance des utilisateurs (collection MongoDB ``users``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    """Accès CRUD utilisateur."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        return self._db.users.find_one({"email": email})

    def find_by_id_str(self, uid: str) -> dict[str, Any] | None:
        try:
            return self._db.users.find_one({"_id": ObjectId(uid)})
        except InvalidId:
            return None

    def create(self, email: str, password_hash: str, *, role: str) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "created_at": utc_now(),
        }
        result = self._db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    @staticmethod
    def user_id_str(doc: dict[str, Any]) -> str:
        return str(doc["_id"])
