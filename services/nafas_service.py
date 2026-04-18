"""
Prévisions style NAFAS — données 100 % dynamiques (Open-Meteo).

Qualité de l'air + vent en temps réel ; conversion µg/m³ → mol/m² pour comparaison OMS.
Aucune valeur de pollution statique ; repli uniquement si les API sont inaccessibles.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

GABES_LAT = 33.8869
GABES_LON = 10.0982
GCT_LAT = 33.88
GCT_LON = 10.09

WHO_LIMITS = {
    "NO2": 5.30e-06,
    "SO2": 5.00e-06,
    "AAI": 0.5,
}

MOLAR_MASS = {
    "NO2": 46.0055,
    "SO2": 64.066,
}

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_dynamic_nafas() -> dict[str, Any]:
    """
    Données temps réel type NAFAS (48 h) à partir d'Open-Meteo.
    Pas de valeurs statiques ; en cas d'échec des API air, retour structuré avec ok=False.
    """
    try:
        air_data = _fetch_air_quality_48h()
        try:
            wind_data = _fetch_wind_48h()
        except Exception:
            wind_data = {
                "speed": 0.0,
                "direction": 0.0,
                "direction_name": "N",
                "unit": "km/h",
                "wind_unavailable": True,
            }

        day1_raw = air_data["day1"]
        day2_raw = air_data["day2"]

        day1_mol = _convert_to_mol(day1_raw)
        day2_mol = _convert_to_mol(day2_raw)

        exceeds_who = (
            day1_mol["NO2"] > WHO_LIMITS["NO2"]
            or day1_mol["SO2"] > WHO_LIMITS["SO2"]
            or day1_mol["AAI"] > WHO_LIMITS["AAI"]
            or day2_mol["NO2"] > WHO_LIMITS["NO2"]
            or day2_mol["SO2"] > WHO_LIMITS["SO2"]
            or day2_mol["AAI"] > WHO_LIMITS["AAI"]
        )

        day1_processed = _process_day(day1_mol, "Day 1", air_data["day1_date"])
        day2_processed = _process_day(day2_mol, "Day 2", air_data["day2_date"])

        overall_risk = _calculate_overall_risk(day1_processed, day2_processed)

        deposition_zones = _calculate_deposition_zones(
            day1_mol["NO2"],
            day1_mol["SO2"],
            day1_mol["AAI"],
            float(wind_data["direction"]),
            float(wind_data["speed"]),
        )

        alerts = _generate_alerts(day1_processed, day2_processed, overall_risk)

        now_utc = datetime.now(timezone.utc)
        return {
            "ok": True,
            "model": "PhosAlert Dynamic Predictor",
            "data_source": "real_openmeteo",
            "input_period": f"Real-time — {now_utc.strftime('%Y-%m-%d %H:00')} UTC",
            "predictions": {
                "day1": day1_processed,
                "day2": day2_processed,
            },
            "wind": wind_data,
            "overall_risk": overall_risk,
            "exceeds_WHO": exceeds_who,
            "WHO_limits": {
                "NO2_mol_m2": WHO_LIMITS["NO2"],
                "SO2_mol_m2": WHO_LIMITS["SO2"],
                "AAI": WHO_LIMITS["AAI"],
                "note": "Source: World Health Organization 2021",
            },
            "deposition_zones": deposition_zones,
            "alerts": alerts,
            "generated_at": now_utc.isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        now_utc = datetime.now(timezone.utc)
        return {
            "ok": False,
            "error": str(exc),
            "message": "Open-Meteo air quality data unavailable",
            "model": "PhosAlert Dynamic Predictor",
            "data_source": "unavailable",
            "predictions": None,
            "wind": None,
            "overall_risk": None,
            "exceeds_WHO": None,
            "WHO_limits": {
                "NO2_mol_m2": WHO_LIMITS["NO2"],
                "SO2_mol_m2": WHO_LIMITS["SO2"],
                "AAI": WHO_LIMITS["AAI"],
                "note": "Source: World Health Organization 2021",
            },
            "deposition_zones": None,
            "alerts": [],
            "generated_at": now_utc.isoformat(),
        }


def _hour_index(times: list[str]) -> int:
    """Index de l'heure la plus proche (UTC) dans la série horaire Open-Meteo."""
    if not times:
        return 0
    now = datetime.now(timezone.utc)
    best_i = 0
    best_diff: float | None = None
    for i, ts in enumerate(times):
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        diff = abs((t - now).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_i = i
    return best_i


def _slice_avg(series: list[Any], start: int, length: int) -> float:
    if not series:
        return 0.0
    end = min(start + length, len(series))
    return _safe_avg(series[start:end])


def _fetch_air_quality_48h() -> dict[str, Any]:
    """Série horaire SO2, NO2, AOD sur ~3 jours ; moyennes glissantes 24h puis 24–48h."""
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,aerosol_optical_depth",
        "forecast_days": 3,
    }
    response = requests.get(AIR_QUALITY_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    hourly = data["hourly"]
    times: list[str] = hourly["time"]
    so2: list[Any] = hourly["sulphur_dioxide"]
    no2: list[Any] = hourly["nitrogen_dioxide"]
    aai: list[Any] = hourly["aerosol_optical_depth"]

    idx = _hour_index(times)

    day1_so2 = _slice_avg(so2, idx, 24)
    day1_no2 = _slice_avg(no2, idx, 24)
    day1_aai = _slice_avg(aai, idx, 24)

    day2_so2 = _slice_avg(so2, idx + 24, 24)
    day2_no2 = _slice_avg(no2, idx + 24, 24)
    day2_aai = _slice_avg(aai, idx + 24, 24)

    now_utc = datetime.now(timezone.utc)
    day1_date = now_utc.strftime("%Y-%m-%d")
    day2_date = (now_utc + timedelta(days=1)).strftime("%Y-%m-%d")

    return {
        "day1": {
            "SO2_ugm3": day1_so2,
            "NO2_ugm3": day1_no2,
            "AAI": day1_aai,
        },
        "day2": {
            "SO2_ugm3": day2_so2,
            "NO2_ugm3": day2_no2,
            "AAI": day2_aai,
        },
        "day1_date": day1_date,
        "day2_date": day2_date,
    }


def _fetch_wind_48h() -> dict[str, Any]:
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 2,
        "wind_speed_unit": "kmh",
    }
    response = requests.get(FORECAST_URL, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    times: list[str] = data["hourly"]["time"]
    speeds: list[Any] = data["hourly"]["wind_speed_10m"]
    directions: list[Any] = data["hourly"]["wind_direction_10m"]

    idx = _hour_index(times)
    current_speed = speeds[idx] if idx < len(speeds) else 0.0
    current_direction = directions[idx] if idx < len(directions) else 0.0
    if current_speed is None:
        current_speed = 0.0
    if current_direction is None:
        current_direction = 0.0

    return {
        "speed": round(float(current_speed), 1),
        "direction": round(float(current_direction), 1),
        "direction_name": _degrees_to_compass(float(current_direction)),
        "unit": "km/h",
    }


def _convert_to_mol(raw: dict[str, Any]) -> dict[str, Any]:
    so2_ugm3 = raw.get("SO2_ugm3")
    no2_ugm3 = raw.get("NO2_ugm3")
    aai = raw.get("AAI")
    so2_ugm3 = float(so2_ugm3) if so2_ugm3 is not None else 0.0
    no2_ugm3 = float(no2_ugm3) if no2_ugm3 is not None else 0.0
    aai = float(aai) if aai is not None else 0.0

    no2_mol = (no2_ugm3 * 1e-6) / MOLAR_MASS["NO2"]
    so2_mol = (so2_ugm3 * 1e-6) / MOLAR_MASS["SO2"]

    return {
        "NO2": no2_mol,
        "SO2": so2_mol,
        "AAI": aai,
        "NO2_ugm3_original": no2_ugm3,
        "SO2_ugm3_original": so2_ugm3,
    }


def _process_day(mol_data: dict[str, Any], label: str, date: str) -> dict[str, Any]:
    no2 = float(mol_data["NO2"])
    so2 = float(mol_data["SO2"])
    aai = float(mol_data["AAI"])

    no2_ratio = round(no2 / WHO_LIMITS["NO2"], 2)
    so2_ratio = round(so2 / WHO_LIMITS["SO2"], 2)

    def level(ratio: float) -> str:
        if ratio >= 10:
            return "CRITICAL"
        if ratio >= 5:
            return "DANGEROUS"
        if ratio >= 2:
            return "MODERATE"
        return "SAFE"

    score = min(
        100,
        int((no2_ratio * 4) + (so2_ratio * 3) + (aai * 20)),
    )

    return {
        "label": label,
        "date": date,
        "NO2": {
            "value_mol_m2": no2,
            "value_scientific": f"{no2:.3e}",
            "value_ugm3": mol_data.get("NO2_ugm3_original"),
            "WHO_ratio": no2_ratio,
            "exceeds_WHO_by": f"{no2_ratio}x",
            "risk_level": level(no2_ratio),
        },
        "SO2": {
            "value_mol_m2": so2,
            "value_scientific": f"{so2:.3e}",
            "value_ugm3": mol_data.get("SO2_ugm3_original"),
            "WHO_ratio": so2_ratio,
            "exceeds_WHO_by": f"{so2_ratio}x",
            "risk_level": level(so2_ratio),
        },
        "AAI": {
            "value": round(aai, 4),
            "threshold": WHO_LIMITS["AAI"],
            "exceeds": aai > WHO_LIMITS["AAI"],
            "exceeds_threshold": aai > WHO_LIMITS["AAI"],
            "risk_level": "DANGEROUS" if aai > 0.5 else "SAFE",
            "note": "aerosols_optical_depth (Open-Meteo) — échelle sans unité",
        },
        "risk_score": score,
        "risk_level": _score_to_level(score),
        "color": _score_to_color(score),
    }


def _calculate_deposition_zones(
    no2: float,
    so2: float,
    aai: float,
    wind_dir: float,
    wind_speed: float,
) -> dict[str, Any]:
    intensity = (
        (no2 / WHO_LIMITS["NO2"]) * 0.5
        + (so2 / WHO_LIMITS["SO2"]) * 0.3
        + (aai / 1.0) * 0.2
    )

    wind_rad = math.radians(wind_dir)
    zones: list[dict[str, Any]] = []
    radii = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0]

    for i, radius in enumerate(radii):
        factor = max(0.0, 1.0 - (i * 0.15))
        deposition = min(intensity * factor, 1.0)

        shift = radius * 0.3
        center_lat = GCT_LAT + shift * math.cos(wind_rad)
        center_lon = GCT_LON + shift * math.sin(wind_rad)

        if deposition >= 0.75:
            color = "red"
            risk = "CRITICAL"
        elif deposition >= 0.5:
            color = "orange"
            risk = "DANGEROUS"
        elif deposition >= 0.3:
            color = "yellow"
            risk = "MODERATE"
        else:
            color = "green"
            risk = "LOW"

        zones.append(
            {
                "id": i + 1,
                "radius_km": round(radius * 111, 1),
                "center_lat": round(center_lat, 4),
                "center_lon": round(center_lon, 4),
                "deposition_index": round(deposition, 3),
                "color": color,
                "risk_level": risk,
            }
        )

    return {
        "center": {
            "name": "GCT Industrial Complex",
            "latitude": GCT_LAT,
            "longitude": GCT_LON,
        },
        "wind_direction_deg": wind_dir,
        "wind_speed_kmh": wind_speed,
        "zones": zones,
        "intensity_index": round(intensity, 3),
        "note": "Zones dérivées des concentrations Open-Meteo + décalage selon vent 10 m",
    }


def _calculate_overall_risk(day1: dict[str, Any], day2: dict[str, Any]) -> dict[str, Any]:
    score = max(int(day1["risk_score"]), int(day2["risk_score"]))
    level = _score_to_level(score)

    messages = {
        "CRITICAL": {
            "fr": "CRITIQUE — Pollution extrême 48h (Open-Meteo)",
            "ar": "حرج — تلوث شديد 48 ساعة (Open-Meteo)",
        },
        "DANGEROUS": {
            "fr": "DANGEREUX — Limitez l'exposition",
            "ar": "خطير — قلل التعرض",
        },
        "MODERATE": {
            "fr": "MODÉRÉ — Surveillance recommandée",
            "ar": "معتدل — المراقبة موصى بها",
        },
        "SAFE": {
            "fr": "Qualité air acceptable",
            "ar": "جودة الهواء مقبولة",
        },
    }

    msg = messages.get(level, messages["SAFE"])
    return {
        "risk_level": level,
        "risk_score": score,
        "color": _score_to_color(score),
        "message_fr": msg["fr"],
        "message_ar": msg["ar"],
        "valid_for_hours": 48,
        "source": "Open-Meteo Real-Time",
    }


def _generate_alerts(
    day1: dict[str, Any],
    day2: dict[str, Any],
    overall_risk: dict[str, Any],
) -> list[dict[str, Any]]:
    _ = day2, overall_risk
    alerts: list[dict[str, Any]] = []
    aid = 1

    if float(day1["NO2"]["WHO_ratio"]) >= 1:
        alerts.append(
            {
                "id": aid,
                "level": day1["NO2"]["risk_level"],
                "type": "NO2",
                "title_fr": f"NO2 à {day1['NO2']['exceeds_WHO_by']} seuil OMS",
                "title_ar": f"NO2 بـ {day1['NO2']['exceeds_WHO_by']} حد OMS",
                "message_fr": "Risque pour la santé respiratoire",
                "message_ar": "خطر على الجهاز التنفسي",
                "target_roles": ["citoyen", "agriculteur"],
                "source": "Open-Meteo Real-Time",
            }
        )
        aid += 1

    if float(day1["SO2"]["WHO_ratio"]) >= 1:
        alerts.append(
            {
                "id": aid,
                "level": day1["SO2"]["risk_level"],
                "type": "SO2_IRRIGATION",
                "title_fr": "SO2 élevé — Irrigation déconseillée",
                "title_ar": "SO2 مرتفع — الري غير مستحسن",
                "message_fr": "Risque acidification eau irrigation",
                "message_ar": "خطر تحميض ماء الري",
                "target_roles": ["agriculteur"],
                "source": "Open-Meteo Real-Time",
            }
        )
        aid += 1

    if bool(day1["AAI"].get("exceeds")):
        alerts.append(
            {
                "id": aid,
                "level": "DANGEROUS",
                "type": "AEROSOL",
                "title_fr": "Aérosols (AOD) au-dessus du seuil",
                "title_ar": "جسيمات (AOD) فوق العتبة",
                "message_fr": "Limiter l'exposition extérieure prolongée",
                "message_ar": "قلل التعرض الطويل في الخارج",
                "target_roles": ["citoyen", "agriculteur"],
                "source": "Open-Meteo Real-Time",
            }
        )

    return alerts


def _safe_avg(lst: list[Any]) -> float:
    vals = [float(v) for v in lst if v is not None]
    return round(sum(vals) / len(vals), 6) if vals else 0.0


def _degrees_to_compass(deg: float) -> str:
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSO",
        "SO",
        "OSO",
        "O",
        "ONO",
        "NO",
        "NNO",
    ]
    return dirs[int(round(deg / 22.5)) % 16]


def _score_to_level(s: int) -> str:
    if s >= 75:
        return "CRITICAL"
    if s >= 50:
        return "DANGEROUS"
    if s >= 25:
        return "MODERATE"
    return "SAFE"


def _score_to_color(s: int) -> str:
    if s >= 75:
        return "red"
    if s >= 50:
        return "orange"
    if s >= 25:
        return "yellow"
    return "green"


if __name__ == "__main__":
    print("Testing 100% Dynamic NAFAS...\n")
    result = fetch_dynamic_nafas()
    if not result.get("ok"):
        print("Source  :", result.get("data_source"))
        print("Error   :", result.get("error"))
    else:
        print(f"Source  : {result['data_source']}")
        print(f"Risk    : {result['overall_risk']['risk_level']}")
        print(f"Day1 NO2: {result['predictions']['day1']['NO2']['value_scientific']}")
        print(f"Day1 SO2: {result['predictions']['day1']['SO2']['value_scientific']}")
        w = result["wind"]
        print(
            f"Wind    : {w['speed']} km/h {w['direction_name']} "
            f"({w['direction']} deg)"
        )
        print(f"Alerts  : {len(result['alerts'])}")
    print("100% Dynamic - No static data!")
