#!/usr/bin/env python3
"""Vérifie la connexion MongoDB (variables MONGODB_URI / MONGODB_DB_NAME depuis .env).

Usage depuis la racine du backend :
    python scripts/check_mongo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def main() -> int:
    load_dotenv(_ROOT / ".env")
    uri = os.environ.get("MONGODB_URI", "").strip()
    db_name = os.environ.get("MONGODB_DB_NAME", "").strip()
    if not uri or not db_name:
        print("Définissez MONGODB_URI et MONGODB_DB_NAME dans .env", file=sys.stderr)
        return 1
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=15000,
            retryWrites=True,
        )
        client.admin.command("ping")
        db = client[db_name]
        n = db.users.count_documents({})
        print(f"OK — ping réussi, base « {db_name} », collection users : {n} document(s).")
        return 0
    except PyMongoError as e:
        print(f"Échec : {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
