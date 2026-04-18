"""
Scores heuristiques (règles + poids fixes) — **sans** dépendance à un fichier entraîné.

Pour l’inférence joblib, voir ``phosalert_model.trained`` et la façade ``phosalert_model.api``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Literal

from phosalert_model.constants import EARTH_RADIUS_KM, GABES_LAT, GABES_LON, GCT_LAT, GCT_LON

CropType = Literal["olive", "dates", "vegetables", "cereals"]
RiskBand = Literal["SAFE", "MODERATE", "DANGEROUS"]
WaterBand = Literal["CLEAN", "SUSPECT", "CONTAMINATED"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.degrees(math.atan2(y, x))
    return (theta + 360.0) % 360.0


def angular_difference_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def is_downwind_of_gct(
    farm_lat: float,
    farm_lon: float,
    wind_from_degrees: float,
    threshold_deg: float = 45.0,
    gct_lat: float = GCT_LAT,
    gct_lon: float = GCT_LON,
) -> bool:
    bearing_gct_to_farm = bearing_degrees(gct_lat, gct_lon, farm_lat, farm_lon)
    wind_toward_deg = (wind_from_degrees + 180.0) % 360.0
    return angular_difference_deg(bearing_gct_to_farm, wind_toward_deg) < threshold_deg


def air_risk_from_so2(so2_ug_m3: float) -> tuple[RiskBand, int, str, str]:
    if so2_ug_m3 > 100:
        return (
            "DANGEROUS",
            min(100, int(60 + so2_ug_m3 / 5)),
            "Alerte: émissions GCT élevées. Restez à l’intérieur si possible.",
            "تنبيه: انبعاثات GCT مرتفعة. ابق في المنزل",
        )
    if so2_ug_m3 > 40:
        return (
            "MODERATE",
            min(85, int(35 + so2_ug_m3)),
            "Qualité de l’air modérée près des sources industrielles. Surveillez les symptômes respiratoires.",
            "جودة الهواء متوسطة قرب المصادر. راقب الأعراض التنفسية",
        )
    return (
        "SAFE",
        max(0, min(35, int(so2_ug_m3))),
        "Les niveaux de SO2 restent dans une plage acceptable à Gabès pour l’instant.",
        "مستويات SO2 مقبولة حالياً في قابس",
    )


def air_color(risk: RiskBand) -> str:
    return {"SAFE": "green", "MODERATE": "orange", "DANGEROUS": "red"}[risk]


def water_contamination_level(turbidity_fnu: float, chlorophyll_ug_l: float) -> tuple[WaterBand, int]:
    score = 10
    if turbidity_fnu > 10:
        band: WaterBand = "CONTAMINATED"
        score = min(100, int(55 + turbidity_fnu * 3 + max(0.0, chlorophyll_ug_l - 5) * 5))
    elif turbidity_fnu > 5 or chlorophyll_ug_l > 5:
        band = "SUSPECT"
        score = min(85, int(35 + turbidity_fnu * 4 + chlorophyll_ug_l * 4))
    else:
        band = "CLEAN"
        score = max(0, min(40, int(turbidity_fnu * 4 + chlorophyll_ug_l * 3)))
    return band, score


def water_color(band: WaterBand) -> str:
    return {"CLEAN": "green", "SUSPECT": "orange", "CONTAMINATED": "red"}[band]


def crop_phosphate_sensitivity(crop: CropType) -> Literal["high", "low"]:
    if crop in ("vegetables", "cereals"):
        return "high"
    return "low"


def clamp_score(v: int) -> int:
    return max(0, min(100, v))


@dataclass(frozen=True)
class IrrigationFeatures:
    distance_km: float
    so2: float
    downwind: bool
    turbidity: float
    crop_sensitivity: Literal["high", "low"]


def irrigation_risk_heuristic(f: IrrigationFeatures) -> int:
    """Modèle additif type RF (poids réglés à la main) — baseline sans fichier .pkl."""
    w = 0
    w += max(0, int(35 - min(f.distance_km, 35)))
    w += int(min(35, f.so2 / 3.5))
    if f.downwind:
        w += 22
    w += int(min(20, f.turbidity * 1.2))
    if f.crop_sensitivity == "high":
        w += 12
    return clamp_score(w)


def simulate_air_gabes(*, near_gct: bool = False) -> dict[str, float]:
    if near_gct:
        so2 = random.uniform(80.0, 200.0)
    else:
        so2 = random.uniform(10.0, 40.0)
    no2 = random.uniform(8.0, 45.0) if near_gct else random.uniform(4.0, 22.0)
    nh3 = random.uniform(3.0, 18.0) if near_gct else random.uniform(1.0, 9.0)
    return {"so2": so2, "no2": no2, "nh3": nh3}


def simulate_water_gulf(*, near_industrial_plume: bool = True) -> dict[str, float]:
    if near_industrial_plume:
        turbidity = random.uniform(5.0, 15.0)
        chlorophyll = random.uniform(4.5, 8.0)
    else:
        turbidity = random.uniform(3.0, 9.0)
        chlorophyll = random.uniform(3.0, 7.0)
    return {"turbidity": turbidity, "chlorophyll": chlorophyll}


def simulate_wind() -> dict[str, float]:
    return {
        "wind_direction_10m": random.uniform(0.0, 359.0),
        "wind_speed_10m": random.uniform(4.0, 28.0),
    }


def zone_risk_score(
    *,
    zone_lat: float,
    zone_lon: float,
    so2: float,
    wind_from_deg: float,
    gct_lat: float = GCT_LAT,
    gct_lon: float = GCT_LON,
) -> int:
    dist = haversine_km(gct_lat, gct_lon, zone_lat, zone_lon)
    downwind = is_downwind_of_gct(zone_lat, zone_lon, wind_from_deg)
    score = 0
    score += max(0, int(40 - min(dist, 40)))
    score += int(min(40, so2 / 4.0))
    if downwind:
        score += 25
    return clamp_score(score)


def risk_level_label_from_score(score: int) -> str:
    if score >= 70:
        return "DANGEREUX"
    if score >= 40:
        return "MODÉRÉ"
    return "FAIBLE"
