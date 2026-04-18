"""Routes moteur d'alertes (agrégat NAFAS + air + eau + vent)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from services.alert_engine import run_alert_engine

alerts_bp = Blueprint("alerts", __name__)
bp = alerts_bp


@bp.get("/alerts")
def alerts_index():
    """
    Résumé alertes et liste courte.
    ---
    tags:
      - Alertes
    summary: Alertes (résumé)
    security:
      - Bearer: []
    responses:
      200:
        description: summary, alerts, generated_at
    """
    try:
        r = run_alert_engine()
        return (
            jsonify(
                {
                    "summary": r["summary"],
                    "alerts": r["alerts"],
                    "generated_at": r["generated_at"],
                }
            ),
            200,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/alerts/zones")
def alerts_zones():
    """
    Scores par zone.
    ---
    tags:
      - Alertes
    summary: Zones et scores
    security:
      - Bearer: []
    """
    try:
        r = run_alert_engine()
        return jsonify({"zone_scores": r["zone_scores"], "generated_at": r["generated_at"]}), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/alerts/forecast")
def alerts_forecast():
    """
    Prévision risque 48h (SO2 horaire).
    ---
    tags:
      - Alertes
    summary: Prévision 48h
    security:
      - Bearer: []
    """
    try:
        r = run_alert_engine()
        return (
            jsonify(
                {
                    "forecast_48h": r["forecast_48h"],
                    "generated_at": r["generated_at"],
                }
            ),
            200,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/alerts/full")
def alerts_full():
    """
    Payload complet du moteur d'alertes.
    ---
    tags:
      - Alertes
    summary: Alert engine complet
    security:
      - Bearer: []
    """
    try:
        return jsonify(run_alert_engine()), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
