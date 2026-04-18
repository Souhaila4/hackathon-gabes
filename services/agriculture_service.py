"""
Recommandations agricoles (cultures, irrigation, risques GCT / qualité de l'air).

Données : Open-Meteo + heuristiques ``phosalert_model`` (cohérent avec ``/api/predict/irrigation``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

# Permet ``python services/agriculture_service.py`` depuis la racine backend
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import phosalert_model as pm
from phosalert_model import CropType
from services import openmeteo_service as owm

SUPPORTED_CROPS: tuple[str, ...] = ("olive", "dates", "vegetables", "cereals")

CROP_LABELS: dict[str, dict[str, str]] = {
    "olive": {"fr": "Olivier", "ar": "زيتون"},
    "dates": {"fr": "Palmier dattier", "ar": "نخيل"},
    "vegetables": {"fr": "Maraîchage", "ar": "خضروات"},
    "cereals": {"fr": "Céréales", "ar": "حبوب"},
}


def _risk_word_fr(score: int) -> str:
    if score >= 70:
        return "ÉLEVÉ"
    if score >= 40:
        return "MODÉRÉ"
    return "FAIBLE"


def _gather_context(latitude: float, longitude: float) -> dict[str, Any]:
    """Air, vent, distance GCT, turbidité eau (même logique que predict/irrigation)."""
    aq, aq_ok = owm.fetch_air_quality_snapshot(latitude, longitude)
    wind, wind_ok = owm.fetch_wind_snapshot(latitude, longitude)

    data_source = "live"
    if not aq_ok or aq.get("so2") is None:
        data_source = "simulated"
        near = pm.haversine_km(pm.GCT_LAT, pm.GCT_LON, latitude, longitude) < 15
        sim_a = pm.simulate_air_gabes(near_gct=near)
        aq = {**aq, **sim_a}
    if not wind_ok or wind.get("wind_direction") is None:
        data_source = "simulated"
        sw = pm.simulate_wind()
        wind = {"wind_direction": sw["wind_direction_10m"], "wind_speed": sw["wind_speed_10m"]}

    so2 = float(aq.get("so2") or 0.0)
    wind_from = float(wind.get("wind_direction") or 0.0)
    wind_speed = float(wind.get("wind_speed") or 0.0)

    dist_gct = pm.haversine_km(pm.GCT_LAT, pm.GCT_LON, latitude, longitude)
    downwind = pm.is_downwind_of_gct(latitude, longitude, wind_from)

    marine, marine_ok = owm.fetch_marine_snapshot(pm.GABES_LAT, pm.GABES_LON)
    if marine_ok and marine.get("chlorophyll") is not None:
        turbidity = float(pm.simulate_water_gulf(near_industrial_plume=dist_gct < 15)["turbidity"])
    else:
        turbidity = float(pm.simulate_water_gulf(near_industrial_plume=dist_gct < 15)["turbidity"])

    return {
        "aq": aq,
        "wind": wind,
        "so2": so2,
        "wind_from_deg": wind_from,
        "wind_speed_kmh": wind_speed,
        "distance_km_gct": dist_gct,
        "downwind": downwind,
        "turbidity": turbidity,
        "data_source": data_source,
    }


def recommend_agriculture(crop: str, latitude: float, longitude: float) -> dict[str, Any]:
    """
    Recommandation pour une culture à une position (irrigation, risques, conseils).
    Lève ``ValueError`` si culture inconnue.
    """
    key = crop.lower().strip()
    if key not in SUPPORTED_CROPS:
        raise ValueError(f"culture inconnue: {crop!r} (attendu: {list(SUPPORTED_CROPS)})")

    ctx = _gather_context(latitude, longitude)
    sensitivity = pm.crop_phosphate_sensitivity(cast(CropType, key))

    feats = pm.IrrigationFeatures(
        distance_km=float(ctx["distance_km_gct"]),
        so2=float(ctx["so2"]),
        downwind=bool(ctx["downwind"]),
        turbidity=float(ctx["turbidity"]),
        crop_sensitivity=sensitivity,
    )
    score = pm.irrigation_risk_score(feats)
    irrigate = score < 58 and not (
        ctx["downwind"] and ctx["so2"] > 90 and ctx["turbidity"] > 12
    )

    band = _risk_word_fr(score)
    reasons: list[str] = []
    if ctx["distance_km_gct"] < 8:
        reasons.append("Proximité du complexe GCT (< 8 km)")
    if ctx["downwind"]:
        reasons.append("Vent orienté depuis GCT vers la parcelle")
    if ctx["so2"] > 60:
        reasons.append("SO2 ambiant élevé")
    if ctx["turbidity"] > 10:
        reasons.append("Eaux côtières très turbides")
    if sensitivity == "high":
        reasons.append("Culture sensible aux apports phosphate / contaminants")

    tips_fr: list[str] = []
    tips_ar: list[str] = []
    if key == "olive":
        tips_fr.append("Entretien sol drainé; éviter l’excès d’azote si panache industriel.")
        tips_ar.append("تربة جيدة الصرف؛ تجنب فرط النيتروجين عند اللوثة.")
    elif key == "dates":
        tips_fr.append("Surveiller salinité et apports en période de vent de mer / brume.")
        tips_ar.append("راقب الملوحة والري عند الرياح البحرية.")
    elif key == "vegetables":
        tips_fr.append("Privilégier arrosage au goutte-à-goutte; laver les feuilles si SO2 modéré.")
        tips_ar.append("الري بالتنقيط؛ غسل الأوراق عند SO2 متوسط.")
    else:
        tips_fr.append("Adapter densité de semis selon stress salin / poussières.")
        tips_ar.append("اضبط الكثافة حسب الملوحة والغبار.")

    return {
        "ok": True,
        "crop": key,
        "labels": CROP_LABELS.get(key, {}),
        "location": {"latitude": latitude, "longitude": longitude},
        "distance_km_gct": round(ctx["distance_km_gct"], 2),
        "phosphate_sensitivity": sensitivity,
        "irrigation": {
            "risk_score": score,
            "risk_level_fr": band,
            "irrigate_recommended": irrigate,
            "best_time_window": "06:00-08:00" if irrigate else "avoid",
            "reasons": reasons,
        },
        "air": {"so2_ug_m3": ctx["so2"], "snapshot_ok": ctx["aq"].get("so2") is not None},
        "wind": {
            "from_degrees": ctx["wind_from_deg"],
            "speed_kmh": ctx["wind_speed_kmh"],
            "downwind_from_gct": ctx["downwind"],
        },
        "data_source": ctx["data_source"],
        "tips_fr": tips_fr,
        "tips_ar": tips_ar,
    }


def crops_for_location(latitude: float, longitude: float) -> dict[str, Any]:
    """
    Liste les cultures suivies avec un score de « confort agricole » (100 = favorable).
    Score dérivé du risque irrigation (plus le score de risque est bas, plus le confort est haut).
    """
    ctx = _gather_context(latitude, longitude)
    out: list[dict[str, Any]] = []

    for c in SUPPORTED_CROPS:
        sens = pm.crop_phosphate_sensitivity(cast(CropType, c))
        feats = pm.IrrigationFeatures(
            distance_km=float(ctx["distance_km_gct"]),
            so2=float(ctx["so2"]),
            downwind=bool(ctx["downwind"]),
            turbidity=float(ctx["turbidity"]),
            crop_sensitivity=sens,
        )
        risk = pm.irrigation_risk_score(feats)
        comfort = max(0, min(100, 100 - risk))
        out.append(
            {
                "id": c,
                "name_fr": CROP_LABELS[c]["fr"],
                "name_ar": CROP_LABELS[c]["ar"],
                "phosphate_sensitivity": sens,
                "irrigation_risk_score": risk,
                "suitability_score": comfort,
                "note_fr": _crop_note_fr(c, risk, ctx["distance_km_gct"]),
            }
        )

    out.sort(key=lambda x: (-int(x["suitability_score"]), x["id"]))
    return {
        "ok": True,
        "location": {"latitude": latitude, "longitude": longitude},
        "distance_km_gct": round(ctx["distance_km_gct"], 2),
        "crops": out,
        "data_source": ctx["data_source"],
    }


def _crop_note_fr(crop: str, risk: int, dist_km: float) -> str:
    if crop in ("olive", "dates") and dist_km < 12:
        return "Adapté à la zone oasiennes / périmètre GCT; surveiller dépôts."
    if crop in ("vegetables", "cereals") and risk >= 55:
        return "Culture sensible: exiger surveillance SO2 et qualité d’eau d’irrigation."
    if risk < 40:
        return "Conditions relativement favorables pour la période."
    return "Adapter pratiques (horaires d’irrigation, hygiène des récoltes)."


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    lat, lon = 33.88, 10.05
    print("Agriculture service — test direct\n")
    r = recommend_agriculture("olive", lat, lon)
    print("[recommend olive]", r["crop"], "risk", r["irrigation"]["risk_score"], r["irrigation"]["risk_level_fr"])
    c = crops_for_location(lat, lon)
    print("[crops]", len(c["crops"]), "cultures, meilleur:", c["crops"][0]["id"], "suitability", c["crops"][0]["suitability_score"])
    print("OK.")
