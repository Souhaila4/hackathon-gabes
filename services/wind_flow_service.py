"""
Vent — grille U/V Open-Meteo, panache indicatif GCT, paramètres d’animation carte.

Source : https://api.open-meteo.com/v1/forecast (sans clé API).
Les trajectoires panache sont **indicatives** (simplification 2D, pas de dispersion réelle).
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# GCT Industrial Complex
GCT_LAT = 33.88
GCT_LON = 10.09

# Gabès center (reference)
GABES_CENTER_LAT = 33.8869
GABES_CENTER_LON = 10.0982

GRID_SPACING = 0.1  # degrees (~11 km)
GRID_SIZE = 5  # 5x5

# Open-Meteo « forecast » accepte speed/direction/gusts ; les U/V bruts posent problème en combo → calcul local.
_HOURLY_WIND_VARS = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"


def wind_vector_uv_ms(speed_ms: float, direction_from_deg: float) -> tuple[float, float]:
    """
    u = est (+), v = nord (+). Direction météo = provenance du vent (deg depuis le nord).
    Vecteur déplacement de l'air : vers direction_from + 180°.
    """
    phi = math.radians((float(direction_from_deg) + 180.0) % 360.0)
    sp = float(speed_ms)
    u = sp * math.sin(phi)
    v = sp * math.cos(phi)
    return u, v


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def closest_hour_index(times: list[str]) -> int:
    """Index du créneau horaire le plus proche de maintenant (UTC)."""
    if not times:
        return 0
    now = datetime.now(timezone.utc)
    best_i = 0
    best_d: float | None = None
    for i, t in enumerate(times):
        try:
            ts = datetime.fromisoformat(t.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            d = abs((ts - now).total_seconds())
        except (ValueError, TypeError):
            continue
        if best_d is None or d < best_d:
            best_d = d
            best_i = i
    return best_i


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
    return dirs[round((float(deg) % 360) / 22.5) % 16]


def _speed_to_intensity(speed_ms: float) -> int:
    return min(10, int(float(speed_ms) * 0.8))


def _speed_to_color(speed_ms: float) -> str:
    s = float(speed_ms)
    if s < 3:
        return "green"
    if s < 8:
        return "yellow"
    if s < 15:
        return "orange"
    return "red"


def generate_grid_points() -> list[dict[str, Any]]:
    """
    Grille 5×5 centrée sur GCT, pas 0,1° (env. 55 km × 55 km).
    Row 0 = Nord, col 0 = Ouest (lon min).
    """
    points: list[dict[str, Any]] = []
    half = GRID_SIZE // 2
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            lat = GCT_LAT + (half - row) * GRID_SPACING
            lon = GCT_LON - ((GRID_SIZE - 1) - col) * GRID_SPACING
            points.append(
                {
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "row": row,
                    "col": col,
                    "grid_id": f"r{row}c{col}",
                }
            )
    return points


def _fetch_single_grid_point(point: dict[str, Any]) -> dict[str, Any]:
    params = {
        "latitude": point["lat"],
        "longitude": point["lon"],
        "hourly": "wind_speed_10m,wind_direction_10m",
        "forecast_days": 1,
        "wind_speed_unit": "ms",
    }
    try:
        resp = requests.get(OPEN_METEO_FORECAST, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        times: list[str] = hourly["time"]
        speed = hourly["wind_speed_10m"]
        direc = hourly["wind_direction_10m"]
        idx = closest_hour_index(times)
        current_speed = float(speed[idx] or 0.0)
        current_dir = float(direc[idx] or 0.0)
        current_u, current_v = wind_vector_uv_ms(current_speed, current_dir)
        return {
            "lat": point["lat"],
            "lon": point["lon"],
            "row": point["row"],
            "col": point["col"],
            "grid_id": point["grid_id"],
            "speed_ms": round(current_speed, 2),
            "speed_kmh": round(current_speed * 3.6, 1),
            "direction": round(current_dir, 1),
            "compass": _degrees_to_compass(current_dir),
            "u": round(current_u, 4),
            "v": round(current_v, 4),
            "u_v_source": "computed_from_speed_direction",
            "intensity": _speed_to_intensity(current_speed),
            "color": _speed_to_color(current_speed),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "lat": point["lat"],
            "lon": point["lon"],
            "row": point["row"],
            "col": point["col"],
            "grid_id": point["grid_id"],
            "speed_ms": 0.0,
            "speed_kmh": 0.0,
            "direction": 0.0,
            "compass": "N",
            "u": 0.0,
            "v": 0.0,
            "intensity": 0,
            "color": "gray",
            "error": str(e),
        }


def fetch_grid_parallel(grid_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Récupère les 25 points en parallèle (ThreadPoolExecutor)."""
    results: list[dict[str, Any]] = []
    max_workers = min(10, max(4, len(grid_points)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_single_grid_point, p): p for p in grid_points}
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda x: (x["row"], x["col"]))
    return results


def fetch_gct_center_wind() -> dict[str, Any]:
    """Vent détaillé au GCT + série horaire 48 h (indices u, v, rafales)."""
    params = {
        "latitude": GCT_LAT,
        "longitude": GCT_LON,
        "hourly": _HOURLY_WIND_VARS,
        "forecast_days": 2,
        "wind_speed_unit": "ms",
    }
    resp = requests.get(OPEN_METEO_FORECAST, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    hourly_d = data["hourly"]
    times = hourly_d["time"]
    speed = hourly_d["wind_speed_10m"]
    direc = hourly_d["wind_direction_10m"]
    gusts = hourly_d["wind_gusts_10m"]

    idx = closest_hour_index(times)
    current_speed = float(speed[idx] or 0.0)
    current_dir = float(direc[idx] or 0.0)
    current_u, current_v = wind_vector_uv_ms(current_speed, current_dir)
    current_gusts = float(gusts[idx] or 0.0)
    now_str = times[idx]

    hourly_list: list[dict[str, Any]] = []
    for i in range(idx, min(idx + 48, len(times))):
        sp = float(speed[i] or 0.0)
        di = float(direc[i] or 0.0)
        ui, vi = wind_vector_uv_ms(sp, di)
        hourly_list.append(
            {
                "time": times[i],
                "hour": i - idx,
                "speed_ms": round(sp, 2),
                "speed_kmh": round(sp * 3.6, 1),
                "direction": round(di, 1),
                "compass": _degrees_to_compass(di),
                "u": round(ui, 4),
                "v": round(vi, 4),
                "gusts_ms": round(float(gusts[i] or 0.0), 2),
            }
        )

    return {
        "location": "GCT Ghannouch",
        "latitude": GCT_LAT,
        "longitude": GCT_LON,
        "u_v_source": "computed_from_speed_direction",
        "current": {
            "speed_ms": round(current_speed, 2),
            "speed_kmh": round(current_speed * 3.6, 1),
            "direction": round(current_dir, 1),
            "compass": _degrees_to_compass(current_dir),
            "u": round(current_u, 4),
            "v": round(current_v, 4),
            "gusts_ms": round(current_gusts, 2),
            "gusts_kmh": round(current_gusts * 3.6, 1),
            "intensity": _speed_to_intensity(current_speed),
            "color": _speed_to_color(current_speed),
            "timestamp": now_str,
        },
        "hourly_48h": hourly_list,
    }


def calculate_pollution_plume(gct_wind: dict[str, Any]) -> dict[str, Any]:
    """
    Trajectoire indicative du panache depuis GCT (direction vent + 180°).
    """
    cur = gct_wind["current"]
    speed = float(cur["speed_ms"])
    direction = float(cur["direction"])
    u = float(cur["u"])
    v = float(cur["v"])

    plume_direction = (direction + 180.0) % 360.0
    plume_rad = math.radians(plume_direction)

    trajectory: list[dict[str, Any]] = []
    for minutes in range(0, 181, 15):
        hours = minutes / 60.0
        distance_km = (speed * 3.6) * hours

        delta_lat = (distance_km / 111.0) * math.cos(plume_rad)
        delta_lon = (distance_km / (111.0 * math.cos(math.radians(GCT_LAT)))) * math.sin(plume_rad)
        new_lat = GCT_LAT + delta_lat
        new_lon = GCT_LON + delta_lon

        concentration = max(0.0, 1.0 - (distance_km / 100.0))
        if concentration > 0.7:
            color = "red"
        elif concentration > 0.4:
            color = "orange"
        elif concentration > 0.1:
            color = "yellow"
        else:
            color = "transparent"

        zone = identify_zone(new_lat, new_lon)
        trajectory.append(
            {
                "minute": minutes,
                "latitude": round(new_lat, 6),
                "longitude": round(new_lon, 6),
                "distance_km": round(distance_km, 2),
                "concentration": round(concentration, 3),
                "color": color,
                "zone_affected": zone,
            }
        )

    cone_left = calculate_cone_side(plume_direction - 30.0, speed, 50)
    cone_right = calculate_cone_side(plume_direction + 30.0, speed, 50)

    affected = list(
        {p["zone_affected"] for p in trajectory if p["zone_affected"] != "Unknown"}
    )

    compass_plume = _degrees_to_compass(plume_direction)

    return {
        "source": {"latitude": GCT_LAT, "longitude": GCT_LON, "name": "GCT Ghannouch"},
        "pollutants_modeled": ["SO2", "NH3"],
        "wind_direction_from_deg": direction,
        "plume_direction_deg": round(plume_direction, 1),
        "wind_speed_ms": speed,
        "wind_speed_kmh": round(speed * 3.6, 1),
        "components_uv_fr": "u/v utiles pour intégration vectorielle (m/s).",
        "u_ms": round(u, 4),
        "v_ms": round(v, 4),
        "trajectory": trajectory,
        "cone_left": cone_left,
        "cone_right": cone_right,
        "affected_zones": affected,
        "max_reach_km": round((speed * 3.6) * 3.0, 1),
        "description_fr": (
            f"Panache indicatif depuis GCT vers {compass_plume} "
            f"à ~{round(speed * 3.6, 1)} km/h (modèle simplifié). "
            f"Zones citées : {', '.join(affected) if affected else 'hors zones démo'}."
        ),
        "description_ar": (
            f"انبعاثات نموذجية من GCT نحو {compass_plume} "
            f"بسرعة ~{round(speed * 3.6, 1)} كم/س"
        ),
    }


def calculate_cone_side(direction_deg: float, _speed_ms: float, max_km: int) -> list[dict[str, Any]]:
    rad = math.radians(direction_deg % 360.0)
    points: list[dict[str, Any]] = []
    step = max(5, min(15, max_km // 5))
    for dist_km in range(0, max_km + 1, step):
        delta_lat = (dist_km / 111.0) * math.cos(rad)
        delta_lon = (dist_km / (111.0 * math.cos(math.radians(GCT_LAT)))) * math.sin(rad)
        points.append(
            {
                "latitude": round(GCT_LAT + delta_lat, 6),
                "longitude": round(GCT_LON + delta_lon, 6),
                "distance_km": dist_km,
            }
        )
    return points


def build_animation_params(
    gct_wind: dict[str, Any],
    grid_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Paramètres pour particules / flèches (Flutter, Leaflet)."""
    _ = grid_data  # réservé — interpolation future sur grille
    cur = gct_wind["current"]
    speed = float(cur["speed_ms"])
    direction = float(cur["direction"])
    u = float(cur["u"])
    v = float(cur["v"])

    particle_speed = max(0.5, min(speed * 0.8, 5.0))
    particle_count = min(200, max(50, int(speed * 20)))
    particle_life = max(20, min(100, int(50 / max(speed, 0.1))))

    return {
        "particle_speed": round(particle_speed, 2),
        "particle_count": particle_count,
        "particle_life": particle_life,
        "wind_u": round(u, 4),
        "wind_v": round(v, 4),
        "wind_speed_ms": round(speed, 2),
        "wind_direction_deg": round(direction, 1),
        "frame_rate": 30,
        "color_scale": [
            {"speed_ms": 0, "color": "#00FF00"},
            {"speed_ms": 5, "color": "#FFFF00"},
            {"speed_ms": 10, "color": "#FFA500"},
            {"speed_ms": 15, "color": "#FF4500"},
            {"speed_ms": 20, "color": "#FF0000"},
            {"speed_ms": 25, "color": "#8B0000"},
        ],
        "arrow_scale": max(0.3, min(speed / 10.0, 1.5)),
        "opacity": 0.8,
        "line_width": 1.5,
        "grid_points_available": len(grid_data) if grid_data else 0,
        "note": (
            "U = composante est-ouest (m/s, + vers l’est), V = nord-sud (+ vers le nord). "
            "Utiliser U/V pour flèches et particules."
        ),
    }


def build_24h_forecast(gct_wind: dict[str, Any]) -> list[dict[str, Any]]:
    hourly = gct_wind["hourly_48h"][:24]
    forecast: list[dict[str, Any]] = []
    for h in hourly:
        sm = float(h["speed_ms"])
        forecast.append(
            {
                "time": h["time"],
                "hour": h["hour"],
                "speed_kmh": h["speed_kmh"],
                "direction": h["direction"],
                "compass": h["compass"],
                "u": h["u"],
                "v": h["v"],
                "intensity": _speed_to_intensity(sm),
                "color": _speed_to_color(sm),
                "risk_note": (
                    "Vent fort — dispersion rapide"
                    if sm > 10
                    else "Vent faible — accumulation locale"
                    if sm < 3
                    else "Vent modéré"
                ),
            }
        )
    return forecast


def identify_zone(lat: float, lon: float) -> str:
    zones = [
        {"name": "Chott Essalem", "center_lat": 33.87, "center_lon": 10.08, "radius_deg": 0.05},
        {"name": "Port de Gabès", "center_lat": 33.895, "center_lon": 10.11, "radius_deg": 0.05},
        {"name": "Médina de Gabès", "center_lat": GABES_CENTER_LAT, "center_lon": GABES_CENTER_LON, "radius_deg": 0.05},
        {"name": "Zone Agricole Nord", "center_lat": 33.95, "center_lon": 10.07, "radius_deg": 0.08},
        {"name": "Zone Agricole Sud", "center_lat": 33.82, "center_lon": 10.10, "radius_deg": 0.08},
        {"name": "Plage de Gabès", "center_lat": 33.90, "center_lon": 10.12, "radius_deg": 0.05},
        {"name": "Oasis de Gabès", "center_lat": 33.88, "center_lon": 10.06, "radius_deg": 0.06},
    ]
    for zone in zones:
        dist = math.sqrt((lat - zone["center_lat"]) ** 2 + (lon - zone["center_lon"]) ** 2)
        if dist <= zone["radius_deg"]:
            return zone["name"]
    return "Unknown"


def get_wind_flow_data() -> dict[str, Any]:
    """
    Payload complet : grille 5×5, vent GCT, panache, animation, prévision 24 h.
    """
    grid_points = generate_grid_points()
    grid_data = fetch_grid_parallel(grid_points)
    gct_wind = fetch_gct_center_wind()
    plume = calculate_pollution_plume(gct_wind)
    animation = build_animation_params(gct_wind, grid_data)
    forecast_24h = build_24h_forecast(gct_wind)

    extent_km = GRID_SPACING * 111.0 * (GRID_SIZE - 1)

    return {
        "wind_grid": grid_data,
        "gct_wind": gct_wind,
        "plume": plume,
        "animation": animation,
        "forecast_24h": forecast_24h,
        "metadata": {
            "center_gct_lat": GCT_LAT,
            "center_gct_lon": GCT_LON,
            "gabes_center_lat": GABES_CENTER_LAT,
            "gabes_center_lon": GABES_CENTER_LON,
            "grid_size": f"{GRID_SIZE}x{GRID_SIZE}",
            "grid_spacing_deg": GRID_SPACING,
            "coverage_extent_km_approx": round(extent_km, 1),
            "source": "Open-Meteo Forecast API (real-time)",
            "generated_at": _utc_now_iso(),
            "disclaimer_fr": "Panache et cônes : visualisation pédagogique, pas modèle réglementaire.",
            "u_v_note_fr": (
                "Composantes u/v dérivées de la vitesse et de la direction (API Open-Meteo ne combine pas "
                "toujours les champs bruts u/v avec les autres sur ce endpoint)."
            ),
        },
    }


def get_wind_grid_only() -> dict[str, Any]:
    pts = generate_grid_points()
    grid_data = fetch_grid_parallel(pts)
    return {
        "grid": grid_data,
        "grid_size": f"{GRID_SIZE}x{GRID_SIZE}",
        "total_points": len(grid_data),
        "generated_at": _utc_now_iso(),
    }


def get_wind_plume_only() -> dict[str, Any]:
    gct_wind = fetch_gct_center_wind()
    plume = calculate_pollution_plume(gct_wind)
    return {
        "plume": plume,
        "current_wind": gct_wind["current"],
        "generated_at": _utc_now_iso(),
    }


def get_wind_animation_only() -> dict[str, Any]:
    gct_wind = fetch_gct_center_wind()
    animation = build_animation_params(gct_wind, [])
    return {
        "animation": animation,
        "current_wind": gct_wind["current"],
        "generated_at": _utc_now_iso(),
    }


if __name__ == "__main__":
    import json

    print("Wind Flow Service — test\n")
    result = get_wind_flow_data()
    print(json.dumps({k: result[k] for k in ("metadata",) if k in result}, indent=2))
    print(f"Grid points: {len(result['wind_grid'])}")
    c = result["gct_wind"]["current"]
    print(f"GCT now: {c['speed_kmh']} km/h, {c['direction']}° ({c['compass']}), u={c['u']}, v={c['v']}")
    print(f"Plume max reach: {result['plume']['max_reach_km']} km")
    print("OK")
