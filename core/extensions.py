"""Flask extensions (MongoDB, JWT) — Mongo initialisé dans ``create_app``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_jwt_extended import JWTManager
from pymongo import MongoClient

if TYPE_CHECKING:
    from pymongo.database import Database

jwt = JWTManager()
_mongo_client: MongoClient | None = None
mongo_db: Database | None = None


def init_mongo(app) -> None:
    """Connexion MongoDB, base nommée, index unique sur ``users.email``."""
    global _mongo_client, mongo_db
    uri = app.config["MONGODB_URI"]
    db_name = app.config["MONGODB_DB_NAME"]
    _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    mongo_db = _mongo_client[db_name]
    mongo_db.users.create_index("email", unique=True)
