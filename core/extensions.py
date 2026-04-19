"""Flask extensions (MongoDB, JWT) — Mongo initialisé dans ``create_app``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask_jwt_extended import JWTManager
from pymongo import MongoClient
from pymongo.errors import PyMongoError

if TYPE_CHECKING:
    from pymongo.database import Database

jwt = JWTManager()
_mongo_client: MongoClient | None = None
mongo_db: Database | None = None

logger = logging.getLogger(__name__)


def init_mongo(app) -> None:
    """Connexion MongoDB (local ou Atlas ``mongodb+srv``), ping au démarrage, index ``users.email``."""
    global _mongo_client, mongo_db
    uri = str(app.config["MONGODB_URI"]).strip()
    db_name = str(app.config["MONGODB_DB_NAME"]).strip()
    if not uri or not db_name:
        raise RuntimeError("MONGODB_URI et MONGODB_DB_NAME sont requis.")

    try:
        _mongo_client = MongoClient(
            uri,
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=15000,
            socketTimeoutMS=45000,
            retryWrites=True,
        )
        _mongo_client.admin.command("ping")
        mongo_db = _mongo_client[db_name]
        mongo_db.users.create_index("email", unique=True)
    except PyMongoError as exc:
        hint = ""
        if "mongodb+srv" in uri:
            hint = (
                " Vérifiez Atlas : Network Access (IP 0.0.0.0/0 ou IP Railway), "
                "identifiants, et que la chaîne contient bien retryWrites / appName si besoin."
            )
        logger.exception("MongoDB connection failed.%s", hint)
        raise RuntimeError(f"Impossible de joindre MongoDB ({db_name}): {exc}") from exc

    logger.info("MongoDB OK — base « %s ».", db_name)
