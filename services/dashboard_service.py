"""
Tableaux de bord par rôle — agrégation 100 % dynamique (Open-Meteo, CSV eau, NAFAS, agriculture).
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import phosalert_model as pm
import requests

from services.gabes_zone_scores import build_unified_zone_rows

GABES_LAT = 33.8869
GABES_LON = 10.0982
GCT_LAT = 33.88
GCT_LON = 10.09

# Seuils indicatifs µg/m³ (guidelines air — comparaisons dashboard)
WHO_LIMITS_UGM3 = {
    "NO2": 40.0,
    "SO2": 20.0,
    "NH3": 1.0,
}

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def _hour_index(times: list[str]) -> int:
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


def _fetch_current_air() -> dict[str, Any]:
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,ammonia",
        "forecast_days": 3,
    }
    resp = requests.get(AIR_QUALITY_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    hourly = data["hourly"]
    times: list[str] = hourly["time"]
    so2: list[Any] = hourly["sulphur_dioxide"]
    no2: list[Any] = hourly["nitrogen_dioxide"]
    nh3: list[Any] = hourly["ammonia"]

    idx = _hour_index(times)
    current_so2 = float(so2[idx] or 0.0) if idx < len(so2) else 0.0
    current_no2 = float(no2[idx] or 0.0) if idx < len(no2) else 0.0
    current_nh3 = float(nh3[idx] or 0.0) if idx < len(nh3) else 0.0

    score = 0
    if current_so2 > WHO_LIMITS_UGM3["SO2"]:
        score += 40
    elif current_so2 > WHO_LIMITS_UGM3["SO2"] * 0.5:
        score += 20
    if current_no2 > WHO_LIMITS_UGM3["NO2"]:
        score += 35
    elif current_no2 > WHO_LIMITS_UGM3["NO2"] * 0.5:
        score += 15
    if current_nh3 > WHO_LIMITS_UGM3["NH3"]:
        score += 25

    if score >= 60:
        risk, color = "DANGEROUS", "red"
    elif score >= 30:
        risk, color = "MODERATE", "orange"
    else:
        risk, color = "SAFE", "green"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    forecast: list[dict[str, Any]] = []
    for i in range(idx, min(idx + 48, len(times))):
        forecast.append(
            {
                "time": times[i],
                "so2": float(so2[i] or 0.0) if i < len(so2) else 0.0,
                "no2": float(no2[i] or 0.0) if i < len(no2) else 0.0,
                "nh3": float(nh3[i] or 0.0) if i < len(nh3) else 0.0,
            }
        )

    return {
        "so2_ugm3": round(current_so2, 2),
        "no2_ugm3": round(current_no2, 2),
        "nh3_ugm3": round(current_nh3, 2),
        "risk_level": risk,
        "risk_score": score,
        "color": color,
        "forecast_48h": forecast,
        "who_limits_ugm3": WHO_LIMITS_UGM3,
        "timestamp": now_str,
        "source": "Open-Meteo Real-Time",
    }


def _fetch_wind() -> dict[str, Any]:
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 1,
        "wind_speed_unit": "kmh",
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    times: list[str] = data["hourly"]["time"]
    speeds: list[Any] = data["hourly"]["wind_speed_10m"]
    dirs: list[Any] = data["hourly"]["wind_direction_10m"]
    idx = _hour_index(times)
    speed = float(speeds[idx] or 0.0) if idx < len(speeds) else 0.0
    direc = float(dirs[idx] or 0.0) if idx < len(dirs) else 0.0
    return {
        "speed_kmh": round(speed, 1),
        "direction_deg": round(direc, 1),
        "direction_name": _degrees_to_compass(direc),
        "source": "Open-Meteo Real-Time",
    }


def _fetch_historical_24h() -> list[dict[str, Any]]:
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,ammonia",
        "past_days": 1,
        "forecast_days": 0,
    }
    try:
        resp = requests.get(AIR_QUALITY_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        times: list[str] = hourly["time"]
        so2: list[Any] = hourly["sulphur_dioxide"]
        no2: list[Any] = hourly["nitrogen_dioxide"]
        nh3: list[Any] = hourly["ammonia"]
        history: list[dict[str, Any]] = []
        for i in range(len(times)):
            history.append(
                {
                    "time": times[i],
                    "so2": float(so2[i] or 0.0) if i < len(so2) else 0.0,
                    "no2": float(no2[i] or 0.0) if i < len(no2) else 0.0,
                    "nh3": float(nh3[i] or 0.0) if i < len(nh3) else 0.0,
                }
            )
        return history
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def _water_from_csv(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        turs = [float(r["TUR"]) for r in rows if r.get("TUR")]
        chls = [float(r["CHL"]) for r in rows if r.get("CHL")]
        spms = [float(r["SPM"]) for r in rows if r.get("SPM")]
        if not turs:
            return None
        avg_tur = sum(turs) / len(turs)
        avg_chl = sum(chls) / len(chls) if chls else 0.0
        avg_spm = sum(spms) / len(spms) if spms else 0.0
        band, _wscore = pm.water_contamination_level(avg_tur, avg_chl)
        color = pm.water_color(band)
        return {
            "turbidity_FNU": round(avg_tur, 2),
            "chlorophyll_ugL": round(avg_chl, 2),
            "SPM_mgL": round(avg_spm, 2),
            "contamination_level": band,
            "color": color,
            "source": str(path.as_posix()),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _fetch_water_dynamic() -> dict[str, Any]:
    """CSV projet (moyennes) ; sinon chaîne modèle (même logique que ``/api/water-quality``)."""
    csv_path = _ROOT / "data" / "gabes_water_quality_simulated.csv"
    got = _water_from_csv(csv_path)
    if got is not None:
        return got

    lat, lon = pm.GABES_LAT, pm.GABES_LON
    turbidity: float | None = None
    chlorophyll: float | None = None
    data_source = "simulated_phosalert"
    sim = pm.simulate_water_gulf(near_industrial_plume=True)
    turbidity = float(sim["turbidity"])
    chlorophyll = float(sim["chlorophyll"])
    band, _ = pm.water_contamination_level(turbidity, chlorophyll)
    return {
        "turbidity_FNU": round(turbidity, 2),
        "chlorophyll_ugL": round(chlorophyll, 2),
        "SPM_mgL": None,
        "contamination_level": band,
        "color": pm.water_color(band),
        "source": data_source,
    }


def _fetch_nafas_safe() -> dict[str, Any] | None:
    try:
        from services.nafas_service import fetch_dynamic_nafas

        return fetch_dynamic_nafas()
    except Exception:  # noqa: BLE001
        return None


def _calculate_zones(air: dict[str, Any], wind: dict[str, Any]) -> list[dict[str, Any]]:
    """Même liste et même score que ``GET /api/map/zones`` (voir ``gabes_zone_scores``)."""
    so2 = float(air["so2_ugm3"])
    wind_dir = float(wind["direction_deg"])
    wind_speed = float(wind["speed_kmh"])
    return build_unified_zone_rows(so2, wind_dir, wind_speed)


def _generate_alerts_dynamic(
    air: dict[str, Any],
    water: dict[str, Any],
    nafas: dict[str, Any] | None,
    role: str,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    aid = 1
    so2 = float(air["so2_ugm3"])
    no2 = float(air["no2_ugm3"])
    nh3 = float(air["nh3_ugm3"])
    _ = no2

    if so2 > WHO_LIMITS_UGM3["SO2"]:
        alerts.append(
            {
                "id": aid,
                "type": "SO2_HIGH",
                "level": "DANGEROUS",
                "color": "red",
                "title_fr": f"SO2 élevé: {so2:.1f} µg/m³ (seuil indicatif: {WHO_LIMITS_UGM3['SO2']})",
                "title_ar": f"SO2 مرتفع: {so2:.1f} µg/m³",
                "roles": ["citoyen", "agriculteur", "chercheur_scientifique"],
            }
        )
        aid += 1

    if so2 > 40 and role == "agriculteur":
        alerts.append(
            {
                "id": aid,
                "type": "IRRIGATION_RISK",
                "level": "WARNING",
                "color": "orange",
                "title_fr": f"SO2={so2:.1f} µg/m³ — prudence irrigation",
                "title_ar": f"SO2={so2:.1f} µg/m³ — احذر من الري",
                "roles": ["agriculteur"],
            }
        )
        aid += 1

    if water["contamination_level"] == "CONTAMINATED":
        alerts.append(
            {
                "id": aid,
                "type": "WATER_CONTAMINATED",
                "level": "DANGEROUS",
                "color": "red",
                "title_fr": f"Eau côtière / fichier — turbidité moy. {water['turbidity_FNU']} FNU",
                "title_ar": f"مياه ساحلية — عكارة {water['turbidity_FNU']} FNU",
                "roles": ["citoyen", "agriculteur", "chercheur_scientifique"],
            }
        )
        aid += 1

    if nafas and nafas.get("ok") and nafas.get("exceeds_WHO"):
        alerts.append(
            {
                "id": aid,
                "type": "WHO_EXCEEDED",
                "level": "CRITICAL",
                "color": "red",
                "title_fr": "NAFAS: dépassement seuils (mol/m²) — fenêtre 48h",
                "title_ar": "NAFAS: تجاوز عتبات — 48 ساعة",
                "roles": ["citoyen", "agriculteur", "chercheur_scientifique"],
            }
        )
        aid += 1

    if nh3 > WHO_LIMITS_UGM3["NH3"]:
        alerts.append(
            {
                "id": aid,
                "type": "NH3_HIGH",
                "level": "WARNING",
                "color": "orange",
                "title_fr": f"NH3: {nh3:.2f} µg/m³ — risque respiratoire",
                "title_ar": f"NH3: {nh3:.2f} µg/m³",
                "roles": ["citoyen", "agriculteur", "chercheur_scientifique"],
            }
        )
        aid += 1

    return [a for a in alerts if role in a.get("roles", [])]


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


def _water_quantity_L(crop: str, risk_score: int) -> float:
    base = 4500.0 if crop in ("vegetables", "cereals") else 2800.0
    return round(base * (1.15 - min(risk_score, 85) / 220.0), 1)


def _fetch_precipitation_calendar_7d(lat: float, lon: float) -> list[dict[str, Any]]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "forecast_days": 7,
    }
    try:
        r = requests.get(FORECAST_URL, params=params, timeout=15)
        r.raise_for_status()
        d = r.json()
        daily = d.get("daily") or {}
        times = daily.get("time") or []
        prec = daily.get("precipitation_sum") or []
        out: list[dict[str, Any]] = []
        for i in range(min(7, len(times))):
            v = prec[i] if i < len(prec) else 0.0
            out.append({"date": times[i], "precipitation_mm": round(float(v or 0.0), 2)})
        return out
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return []


def build_citoyen_dashboard() -> dict[str, Any]:
    air = _fetch_current_air()
    wind = _fetch_wind()
    water = _fetch_water_dynamic()
    nafas = _fetch_nafas_safe()
    zones = _calculate_zones(air, wind)
    alerts = _generate_alerts_dynamic(air, water, nafas, "citoyen")
    safe_zones = [z for z in zones if z["is_safe"]]

    so2 = air["so2_ugm3"]
    lim = WHO_LIMITS_UGM3["SO2"]
    if so2 > lim * 2:
        advice_fr = f"Restez à l'intérieur si possible. SO2 à {so2:.1f} µg/m³."
        advice_ar = f"ابق في المنزل إن أمكن. SO2 {so2:.1f} µg/m³."
    elif so2 > lim:
        advice_fr = f"Limitez l'exposition extérieure. SO2: {so2:.1f} µg/m³."
        advice_ar = f"قلل التعرض. SO2: {so2:.1f} µg/m³."
    else:
        advice_fr = "Air dans une plage acceptable pour les activités extérieures courantes."
        advice_ar = "الهواء مقبول للأنشطة الخارجية العادية."

    wq = water["contamination_level"]
    advice_water_fr = "Évitez la baignade" if wq == "CONTAMINATED" else "Surveillez les avis locaux sur la qualité des eaux."
    return {
        "role": "citoyen",
        "air_quality": air,
        "wind": wind,
        "safe_zones": safe_zones,
        "all_zones": zones,
        "alerts": alerts,
        "advice_fr": advice_fr,
        "advice_ar": advice_ar,
        "water_quality": {
            "contamination_level": wq,
            "color": water["color"],
            "advice_fr": advice_water_fr,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "Open-Meteo Real-Time",
    }


def build_agriculteur_dashboard(
    crop: str = "olive",
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    from services.agriculture_service import crops_for_location, recommend_agriculture

    farm_lat = lat if lat is not None else GABES_LAT
    farm_lon = lon if lon is not None else GABES_LON

    air = _fetch_current_air()
    wind = _fetch_wind()
    water = _fetch_water_dynamic()
    nafas = _fetch_nafas_safe()
    zones = _calculate_zones(air, wind)
    alerts = _generate_alerts_dynamic(air, water, nafas, "agriculteur")

    try:
        agri = recommend_agriculture(crop, farm_lat, farm_lon)
        irr = agri["irrigation"]
        agri_err = None
    except Exception as exc:  # noqa: BLE001
        agri = {}
        irr = {}
        agri_err = str(exc)

    risk_score = int(irr.get("risk_score", 0))
    calendar = _fetch_precipitation_calendar_7d(farm_lat, farm_lon)
    try:
        alt = crops_for_location(farm_lat, farm_lon)
        alts = [c for c in alt.get("crops", []) if c.get("id") != crop][:3]
    except Exception:  # noqa: BLE001
        alts = []

    tips_fr = " ".join(agri.get("tips_fr", [])) if agri.get("tips_fr") else ""
    tips_ar = " ".join(agri.get("tips_ar", [])) if agri.get("tips_ar") else ""
    reasons_txt = "; ".join(irr.get("reasons", [])) if irr.get("reasons") else ""

    return {
        "role": "agriculteur",
        "air_quality": {
            "so2_ugm3": air["so2_ugm3"],
            "no2_ugm3": air["no2_ugm3"],
            "nh3_ugm3": air["nh3_ugm3"],
            "risk_level": air["risk_level"],
            "color": air["color"],
        },
        "wind": wind,
        "irrigation_recommend": {
            "irrigate_today": irr.get("irrigate_recommended", False),
            "best_time": irr.get("best_time_window", "06:00-08:00"),
            "water_quantity_L": _water_quantity_L(crop, risk_score),
            "risk_level": irr.get("risk_level_fr", "UNKNOWN"),
            "advice_fr": tips_fr or reasons_txt,
            "advice_ar": tips_ar,
        },
        "calendar_7days": calendar,
        "alternative_crops": alts,
        "water_quality": water,
        "alerts": alerts,
        "decision_factors": {
            "distance_km_gct": agri.get("distance_km_gct"),
            "downwind": agri.get("wind", {}).get("downwind_from_gct") if agri.get("wind") else None,
            "so2_ug_m3": agri.get("air", {}).get("so2_ug_m3") if agri.get("air") else air["so2_ugm3"],
            "irrigation_risk_score": risk_score,
        },
        "agriculture_error": agri_err,
        "zones_summary": zones[:4],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "Open-Meteo Real-Time + NAFAS + agriculture_service",
    }


def build_chercheur_dashboard() -> dict[str, Any]:
    air = _fetch_current_air()
    wind = _fetch_wind()
    water = _fetch_water_dynamic()
    nafas = _fetch_nafas_safe()
    history = _fetch_historical_24h()
    zones = _calculate_zones(air, wind)
    alerts = _generate_alerts_dynamic(air, water, nafas, "chercheur_scientifique")

    who_comparison = {
        "SO2": {
            "measured_ugm3": air["so2_ugm3"],
            "who_limit_ugm3": WHO_LIMITS_UGM3["SO2"],
            "ratio": round(air["so2_ugm3"] / WHO_LIMITS_UGM3["SO2"], 4)
            if WHO_LIMITS_UGM3["SO2"]
            else None,
            "exceeds": air["so2_ugm3"] > WHO_LIMITS_UGM3["SO2"],
            "exceeds_by": f"{air['so2_ugm3'] / WHO_LIMITS_UGM3['SO2']:.2f}x",
        },
        "NO2": {
            "measured_ugm3": air["no2_ugm3"],
            "who_limit_ugm3": WHO_LIMITS_UGM3["NO2"],
            "ratio": round(air["no2_ugm3"] / WHO_LIMITS_UGM3["NO2"], 4)
            if WHO_LIMITS_UGM3["NO2"]
            else None,
            "exceeds": air["no2_ugm3"] > WHO_LIMITS_UGM3["NO2"],
            "exceeds_by": f"{air['no2_ugm3'] / WHO_LIMITS_UGM3['NO2']:.2f}x",
        },
        "NH3": {
            "measured_ugm3": air["nh3_ugm3"],
            "who_limit_ugm3": WHO_LIMITS_UGM3["NH3"],
            "ratio": round(air["nh3_ugm3"] / WHO_LIMITS_UGM3["NH3"], 4)
            if WHO_LIMITS_UGM3["NH3"]
            else None,
            "exceeds": air["nh3_ugm3"] > WHO_LIMITS_UGM3["NH3"],
        },
        "water_turbidity": {
            "measured_FNU": water["turbidity_FNU"],
            "safe_limit_FNU": 5.0,
            "ratio": round(water["turbidity_FNU"] / 5.0, 4) if water["turbidity_FNU"] is not None else None,
            "exceeds": float(water["turbidity_FNU"]) > 5.0,
        },
        "source": "Indicative thresholds for dashboard comparison (µg/m³)",
    }

    nafas_raw = None
    if nafas and nafas.get("ok"):
        nafas_raw = {
            "model": nafas.get("model"),
            "data_source": nafas.get("data_source"),
            "input_period": nafas.get("input_period"),
            "predictions": nafas.get("predictions"),
            "exceeds_WHO": nafas.get("exceeds_WHO"),
            "deposition_zones": nafas.get("deposition_zones"),
            "generated_at": nafas.get("generated_at"),
        }

    stats_24h: dict[str, Any] = {}
    if history:
        so2_vals = [h["so2"] for h in history if h.get("so2") is not None]
        no2_vals = [h["no2"] for h in history if h.get("no2") is not None]
        if so2_vals:
            stats_24h["so2"] = {
                "avg": round(sum(so2_vals) / len(so2_vals), 2),
                "max": round(max(so2_vals), 2),
                "min": round(min(so2_vals), 2),
                "hours_above_who": sum(1 for v in so2_vals if v > WHO_LIMITS_UGM3["SO2"]),
            }
        if no2_vals:
            stats_24h["no2"] = {
                "avg": round(sum(no2_vals) / len(no2_vals), 2),
                "max": round(max(no2_vals), 2),
                "min": round(min(no2_vals), 2),
                "hours_above_who": sum(1 for v in no2_vals if v > WHO_LIMITS_UGM3["NO2"]),
            }

    return {
        "role": "chercheur_scientifique",
        "air_quality": air,
        "wind": wind,
        "nafas_raw_data": nafas_raw,
        "water_quality": water,
        "historical_24h": history,
        "stats_24h": stats_24h,
        "who_comparison": who_comparison,
        "all_zones": zones,
        "alerts": alerts,
        "gct_reference": {
            "latitude": GCT_LAT,
            "longitude": GCT_LON,
            "name": "GCT Industrial Complex, Ghannouch",
            "note": "WGS84 — inventaires d’émissions : sources CAMS / littérature scientifique séparées",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": [
            "Open-Meteo Air Quality API",
            "Open-Meteo Forecast API",
            "NAFAS dynamic (Open-Meteo)",
            "Water: project CSV or phosalert simulation",
            "Agriculture: phosalert_model + Open-Meteo",
        ],
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("Testing Role-Based Dashboard...\n")
    print("=" * 40)
    print("CITOYEN Dashboard:")
    c = build_citoyen_dashboard()
    print(f"  Air risk   : {c['air_quality']['risk_level']}")
    print(f"  Safe zones : {len(c['safe_zones'])}")
    print(f"  Alerts     : {len(c['alerts'])}")

    print("\n" + "=" * 40)
    print("AGRICULTEUR Dashboard:")
    a = build_agriculteur_dashboard("olive")
    print(f"  Irrigate   : {a['irrigation_recommend']['irrigate_today']}")
    print(f"  Best time  : {a['irrigation_recommend']['best_time']}")
    print(f"  Calendar   : {len(a['calendar_7days'])} days")
    print(f"  Alerts     : {len(a['alerts'])}")

    print("\n" + "=" * 40)
    print("CHERCHEUR Dashboard:")
    r = build_chercheur_dashboard()
    print(f"  History    : {len(r['historical_24h'])} points")
    print(f"  SO2 ratio  : {r['who_comparison']['SO2']['ratio']}x")
    print(f"  NAFAS      : {'yes' if r['nafas_raw_data'] else 'no'}")
    print(f"  Stats 24h  : {bool(r['stats_24h'])}")
    print("\nRole-Based Dashboard - 100% Dynamic!")
