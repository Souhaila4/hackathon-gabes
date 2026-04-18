"""
Client HTTP vers le Space Hugging Face **kaaboura/gabes-nappe-eau** (classification /
segmentation d’images — tuiles type Sentinel-2).

Ce Space n’expose pas une API « lat/lon → JSON » : il attend un fichier image en
``POST /classify`` ou ``POST /segment``. Voir ``main.py`` du Space.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

_log = logging.getLogger(__name__)


def get_base_url() -> str:
    return os.environ.get("GABES_GEOML_SPACE_URL", "https://kaaboura-gabes-nappe-eau.hf.space").rstrip(
        "/"
    )


def geoml_health() -> dict[str, Any] | None:
    """Sonde ``GET /health`` du Space GeoML (optionnel, pour diagnostics)."""
    try:
        r = requests.get(f"{get_base_url()}/health", timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        _log.warning("GeoML health indisponible: %s", exc)
        return None


def geoml_classify_image(image_bytes: bytes, filename: str = "tile.png") -> tuple[dict[str, Any] | None, str | None]:
    """
    POST ``/classify`` (multipart). Retourne ``(json, None)`` ou ``(None, message_erreur)``.
    """
    url = f"{get_base_url()}/classify"
    lower = filename.lower()
    if lower.endswith((".jpg", ".jpeg")):
        mime = "image/jpeg"
    elif lower.endswith(".tif") or lower.endswith(".tiff"):
        mime = "image/tiff"
    else:
        mime = "image/png"
    files = {"file": (filename, image_bytes, mime)}
    try:
        r = requests.post(url, files=files, timeout=120)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data, None
        return {"raw": data}, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
