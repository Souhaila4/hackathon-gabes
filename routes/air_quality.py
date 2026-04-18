"""Air quality, wind, and combined Open-Meteo realtime endpoints."""

from __future__ import annotations

from flask import Blueprint, jsonify

from services.openmeteo_service import fetch_air_quality, fetch_all_realtime, fetch_wind_data

bp = Blueprint("air_quality", __name__)


@bp.get("/air-quality")
def get_air_quality():
    """
    Dernières mesures SO₂ / NO₂ / NH₃, historiques, vent fusionné.
    ---
    tags:
      - Air
    summary: "Qualité de l'air + vent"
    security:
      - Bearer: []
    description: "Clés legacy wind_speed / wind_direction conservées."
    responses:
      200:
        description: Payload air + vent
      500:
        description: Erreur serveur
    """
    try:
        air = fetch_air_quality()
        wind = fetch_wind_data()

        payload = {
            **air,
            "wind_speed_kmh": wind["wind_speed_kmh"],
            "wind_direction_degrees": wind["wind_direction_degrees"],
            "wind_direction_name": wind.get("wind_direction_name"),
            "wind_speed": wind["wind_speed_kmh"],
            "wind_direction": wind["wind_direction_degrees"],
            "wind_timestamp": wind.get("timestamp"),
            "wind_data_source": wind["data_source"],
        }

        payload["data_source"] = (
            "live" if air["data_source"] == "real" and wind["data_source"] == "real" else "simulated"
        )

        return jsonify(payload), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500


@bp.get("/wind")
def get_wind():
    """
    Vent — vitesse, direction, prévision 24h.
    ---
    tags:
      - Air
    summary: Vent
    security:
      - Bearer: []
    responses:
      200:
        description: Données vent
      500:
        description: Erreur serveur
    """
    try:
        data = fetch_wind_data()
        return jsonify(data), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500


@bp.get("/realtime")
def get_realtime():
    """
    Air + vent + zones affectées (temps réel combiné).
    ---
    tags:
      - Air
    summary: Temps réel combiné
    security:
      - Bearer: []
    responses:
      200:
        description: Agrégat temps réel
      500:
        description: Erreur serveur
    """
    try:
        data = fetch_all_realtime()
        return jsonify(data), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500
