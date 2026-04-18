"""Irrigation safety prediction using Open-Meteo data and heuristic scoring."""

from __future__ import annotations

import base64
from typing import Any, cast

from flask import Blueprint, jsonify, request

import phosalert_model
from services import gabes_geoml_service
from services import openmeteo_service as owm

bp = Blueprint("prediction", __name__)


def _risk_word_fr(score: int) -> str:
    if score >= 70:
        return "ÉLEVÉ"
    if score >= 40:
        return "MODÉRÉ"
    return "FAIBLE"


def _predict_hour_risk(so2: float, base_score: int) -> tuple[str, int]:
    """Map projected SO2 to coarse risk label for 48h strip."""
    adj = int(min(25, max(-15, (so2 - 40) / 3)))
    s = phosalert_model.clamp_score(base_score + adj)
    label = _risk_word_fr(s)
    return label, s


def build_irrigation_prediction(body: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """
    Construit le payload irrigation (identique à l’ancien ``predict_irrigation``).

    Retourne ``(payload, code_http)`` — en cas d’erreur client, ``payload`` contient
    ``ok: False`` et ``error``.
    """
    farm_lat = float(body.get("latitude", phosalert_model.GABES_LAT))
    farm_lon = float(body.get("longitude", phosalert_model.GABES_LON))
    crop = str(body.get("crop_type", "vegetables"))
    _ = float(body.get("farm_area_ha", 1.0))  # réservé évolutions / affichage

    if crop not in ("olive", "dates", "vegetables", "cereals"):
        return {"error": "crop_type invalide", "ok": False}, 400

    sensitivity = phosalert_model.crop_phosphate_sensitivity(cast(phosalert_model.CropType, crop))

    aq, aq_ok = owm.fetch_air_quality_snapshot(farm_lat, farm_lon)
    wind, wind_ok = owm.fetch_wind_snapshot(farm_lat, farm_lon)

    data_source = "live"
    if not aq_ok or aq.get("so2") is None:
        data_source = "simulated"
        near = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, farm_lat, farm_lon) < 15
        sim_a = phosalert_model.simulate_air_gabes(near_gct=near)
        aq = {**aq, **sim_a}
    if not wind_ok or wind.get("wind_direction") is None:
        data_source = "simulated"
        sw = phosalert_model.simulate_wind()
        wind = {"wind_direction": sw["wind_direction_10m"], "wind_speed": sw["wind_speed_10m"]}

    so2 = float(aq.get("so2") or 0.0)
    wind_from = float(wind.get("wind_direction") or 0.0)

    cop = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, farm_lat, farm_lon)
    downwind = phosalert_model.is_downwind_of_gct(farm_lat, farm_lon, wind_from)

    marine, marine_ok = owm.fetch_marine_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
    if marine_ok and marine.get("chlorophyll") is not None:
        turbidity = float(phosalert_model.simulate_water_gulf(near_industrial_plume=cop < 15)["turbidity"])
        data_source_marine = "live_chlorophyll_sim_turbidity"
    else:
        turbidity = float(phosalert_model.simulate_water_gulf(near_industrial_plume=cop < 15)["turbidity"])
        data_source_marine = "simulated"

    feats = phosalert_model.IrrigationFeatures(
        distance_km=cop,
        so2=so2,
        downwind=downwind,
        turbidity=float(turbidity),
        crop_sensitivity=sensitivity,
    )
    score = phosalert_model.irrigation_risk_score(feats)
    irrigate = score < 58 and not (downwind and so2 > 90 and turbidity > 12)

    band_fr = _risk_word_fr(score)
    reasons: list[str] = []
    if cop < 8:
        reasons.append("Proximité du complexe GCT (< 8 km)")
    if downwind:
        reasons.append("Vent orienté depuis GCT vers la parcelle")
    if so2 > 60:
        reasons.append("SO2 ambiant élevé")
    if turbidity > 10:
        reasons.append("Eaux côtières très turbides (phosphates / particules)")
    if sensitivity == "high":
        reasons.append("Culture sensible aux apports phosphate / contaminants")

    best_time = "06:00-08:00" if irrigate else "avoid"
    base_water = 4500.0 if crop in ("vegetables", "cereals") else 2800.0
    water_l_per_ha = round(base_water * (1.15 - min(score, 85) / 220.0), 1)

    hourly_fc, fc_ok = owm.fetch_air_quality_hourly_forecast(farm_lat, farm_lon, hours=48)
    prediction_48h: list[dict[str, object]] = []
    if fc_ok and hourly_fc:
        for row in hourly_fc[:48]:
            lbl, sc = _predict_hour_risk(float(row["so2"]), score)
            prediction_48h.append({"hour": int(row["hour_of_day"]), "risk": lbl, "score": sc})
    else:
        data_source = "simulated"
        sim = phosalert_model.simulate_air_gabes(near_gct=cop < 15)
        for h in range(48):
            v = float(sim["so2"]) + (h % 7) * 0.8
            lbl, sc = _predict_hour_risk(v, score)
            prediction_48h.append({"hour": h % 24, "risk": lbl, "score": sc})

    advice_fr = (
        "Irrigation possible ce matin tôt; limitez l’arrosage aux heures les plus fraîches."
        if irrigate
        else "Évitez d’irriguer : combinaison vent, SO2 ou eau côtière défavorable."
    )
    advice_ar = "آمن للري — أفضل وقت: 6 صباحاً - 8 صباحاً" if irrigate else "لا تسقي اليوم"

    payload = {
        "irrigate_today": irrigate,
        "risk_score": score,
        "risk_level": band_fr,
        "best_time": best_time,
        "water_quantity_L": water_l_per_ha,
        "advice_fr": advice_fr,
        "advice_ar": advice_ar,
        "reasons": reasons,
        "prediction_48h": prediction_48h,
        "data_source": data_source,
        "marine_data_source": data_source_marine,
        "context": {
            "distance_gct_km": round(cop, 3),
            "so2_ug_m3": round(so2, 2),
            "downwind_from_gct": downwind,
            "wind_from_deg": round(wind_from, 2),
            "wind_speed_kmh": round(float(wind.get("wind_speed") or 0.0), 2),
            "turbidity_model_input": round(float(turbidity), 2),
        },
    }
    return payload, 200


@bp.post("/predict/irrigation")
def predict_irrigation():
    """
    Évaluer si l'irrigation est recommandable (vent, distance GCT, air, eau).
    ---
    tags:
      - Prédiction
    summary: Prédiction irrigation
    security:
      - Bearer: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            latitude:
              type: number
            longitude:
              type: number
            crop_type:
              type: string
              enum: [olive, dates, vegetables, cereals]
            farm_area_ha:
              type: number
    responses:
      200:
        description: Scores et recommandation
      400:
        description: crop_type invalide
      500:
        description: Erreur serveur
    """
    try:
        body = request.get_json(silent=True) or {}
        payload, code = build_irrigation_prediction(body)
        return jsonify(payload), code
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500


@bp.post("/predict/zone")
def predict_zone_water_and_irrigation():
    """
    Parcelle (lat/lon + culture) : irrigation PhosAlert + lien / option GeoML Gabès.

    Combine l’évaluation irrigation (Open-Meteo + modèle HF si configuré) avec le Space
    **kaaboura/gabes-nappe-eau** lorsque le mobile envoie une image tuile en base64.

    Le Space GeoML ne renvoie pas une « nappe » JSON par coordonnées seules : il attend
    ``POST /classify`` avec fichier image. Sans image, la réponse inclut les URLs et une
    note pour l’app (WebView ou export tuile Sentinel-2).
    ---
    tags:
      - Prédiction
    summary: Zone — irrigation + surfaces en eau (GeoML optionnel)
    """
    try:
        body = request.get_json(silent=True) or {}
        irr_payload, code = build_irrigation_prediction(body)
        if code != 200:
            return jsonify(irr_payload), code

        farm_lat = float(body.get("latitude", phosalert_model.GABES_LAT))
        farm_lon = float(body.get("longitude", phosalert_model.GABES_LON))
        crop = str(body.get("crop_type", "vegetables"))
        zone_id = body.get("zone_id") or body.get("zone_name")

        base = gabes_geoml_service.get_base_url()
        geoml: dict[str, Any] = {
            "space_id": "kaaboura/gabes-nappe-eau",
            "space_ui": f"{base}/",
            "post_classify": f"{base}/classify",
            "post_segment": f"{base}/segment",
            "openapi_docs": f"{base}/docs",
            "note_fr": (
                "Le modèle GeoML Gabès attend une image (tuile satellite / Sentinel-2), pas "
                "uniquement lat/lon. Envoyez ``satellite_image_base64`` pour obtenir la classification "
                "ici ; sinon ouvrez ``space_ui`` ou fournissez une tuile depuis votre application."
            ),
            "classification": None,
            "classification_error": None,
            "geoml_health": gabes_geoml_service.geoml_health(),
        }

        b64 = body.get("satellite_image_base64")
        fname = str(body.get("satellite_image_filename", "tile.png"))
        if b64:
            try:
                raw = base64.b64decode(b64, validate=False)
                cls, err = gabes_geoml_service.geoml_classify_image(raw, fname)
                if cls is not None:
                    geoml["classification"] = cls
                else:
                    geoml["classification_error"] = err
            except Exception as exc:  # noqa: BLE001
                geoml["classification_error"] = str(exc)

        feasible = bool(irr_payload.get("irrigate_today"))
        summary = (
            "Irrigation jugée favorable pour cette parcelle."
            if feasible
            else "Irrigation déconseillée avec les conditions actuelles (vent, SO₂, turbidité)."
        )
        summary += f" Score risque : {irr_payload['risk_score']}/100 ({irr_payload['risk_level']})."
        if geoml.get("classification"):
            summary += " Classification surfaces en eau (GeoML) jointe."

        out: dict[str, Any] = {
            "ok": True,
            "zone": {
                "latitude": farm_lat,
                "longitude": farm_lon,
                "crop_type": crop,
            },
            "irrigation": irr_payload,
            "geoml_water_surfaces": geoml,
            "feasibility": {
                "irrigation_recommended": feasible,
                "summary_fr": summary,
            },
        }
        if zone_id is not None:
            out["zone"]["id_or_name"] = zone_id

        return jsonify(out), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500
