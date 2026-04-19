"""Scores et listes de zones Gabès — **unique source** pour dashboard et carte."""

from __future__ import annotations

from typing import Any

import phosalert_model as pm

from models.gabes_zones import GABES_ZONES_SPEC


def build_unified_zone_rows(
    so2_ugm3: float,
    wind_direction_from_deg: float,
    wind_speed_kmh: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Liste des zones avec scores — même jeu que `/api/map/zones` :
    ``GABES_ZONES_SPEC`` + ``phosalert_model.zone_risk_score`` + seuils 70 / 40.

    ``wind_speed_kmh`` est réservé pour une évolution future du modèle (non utilisé aujourd’hui).
    """
    _ = wind_speed_kmh  # API stable pour alignement carte / dashboard
    zones_out: list[dict[str, Any]] = []
    so2_f = float(so2_ugm3 or 0.0)
    wd_f = float(wind_direction_from_deg or 0.0)

    for z in GABES_ZONES_SPEC:
        lat_f = float(z["latitude"])
        lon_f = float(z["longitude"])
        score = pm.zone_risk_score(
            zone_lat=lat_f,
            zone_lon=lon_f,
            so2=so2_f,
            wind_from_deg=wd_f,
        )
        if score >= 70:
            level, color = "DANGEROUS", "red"
        elif score >= 40:
            level, color = "MODERATE", "orange"
        else:
            level, color = "SAFE", "green"

        dist = pm.haversine_km(pm.GCT_LAT, pm.GCT_LON, lat_f, lon_f)
        dist_r = round(dist, 3)
        downwind = pm.is_downwind_of_gct(lat_f, lon_f, wd_f)
        safe = level == "SAFE"
        name_ar = (z.get("name_ar") or "").strip()

        zones_out.append(
            {
                "id": z["id"],
                "name": z["name"],
                "name_ar": name_ar,
                "latitude": lat_f,
                "longitude": lon_f,
                "risk_score": score,
                "risk_level": level,
                "color": color,
                "pollution_type": z["pollution_type"],
                "is_safe": safe,
                "is_downwind": downwind,
                "distance_gct_km": dist_r,
                "distance_from_gct_km": dist_r,
            }
        )
    return zones_out


def markers_for_map_payload(
    so2_ugm3: float,
    wind_direction_from_deg: float,
    wind_speed_kmh: float = 0.0,
) -> list[dict[str, Any]]:
    """Sous-ensemble JSON attendu par l’app mobile pour la carte."""
    rows = build_unified_zone_rows(so2_ugm3, wind_direction_from_deg, wind_speed_kmh)
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "name": r["name"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "risk_level": r["risk_level"],
                "risk_score": r["risk_score"],
                "color": r["color"],
                "pollution_type": r["pollution_type"],
                "distance_from_gct_km": r["distance_from_gct_km"],
                "is_safe": r["is_safe"],
                "is_downwind": r["is_downwind"],
            }
        )
    return out
