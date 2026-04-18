"""Tableau de bord personnalisé par rôle JWT (données temps réel)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

from models.user_roles import VALID_USER_ROLES
from services.dashboard_service import (
    build_agriculteur_dashboard,
    build_chercheur_dashboard,
    build_citoyen_dashboard,
)

bp = Blueprint("dashboard", __name__)


def _normalize_role(raw: str | None) -> str:
    r = (raw or "citoyen").strip()
    return r if r in VALID_USER_ROLES else "citoyen"


@bp.get("/dashboard")
@jwt_required(optional=True)
def get_dashboard():
    """
    Tableau de bord agrégé — contenu selon le rôle JWT (sinon citoyen).
    Query (agriculteur) : ``crop``, ``lat``, ``lon``.
    ---
    tags:
      - Dashboard
    summary: Tableau de bord (rôle JWT)
    security:
      - Bearer: []
    parameters:
      - in: query
        name: crop
        type: string
        description: Culture (agriculteur)
      - in: query
        name: lat
        type: number
      - in: query
        name: lon
        type: number
    responses:
      200:
        description: Payload personnalisé
      500:
        description: Erreur génération
    """
    try:
        claims = get_jwt() or {}
        role = _normalize_role(claims.get("role"))

        crop = request.args.get("crop", "olive")
        lat = request.args.get("lat", type=float)
        lon = request.args.get("lon", type=float)

        if role == "agriculteur":
            data = build_agriculteur_dashboard(crop=crop, lat=lat, lon=lon)
        elif role == "chercheur_scientifique":
            data = build_chercheur_dashboard()
        else:
            data = build_citoyen_dashboard()

        data["jwt_role"] = role
        return jsonify(data), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "message": "Dashboard generation failed", "ok": False}), 500
