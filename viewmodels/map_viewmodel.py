"""ViewModel carte : agrégation air/vent et marqueurs zones Gabès."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models.gabes_zones import GABES_ZONES_SPEC
import phosalert_model
from services import openmeteo_service as owm


def fetch_air_wind_bundle() -> tuple[dict[str, Any], dict[str, Any], str]:
    """Open-Meteo + repli simulé (même logique qu’historiquement dans ``app``)."""
    aq, aq_ok = owm.fetch_air_quality_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
    wind, wind_ok = owm.fetch_wind_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
    data_source = "live"
    if not aq_ok or aq.get("so2") is None:
        data_source = "simulated"
        sim = phosalert_model.simulate_air_gabes(near_gct=True)
        aq = {**aq, **sim}
    if not wind_ok or wind.get("wind_direction") is None:
        data_source = "simulated"
        sw = phosalert_model.simulate_wind()
        wind = {"wind_direction": sw["wind_direction_10m"], "wind_speed": sw["wind_speed_10m"]}
    return aq, wind, data_source


def build_zone_markers(so2: float, wind_from_deg: float) -> list[dict[str, Any]]:
    zones_out: list[dict[str, Any]] = []
    for z in GABES_ZONES_SPEC:
        dist = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, float(z["latitude"]), float(z["longitude"]))
        score = phosalert_model.zone_risk_score(
            zone_lat=float(z["latitude"]),
            zone_lon=float(z["longitude"]),
            so2=so2,
            wind_from_deg=wind_from_deg,
        )
        if score >= 70:
            rlevel, color = "DANGEROUS", "red"
        elif score >= 40:
            rlevel, color = "MODERATE", "orange"
        else:
            rlevel, color = "SAFE", "green"

        zones_out.append(
            {
                "id": z["id"],
                "name": z["name"],
                "latitude": z["latitude"],
                "longitude": z["longitude"],
                "risk_level": rlevel,
                "risk_score": score,
                "color": color,
                "pollution_type": z["pollution_type"],
                "distance_from_gct_km": round(dist, 3),
            }
        )
    return zones_out


class MapZonesViewModel:
    """Payload JSON pour ``GET /api/map/zones``."""

    def build_payload(self) -> tuple[dict[str, Any], int]:
        try:
            aq, wind, data_source = fetch_air_wind_bundle()
            so2 = float(aq.get("so2") or 0.0)
            wd = float(wind.get("wind_direction") or 0.0)
            ws = float(wind.get("wind_speed") or 0.0)
            zones_out = build_zone_markers(so2, wd)
            payload = {
                "zones": zones_out,
                "gct_location": {"latitude": 33.88, "longitude": 10.09},
                "wind_direction": round(wd, 2),
                "wind_speed": round(ws, 2),
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data_source": data_source,
            }
            return payload, 200
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "ok": False}, 500
