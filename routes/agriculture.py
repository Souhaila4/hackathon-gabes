"""Recommandations agricoles par culture et position."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.agriculture_service import crops_for_location, recommend_agriculture

bp = Blueprint("agriculture", __name__)


@bp.post("/agriculture/recommend")
def recommend():
    """
    Recommandation pour une culture à une coordonnée (irrigation, risques GCT).
    ---
    tags:
      - Agriculture
    summary: Recommandation agriculture
    security:
      - Bearer: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - crop
            - latitude
            - longitude
          properties:
            crop:
              type: string
              example: olive
            latitude:
              type: number
            longitude:
              type: number
    responses:
      200:
        description: Conseils et scores
      400:
        description: Paramètres invalides
      500:
        description: Erreur serveur
    """
    try:
        body = request.get_json(silent=True) or {}
        crop = str(body.get("crop", "")).strip()
        if not crop:
            return jsonify({"ok": False, "error": "crop requis"}), 400
        lat = float(body.get("latitude"))
        lon = float(body.get("longitude"))
        data = recommend_agriculture(crop, lat, lon)
        return jsonify(data), 200
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except (TypeError, KeyError):
        return jsonify(
            {
                "ok": False,
                "error": "latitude, longitude et crop requis (JSON)",
            }
        ), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/agriculture/crops")
def crops():
    """
    Cultures suivies avec score de pertinence pour un point géographique.
    ---
    tags:
      - Agriculture
    summary: Liste cultures / adéquation
    security:
      - Bearer: []
    parameters:
      - in: query
        name: lat
        type: number
        required: true
      - in: query
        name: lon
        type: number
        required: true
    responses:
      200:
        description: Liste triée par adéquation
      400:
        description: lat/lon manquants ou invalides
    """
    try:
        lat = float(request.args.get("lat", ""))
        lon = float(request.args.get("lon", ""))
    except ValueError:
        return jsonify({"ok": False, "error": "lat et lon requis (nombres)"}), 400
    try:
        data = crops_for_location(lat, lon)
        return jsonify(data), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
