"""
Open-Meteo Air Quality + Forecast integrations for PhosAlert (Gabès).

Provides real-time-style hourly indexing (current hour), GCT-oriented risk scoring,
wind-affected zones, simulated fallbacks, and legacy helpers used by other routes.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 10

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

GABES_LAT = 33.8869
GABES_LON = 10.0982
GCT_LAT = 33.88
GCT_LON = 10.09


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_hour_token() -> str:
    """ISO-like hour label matching Open-Meteo hourly ``time`` strings (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")


def _find_hour_index(times: list[str]) -> int:
    """Pick the index for the current UTC hour, else nearest earlier slot, else 0."""
    if not times:
        return 0
    target = _utc_hour_token()
    if target in times:
        return times.index(target)
    best = 0
    best_delta = float("inf")
    try:
        from datetime import datetime as dt

        tgt = dt.fromisoformat(target.replace("Z", ""))
        for i, t in enumerate(times):
            ts = dt.fromisoformat(str(t).replace("Z", ""))
            delta = abs((tgt - ts).total_seconds())
            if delta < best_delta:
                best_delta = delta
                best = i
    except (ValueError, TypeError):
        best = max(0, len(times) - 1)
    return best


def _latest_hourly(values: list[float | None]) -> float | None:
    """Take the last non-null hourly sample."""
    for v in reversed(values or []):
        if v is not None:
            return float(v)
    return None


# ── FETCH AIR QUALITY ──────────────────────────────────────────────────────────


def fetch_air_quality() -> dict[str, Any]:
    """
    Fetch real-time SO2, NO2, NH3 for Gabès from Open-Meteo Air Quality API.

    Uses the **current UTC hour** slot when present in the hourly arrays.
    """
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,ammonia",
        "forecast_days": 3,
    }

    try:
        response = requests.get(AIR_QUALITY_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        data = response.json()

        times = data["hourly"]["time"]
        idx = _find_hour_index(times)

        so2 = float(data["hourly"]["sulphur_dioxide"][idx] or 0.0)
        no2 = float(data["hourly"]["nitrogen_dioxide"][idx] or 0.0)
        nh3 = float(data["hourly"]["ammonia"][idx] or 0.0)

        current_time = times[idx]

        history_24h: list[dict[str, Any]] = []
        for i in range(max(0, idx - 23), idx + 1):
            history_24h.append(
                {
                    "time": times[i],
                    "so2": float(data["hourly"]["sulphur_dioxide"][i] or 0),
                    "no2": float(data["hourly"]["nitrogen_dioxide"][i] or 0),
                    "nh3": float(data["hourly"]["ammonia"][i] or 0),
                }
            )

        forecast_48h: list[dict[str, Any]] = []
        for i in range(idx, min(idx + 48, len(times))):
            forecast_48h.append(
                {
                    "time": times[i],
                    "so2": float(data["hourly"]["sulphur_dioxide"][i] or 0),
                    "no2": float(data["hourly"]["nitrogen_dioxide"][i] or 0),
                }
            )

        risk = calculate_air_risk(so2, no2, nh3)

        return {
            "so2": round(so2, 2),
            "no2": round(no2, 2),
            "nh3": round(nh3, 2),
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "color": risk["color"],
            "advice_fr": risk["advice_fr"],
            "advice_ar": risk["advice_ar"],
            "history_24h": history_24h,
            "forecast_48h": forecast_48h,
            "timestamp": current_time,
            "data_source": "real",
            "source_url": "Open-Meteo Air Quality API",
        }

    except Exception as e:  # noqa: BLE001
        logger.warning("Air Quality API error: %s", e)
        print(f"WARNING: Air Quality API error: {e}")
        return get_simulated_air_quality()


# ── FETCH WIND DATA ────────────────────────────────────────────────────────────


def fetch_wind_data() -> dict[str, Any]:
    """Fetch real-time wind speed and direction for Gabès (no API key)."""
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 1,
        "wind_speed_unit": "kmh",
    }

    try:
        response = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
        data = response.json()

        times = data["hourly"]["time"]
        idx = _find_hour_index(times)

        current_time = times[idx]

        wind_speed = float(data["hourly"]["wind_speed_10m"][idx] or 0.0)
        wind_direction = float(data["hourly"]["wind_direction_10m"][idx] or 0.0)

        wind_forecast: list[dict[str, Any]] = []
        for i in range(len(times)):
            wd = float(data["hourly"]["wind_direction_10m"][i] or 0)
            wind_forecast.append(
                {
                    "time": times[i],
                    "speed": float(data["hourly"]["wind_speed_10m"][i] or 0),
                    "direction": wd,
                    "direction_name": degrees_to_compass(wd),
                }
            )

        return {
            "wind_speed_kmh": round(wind_speed, 1),
            "wind_direction_degrees": round(wind_direction, 1),
            "wind_direction_name": degrees_to_compass(wind_direction),
            "wind_forecast_24h": wind_forecast,
            "timestamp": current_time,
            "data_source": "real",
            "source_url": "Open-Meteo Forecast API",
        }

    except Exception as e:  # noqa: BLE001
        logger.warning("Wind API error: %s", e)
        print(f"WARNING: Wind API error: {e}")
        return get_simulated_wind()


# ── COMBINED FETCH ─────────────────────────────────────────────────────────────


def fetch_all_realtime() -> dict[str, Any]:
    """
    Fetch both air quality and wind data plus zone-level wind impact.

    Intended for the Flutter dashboard (single call).
    """
    air = fetch_air_quality()
    wind = fetch_wind_data()

    affected_zones = calculate_wind_affected_zones(
        wind["wind_direction_degrees"],
        wind["wind_speed_kmh"],
        air["so2"],
    )

    return {
        "air_quality": air,
        "wind": wind,
        "affected_zones": affected_zones,
        "gct_location": {
            "latitude": GCT_LAT,
            "longitude": GCT_LON,
            "name": "GCT Ghannouch",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── RISK CALCULATION ───────────────────────────────────────────────────────────


def calculate_air_risk(so2: float, no2: float, nh3: float) -> dict[str, Any]:
    """
    Air quality risk based on GCT-oriented thresholds (EU / literature bands).

    SO2 remains the dominant signal for the phosphoric acid complex context.
    """
    score = 0

    if so2 > 100:
        score += 50
    elif so2 > 40:
        score += 30
    elif so2 > 15:
        score += 10

    if no2 > 200:
        score += 30
    elif no2 > 100:
        score += 15
    elif no2 > 40:
        score += 5

    if nh3 > 10:
        score += 20
    elif nh3 > 5:
        score += 10

    score = min(100, score)

    if score >= 60:
        return {
            "level": "DANGEROUS",
            "score": score,
            "color": "red",
            "advice_fr": "Danger ! Évitez toute activité extérieure. Ne pas irriguer.",
            "advice_ar": "خطر! تجنب أي نشاط خارجي. لا تسقي.",
        }
    if score >= 30:
        return {
            "level": "MODERATE",
            "score": score,
            "color": "orange",
            "advice_fr": "Risque modéré. Limitez l'exposition. Irriguer tôt le matin.",
            "advice_ar": "خطر معتدل. حد من التعرض. اسقِ في الصباح الباكر.",
        }
    return {
        "level": "SAFE",
        "score": score,
        "color": "green",
        "advice_fr": "Air correct. Activités normales possibles.",
        "advice_ar": "الهواء جيد. الأنشطة العادية ممكنة.",
    }


# ── WIND ZONES CALCULATION ────────────────────────────────────────────────────


def _angular_difference_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _is_downwind_zone(zone_lat: float, zone_lon: float, wind_from_degrees: float) -> bool:
    """
    ``wind_from_degrees`` is meteorological (direction wind blows **from**).
    Plume travels toward ``(wind_from + 180) % 360``.
    """
    bearing = calculate_bearing(GCT_LAT, GCT_LON, zone_lat, zone_lon)
    wind_toward = (wind_from_degrees + 180.0) % 360.0
    return _angular_difference_deg(bearing, wind_toward) < 45.0


def calculate_wind_affected_zones(wind_direction: float, wind_speed: float, so2: float) -> list[dict[str, Any]]:
    """
    Zones around GCT with heuristic risk, using correct downwind alignment
    (bearing from GCT vs plume direction).
    """
    zones = [
        {"id": 1, "name": "Zone GCT Ghannouch", "lat": 33.88, "lon": 10.09, "base_risk": 90},
        {"id": 2, "name": "Chott Essalem", "lat": 33.87, "lon": 10.08, "base_risk": 60},
        {"id": 3, "name": "Port de Gabès", "lat": 33.895, "lon": 10.11, "base_risk": 40},
        {"id": 4, "name": "Médina de Gabès", "lat": 33.8869, "lon": 10.0982, "base_risk": 30},
        {"id": 5, "name": "Zone Agricole Nord", "lat": 33.95, "lon": 10.07, "base_risk": 20},
        {"id": 6, "name": "Zone Agricole Sud", "lat": 33.82, "lon": 10.10, "base_risk": 20},
        {"id": 7, "name": "Plage de Gabès", "lat": 33.90, "lon": 10.12, "base_risk": 35},
        {"id": 8, "name": "Oasis de Gabès", "lat": 33.88, "lon": 10.06, "base_risk": 25},
    ]

    result: list[dict[str, Any]] = []
    for zone in zones:
        bearing = calculate_bearing(GCT_LAT, GCT_LON, zone["lat"], zone["lon"])
        distance = haversine_distance(GCT_LAT, GCT_LON, zone["lat"], zone["lon"])

        is_downwind = _is_downwind_zone(zone["lat"], zone["lon"], wind_direction)

        if is_downwind and wind_speed > 10:
            wind_bonus = 30
        elif is_downwind:
            wind_bonus = 15
        else:
            wind_bonus = 0

        distance_penalty = min(distance * 5, 30)
        so2_bonus = min(so2 / 5, 20)

        final_score = zone["base_risk"] + wind_bonus + so2_bonus - distance_penalty
        final_score = float(min(max(final_score, 0), 100))

        if final_score >= 60:
            level, color = "DANGEROUS", "red"
        elif final_score >= 30:
            level, color = "MODERATE", "orange"
        else:
            level, color = "SAFE", "green"

        result.append(
            {
                "id": zone["id"],
                "name": zone["name"],
                "latitude": zone["lat"],
                "longitude": zone["lon"],
                "risk_score": round(final_score),
                "risk_level": level,
                "color": color,
                "distance_from_gct_km": round(distance, 2),
                "is_downwind": is_downwind,
                "bearing_from_gct": round(bearing, 1),
            }
        )

    return result


# ── HELPER FUNCTIONS ───────────────────────────────────────────────────────────


def degrees_to_compass(degrees: float) -> str:
    """Convert meteorological wind direction (degrees) to compass label."""
    directions = [
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
    idx = int(round(degrees / 22.5) % 16)
    return directions[idx]


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 in degrees ``[0, 360)``."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlon = lon2_r - lon1_r
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360.0) % 360.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r_km = 6371.0
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return r_km * 2 * math.asin(math.sqrt(a))


# ── SIMULATED FALLBACK ───────────────────────────────────────────────────────


def get_simulated_air_quality() -> dict[str, Any]:
    """Simulated air metrics when the API fails."""
    so2 = random.uniform(60, 150)
    no2 = random.uniform(30, 80)
    nh3 = random.uniform(5, 15)
    risk = calculate_air_risk(so2, no2, nh3)

    return {
        "so2": round(so2, 2),
        "no2": round(no2, 2),
        "nh3": round(nh3, 2),
        "risk_level": risk["level"],
        "risk_score": risk["score"],
        "color": risk["color"],
        "advice_fr": risk["advice_fr"],
        "advice_ar": risk["advice_ar"],
        "history_24h": [],
        "forecast_48h": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": "simulated",
        "source_url": None,
    }


def get_simulated_wind() -> dict[str, Any]:
    """Simulated wind when the forecast API fails."""
    direction = random.uniform(0, 360)
    speed = random.uniform(5, 25)

    return {
        "wind_speed_kmh": round(speed, 1),
        "wind_direction_degrees": round(direction, 1),
        "wind_direction_name": degrees_to_compass(direction),
        "wind_forecast_24h": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": "simulated",
        "source_url": None,
    }


# ── LEGACY HELPERS (used by dashboard, prediction, chat, water) ───────────────


def fetch_air_quality_snapshot(
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
) -> tuple[dict[str, Any], bool]:
    """
    Fetch hourly SO2, NO2, NH3 for arbitrary coordinates (latest non-null hour).

    Returns ``(payload, live_ok)`` for routes that predate :func:`fetch_air_quality`.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,ammonia",
        "forecast_days": forecast_days,
    }
    try:
        r = requests.get(AIR_QUALITY_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly") or {}
        so2 = _latest_hourly(hourly.get("sulphur_dioxide") or [])
        no2 = _latest_hourly(hourly.get("nitrogen_dioxide") or [])
        nh3 = _latest_hourly(hourly.get("ammonia") or [])
        times = hourly.get("time") or []
        ts = times[-1] if times else _iso_now()
        if so2 is None and no2 is None and nh3 is None:
            return {"raw": data, "timestamp": ts}, False
        return {
            "so2": so2,
            "no2": no2,
            "nh3": nh3,
            "timestamp": ts,
            "raw": data,
        }, True
    except (requests.RequestException, ValueError, KeyError):
        return {"timestamp": _iso_now()}, False


def fetch_air_quality_history(
    latitude: float,
    longitude: float,
    past_days: int = 1,
) -> tuple[list[dict[str, Any]], bool]:
    """Hourly SO2 series for trend charts (last ~past_days)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "sulphur_dioxide",
        "past_days": past_days,
    }
    try:
        r = requests.get(AIR_QUALITY_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly") or {}
        times: list[str] = hourly.get("time") or []
        series = hourly.get("sulphur_dioxide") or []
        out: list[dict[str, Any]] = []
        for i, t in enumerate(times):
            val = series[i] if i < len(series) else None
            if val is not None:
                try:
                    hr = int(t[11:13]) if len(t) >= 13 else i % 24
                except (ValueError, TypeError):
                    hr = i % 24
                out.append({"hour": hr, "so2": float(val), "time": t})
        return out[-24:], True
    except (requests.RequestException, ValueError, TypeError, IndexError):
        return [], False


def fetch_wind_snapshot(latitude: float, longitude: float, forecast_days: int = 1) -> tuple[dict[str, Any], bool]:
    """Wind speed (km/h) and direction (degrees FROM) — latest non-null hour."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": forecast_days,
        "wind_speed_unit": "kmh",
    }
    try:
        r = requests.get(FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly") or {}
        wd = _latest_hourly(hourly.get("wind_direction_10m") or [])
        ws = _latest_hourly(hourly.get("wind_speed_10m") or [])
        times = hourly.get("time") or []
        ts = times[-1] if times else _iso_now()
        if wd is None or ws is None:
            return {"timestamp": ts}, False
        return {"wind_direction": wd, "wind_speed": ws, "timestamp": ts}, True
    except (requests.RequestException, ValueError):
        return {"timestamp": _iso_now()}, False


def fetch_air_quality_hourly_forecast(
    latitude: float,
    longitude: float,
    hours: int = 48,
    forecast_days: int = 3,
) -> tuple[list[dict[str, Any]], bool]:
    """Next ``hours`` forecast points of SO₂ for irrigation projection."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "sulphur_dioxide",
        "forecast_days": forecast_days,
    }
    try:
        r = requests.get(AIR_QUALITY_URL, params=params, timeout=REQUEST_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly") or {}
        times: list[str] = hourly.get("time") or []
        series = hourly.get("sulphur_dioxide") or []
        out: list[dict[str, Any]] = []
        for i, t in enumerate(times[:hours]):
            val = series[i] if i < len(series) else None
            if val is None:
                continue
            try:
                hr = int(t[11:13]) if len(t) >= 13 else i % 24
            except (ValueError, TypeError):
                hr = i % 24
            out.append({"hour_index": i, "hour_of_day": hr, "so2": float(val)})
        return out[:hours], True
    except (requests.RequestException, ValueError, TypeError, IndexError):
        return [], False


def fetch_marine_snapshot(latitude: float, longitude: float) -> tuple[dict[str, Any], bool]:
    """Placeholder until marine chemistry is wired (see Copernicus integration)."""
    _ = (latitude, longitude)
    return {"timestamp": _iso_now()}, False


if __name__ == "__main__":
    import sys

    # Windows consoles often default to cp1252; UTF-8 avoids UnicodeEncodeError for symbols.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("Testing Open-Meteo APIs for Gabes...\n")

    print("[1] Air Quality API...")
    air = fetch_air_quality()
    print(f"   SO2 : {air['so2']} ug/m3")
    print(f"   NO2 : {air['no2']} ug/m3")
    print(f"   NH3 : {air['nh3']} ug/m3")
    print(f"   Risk: {air['risk_level']} {air['color']}")
    print(f"   Source: {air['data_source']}")

    print("\n[2] Wind API...")
    wind = fetch_wind_data()
    print(f"   Speed    : {wind['wind_speed_kmh']} km/h")
    print(f"   Direction: {wind['wind_direction_degrees']} deg ({wind['wind_direction_name']})")
    print(f"   Source: {wind['data_source']}")

    print("\n[3] Combined fetch_all_realtime()...")
    combined = fetch_all_realtime()
    print(f"   Zones affected: {len(combined['affected_zones'])}")
    for zone in combined["affected_zones"]:
        tag = "[D]" if zone["risk_level"] == "DANGEROUS" else "[M]" if zone["risk_level"] == "MODERATE" else "[S]"
        suffix = " (downwind)" if zone["is_downwind"] else ""
        print(f"   {tag} {zone['name']}: {zone['risk_score']}/100{suffix}")

    print("\nDone.")
