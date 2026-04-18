"""
**Interface publique du modèle** — point d’entrée unique pour le backend PhosAlert.

Le serveur (routes, viewmodels, ``app``) doit importer **uniquement** depuis ce module
ou depuis ``import phosalert_model`` (qui réexporte le même contenu).

Ne pas importer ``phosalert_model.heuristics`` ni ``phosalert_model.trained`` depuis le
code HTTP : cela garde la séparation *API / orchestration* vs *scoring & artefacts ML*.
"""

from __future__ import annotations

from phosalert_model.constants import EARTH_RADIUS_KM, GABES_LAT, GABES_LON, GCT_LAT, GCT_LON
from phosalert_model.heuristics import (
    CropType,
    IrrigationFeatures,
    RiskBand,
    WaterBand,
    air_color,
    air_risk_from_so2,
    angular_difference_deg,
    bearing_degrees,
    clamp_score,
    crop_phosphate_sensitivity,
    haversine_km,
    irrigation_risk_heuristic,
    is_downwind_of_gct,
    risk_level_label_from_score,
    simulate_air_gabes,
    simulate_water_gulf,
    simulate_wind,
    water_color,
    water_contamination_level,
    zone_risk_score,
)
from phosalert_model.trained import try_irrigation_hf_remote, try_irrigation_trained


def irrigation_risk_score(f: IrrigationFeatures) -> int:
    """Score irrigation : Hugging Face (si URL) → joblib local → heuristique."""
    h = try_irrigation_hf_remote(f)
    if h is not None:
        return h
    t = try_irrigation_trained(f)
    if t is not None:
        return t
    return irrigation_risk_heuristic(f)


__all__ = [
    "CropType",
    "EARTH_RADIUS_KM",
    "GABES_LAT",
    "GABES_LON",
    "GCT_LAT",
    "GCT_LON",
    "IrrigationFeatures",
    "RiskBand",
    "WaterBand",
    "air_color",
    "air_risk_from_so2",
    "angular_difference_deg",
    "bearing_degrees",
    "clamp_score",
    "crop_phosphate_sensitivity",
    "haversine_km",
    "irrigation_risk_heuristic",
    "irrigation_risk_score",
    "is_downwind_of_gct",
    "risk_level_label_from_score",
    "simulate_air_gabes",
    "simulate_water_gulf",
    "simulate_wind",
    "try_irrigation_hf_remote",
    "try_irrigation_trained",
    "water_color",
    "water_contamination_level",
    "zone_risk_score",
]
