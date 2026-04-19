"""ViewModel carte : mêmes zones / scores que le dashboard, mêmes SO2/vent quand Open-Meteo répond."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import phosalert_model
from services import openmeteo_service as owm
from services.gabes_zone_scores import markers_for_map_payload
from services.dashboard_service import _fetch_current_air, _fetch_wind


def fetch_air_wind_bundle() -> tuple[dict[str, Any], dict[str, Any], str]:
    """Repli (snapshots + simulation) si les mêmes appels que le dashboard échouent."""
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


def _so2_wind_for_map() -> tuple[float, float, float, str]:
    """
    Préfère les mêmes lectures air/vent que le dashboard (``_fetch_current_air`` + ``_fetch_wind``)
    pour que les scores de la carte coïncident avec le tableau de bord.
    """
    try:
        air = _fetch_current_air()
        wind = _fetch_wind()
        return (
            float(air["so2_ugm3"]),
            float(wind["direction_deg"]),
            float(wind["speed_kmh"]),
            "live",
        )
    except Exception:  # noqa: BLE001
        aq, wind, data_source = fetch_air_wind_bundle()
        return (
            float(aq.get("so2") or 0.0),
            float(wind.get("wind_direction") or 0.0),
            float(wind.get("wind_speed") or 0.0),
            data_source,
        )


class MapZonesViewModel:
    """Payload JSON pour ``GET /api/map/zones``."""

    def build_payload(self) -> tuple[dict[str, Any], int]:
        try:
            so2, wd, ws, data_source = _so2_wind_for_map()
            zones_out = markers_for_map_payload(so2, wd, ws)
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
