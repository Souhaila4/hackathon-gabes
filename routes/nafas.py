"""
NAFAS — prévisions pollution 48h (View HTTP).
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify

from services.nafas_service import fetch_dynamic_nafas

bp = Blueprint("nafas", __name__)


def _nafas_payload_or_error() -> tuple[dict[str, Any], int]:
    data = fetch_dynamic_nafas()
    if not data.get("ok", True):
        return data, 503
    return data, 200


@bp.get("/nafas/predict")
def predict():
    """
    Prévision 48h Gabès — données Open-Meteo temps réel (qualité air + vent).
    ---
    tags:
      - NAFAS
    summary: Prévision pollution (dynamique Open-Meteo)
    security:
      - Bearer: []
    responses:
      200:
        description: Prévisions et zones de dépôt
      503:
        description: Open-Meteo indisponible
      500:
        description: Erreur inattendue
    """
    try:
        data, code = _nafas_payload_or_error()
        return jsonify(data), code
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "message": "NAFAS prediction failed", "ok": False}), 500


@bp.get("/nafas/alerts")
def nafas_alerts():
    """
    Alertes dérivées des prévisions (Open-Meteo).
    ---
    tags:
      - NAFAS
    summary: Alertes uniquement
    security:
      - Bearer: []
    responses:
      200:
        description: alerts, overall_risk, generated_at
      503:
        description: Données source indisponibles
    """
    try:
        data, code = _nafas_payload_or_error()
        if code != 200:
            return jsonify(data), code
        return (
            jsonify(
                {
                    "alerts": data["alerts"],
                    "overall_risk": data["overall_risk"],
                    "generated_at": data["generated_at"],
                }
            ),
            200,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500


@bp.get("/nafas/deposition-map")
def deposition_map():
    """
    Zones de dépôt pour affichage carte (vent Open-Meteo).
    ---
    tags:
      - NAFAS
    summary: Carte dépôt pollution
    security:
      - Bearer: []
    responses:
      200:
        description: deposition_zones et résumé J1/J2
      503:
        description: Données source indisponibles
    """
    try:
        data, code = _nafas_payload_or_error()
        if code != 200:
            return jsonify(data), code
        body: dict[str, Any] = {
            "deposition_zones": data["deposition_zones"],
            "predictions_summary": {
                "day1_risk": data["predictions"]["day1"]["risk_level"],
                "day2_risk": data["predictions"]["day2"]["risk_level"],
                "exceeds_WHO": data["exceeds_WHO"],
            },
            "generated_at": data["generated_at"],
        }
        return jsonify(body), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500
