"""Avis officiels ANPE ↔ suivi industriel GCT (MongoDB)."""

from __future__ import annotations

from datetime import datetime, timezone

import core.extensions as extensions
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

bp = Blueprint("regulatory", __name__)


def _require_role(role: str) -> tuple[dict[str, str] | None, tuple | None]:
    claims = get_jwt() or {}
    if claims.get("role") != role:
        return None, (jsonify({"ok": False, "error": "Accès réservé à ce profil."}), 403)
    email = claims.get("email") or ""
    return {"email": str(email), "role": str(claims.get("role"))}, None


@bp.post("/regulatory/notices")
@jwt_required()
def create_notice():
    """Autorité : envoyer un avis / notification formelle vers le dossier industriel."""
    user, err_resp = _require_role("autorite")
    if err_resp:
        return err_resp
    body = request.get_json(silent=True) or {}
    title = str(body.get("title_fr", "")).strip() or "Avis ANPE"
    message = str(body.get("body_fr", "")).strip()
    violation_type = str(body.get("violation_type", "")).strip()
    db = extensions.mongo_db
    if db is None:
        return jsonify({"ok": False, "error": "MongoDB indisponible."}), 503

    doc = {
        "title_fr": title,
        "body_fr": message,
        "violation_type": violation_type,
        "from_role": "autorite",
        "to_site": "GCT",
        "status": "sent",
        "created_at": datetime.now(timezone.utc),
        "author_email": user["email"] if user else "",
    }
    res = db.regulatory_notices.insert_one(doc)
    return jsonify({"ok": True, "id": str(res.inserted_id)}), 201


@bp.get("/regulatory/notices/inbox")
@jwt_required()
def industriel_inbox():
    """Industriel : liste des avis ANPE adressés au site."""
    _, err_resp = _require_role("industriel")
    if err_resp:
        return err_resp
    db = extensions.mongo_db
    if db is None:
        return jsonify({"ok": False, "notices": []}), 200

    cur = db.regulatory_notices.find({"to_site": "GCT"}).sort("created_at", -1).limit(100)
    notices = []
    for doc in cur:
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        notices.append(doc)
    return jsonify({"ok": True, "notices": notices, "unread_count": 0}), 200


@bp.get("/regulatory/notices/sent")
@jwt_required()
def autorite_sent():
    """Autorité : historique des avis émis."""
    _, err_resp = _require_role("autorite")
    if err_resp:
        return err_resp
    db = extensions.mongo_db
    if db is None:
        return jsonify({"ok": True, "notices": []}), 200

    cur = (
        db.regulatory_notices.find({"from_role": "autorite"})
        .sort("created_at", -1)
        .limit(100)
    )
    notices = []
    for doc in cur:
        doc["_id"] = str(doc["_id"])
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        notices.append(doc)
    return jsonify({"ok": True, "notices": notices}), 200
