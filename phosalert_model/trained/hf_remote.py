"""
Inférence irrigation via **API distante** (ex. Hugging Face Inference / Space).

Variables d'environnement (côté *consommateur*, ex. backend déployé) :
- ``PHOSALERT_HF_INFERENCE_URL`` : URL POST (endpoint de votre Space ou Inference API)
- ``PHOSALERT_HF_TOKEN`` ou ``HF_TOKEN`` : jeton lecture (optionnel selon le repo)

Corps JSON envoyé (contrat stable) ::
    {"features": {"distance_km", "so2", "downwind", "turbidity", "crop_sensitivity"}}

Réponse attendue : ``{"score": <int 0-100>}`` ou liste ``[<score>]``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from phosalert_model.heuristics import IrrigationFeatures

_log = logging.getLogger(__name__)
_warned_once = False


def try_irrigation_hf_remote(f: IrrigationFeatures) -> int | None:
    """Score depuis Hugging Face si URL configurée ; sinon ``None``."""
    global _warned_once

    url = os.environ.get("PHOSALERT_HF_INFERENCE_URL", "").strip()
    if not url:
        return None

    token = (os.environ.get("PHOSALERT_HF_TOKEN") or os.environ.get("HF_TOKEN") or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body: dict[str, Any] = {
        "features": {
            "distance_km": float(f.distance_km),
            "so2": float(f.so2),
            "downwind": bool(f.downwind),
            "turbidity": float(f.turbidity),
            "crop_sensitivity": f.crop_sensitivity,
        }
    }

    try:
        r = requests.post(url, json=body, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        if not _warned_once:
            _log.warning("Appel HF irrigation échoué (%s) — repli heuristique/joblib.", exc)
            _warned_once = True
        return None

    score: float | None = None
    if isinstance(data, dict):
        if "score" in data:
            score = float(data["score"])
        elif "predictions" in data and data["predictions"]:
            score = float(data["predictions"][0])
    elif isinstance(data, list) and len(data) > 0:
        score = float(data[0])

    if score is None:
        return None
    return int(round(max(0.0, min(100.0, score))))
