"""API visualisation du vent (grille U/V, panache GCT, animation carte)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from services.wind_flow_service import (
    get_wind_animation_only,
    get_wind_flow_data,
    get_wind_grid_only,
    get_wind_plume_only,
)

bp = Blueprint("wind_flow", __name__)


@bp.get("/wind/flow")
def get_wind_flow():
    """
    Données complètes pour carte type Windy (grille 5×5, panache, animation, 24 h).
    ---
    tags:
      - Vent
    summary: Flux vent temps réel + grille Gabès / GCT
    responses:
      200:
        description: wind_grid, gct_wind, plume, animation, forecast_24h
      500:
        description: Erreur Open-Meteo ou timeout
    """
    try:
        data = get_wind_flow_data()
        return jsonify(data), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc), "message": "Wind flow data unavailable"}), 500


@bp.get("/wind/flow/grid")
def get_wind_grid():
    """
    Grille 5×5 seule (léger — flèches vent sur carte).
    ---
    tags:
      - Vent
    summary: Grille U/V uniquement
    """
    try:
        return jsonify(get_wind_grid_only()), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/wind/flow/plume")
def get_pollution_plume():
    """
    Panache pollution indicatif depuis GCT (sans grille 25 points).
    ---
    tags:
      - Vent
    summary: Trajectoire panache SO₂/NH₃ (modèle démo)
    """
    try:
        return jsonify(get_wind_plume_only()), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.get("/wind/flow/animation")
def get_animation_params():
    """
    Paramètres animation particules / échelle couleur (1 appel Open-Meteo).
    ---
    tags:
      - Vent
    summary: Paramètres animation carte
    """
    try:
        return jsonify(get_wind_animation_only()), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500
