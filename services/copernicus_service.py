"""
Copernicus Marine Service integration.

Public Copernicus datasets typically require credentials; this module exposes
a stub `fetch_copernicus_marine` that returns None so callers can fall back
to Open-Meteo marine or research-based simulation.
"""

from __future__ import annotations

from typing import Any

import requests

REQUEST_TIMEOUT_S = 10


def fetch_copernicus_marine(
    latitude: float,
    longitude: float,
    motu_url: str | None = None,
) -> dict[str, Any] | None:
    """
    Placeholder for CMEMS/Motu or STAC-backed fetches.

    Without user credentials and product selection, live Copernicus calls are
    not enabled. Extend this function when `COPERNICUS_*` env vars are provided.

    Args:
        latitude: Sample latitude (WGS84).
        longitude: Sample longitude (WGS84).
        motu_url: Optional preconfigured MOTU subset URL.

    Returns:
        Parsed JSON-like dict with turbidity/chlorophyll if successful, else None.
    """
    if motu_url:
        try:
            r = requests.get(motu_url, timeout=REQUEST_TIMEOUT_S)
            if r.ok:
                return {"note": "motu_custom_response", "status": r.status_code}
        except requests.RequestException:
            pass
    return None
