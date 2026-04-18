"""Water quality for Gulf of Gabès with Copernicus → Open-Meteo → simulation chain."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify

from services import copernicus_service
import phosalert_model
from services import openmeteo_service as owm

bp = Blueprint("water_quality", __name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@bp.get("/water-quality")
def get_water_quality():
    """
    Turbidité, chlorophylle, bande de contamination, risque phosphate.
    ---
    tags:
      - Eau
    summary: "Qualité de l'eau (golfe de Gabès)"
    security:
      - Bearer: []
    responses:
      200:
        description: Indicateurs eau
      500:
        description: Erreur serveur
    """
    try:
        lat, lon = phosalert_model.GABES_LAT, phosalert_model.GABES_LON

        cop = copernicus_service.fetch_copernicus_marine(lat, lon)
        marine, marine_ok = owm.fetch_marine_snapshot(lat, lon)

        data_source = "live"
        turbidity: float | None = None
        chlorophyll: float | None = None

        if cop and isinstance(cop, dict) and cop.get("turbidity") is not None:
            turbidity = float(cop["turbidity"])
        if cop and isinstance(cop, dict) and cop.get("chlorophyll") is not None:
            chlorophyll = float(cop["chlorophyll"])

        if marine_ok and marine.get("chlorophyll") is not None:
            chlorophyll = float(marine["chlorophyll"])
        elif chlorophyll is None:
            pass

        if turbidity is None or chlorophyll is None:
            data_source = "simulated"
            sim = phosalert_model.simulate_water_gulf(near_industrial_plume=True)
            if turbidity is None:
                turbidity = sim["turbidity"]
            if chlorophyll is None:
                chlorophyll = sim["chlorophyll"]

        dist_gct_km = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, lat, lon)
        phosphate_risk = dist_gct_km < 12.0

        band, wscore = phosalert_model.water_contamination_level(float(turbidity), float(chlorophyll))
        wcolor = phosalert_model.water_color(band)

        if band == "CONTAMINATED":
            advice_fr = "Turbidité élevée côté baie : risque pour l’irrigation et la pêche locale."
            advice_ar = "الماء ملوث — احذر من الري أو استخدام مياه البحر"
        elif band == "SUSPECT":
            advice_fr = "Qualité de l’eau douteuse : surveillance recommandée pour les récoltes sensibles."
            advice_ar = "جودة الماء مشبوهة — راقب المحاصيل الحساسة"
        else:
            advice_fr = "Indices côtiers relativement calmes mais restez vigilant près du panache industriel."
            advice_ar = "المؤشرات مقبولة لكن انتبه قرب المصنع الكيميائي"

        payload = {
            "turbidity": round(float(turbidity), 2),
            "chlorophyll": round(float(chlorophyll), 2),
            "contamination_level": band,
            "risk_score": wscore,
            "color": wcolor,
            "phosphate_risk": phosphate_risk,
            "advice_fr": advice_fr,
            "advice_ar": advice_ar,
            "timestamp": str(marine.get("timestamp") or _iso_now()),
            "data_source": data_source,
        }
        return jsonify(payload), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500
