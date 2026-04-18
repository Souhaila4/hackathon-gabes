"""
Serveur HTTP minimal (FastAPI) pour un **Space Hugging Face** ou conteneur Docker.

Usage (après ``pip install ".[serve]"``) ::
    uvicorn phosalert_model.serve:app --host 0.0.0.0 --port 7860

Ne pas définir ``PHOSALERT_HF_INFERENCE_URL`` sur la machine qui héberge le modèle
(évite une boucle). Le score utilise joblib + repli heuristique via ``irrigation_risk_score``
sans appel HTTP sortant si l’URL HF n’est pas set.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from phosalert_model.heuristics import IrrigationFeatures, irrigation_risk_heuristic
from phosalert_model.trained.irrigation_joblib import try_irrigation_trained

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError("Installez les extras : pip install 'phosalert-model[serve]'") from exc


class FeaturesIn(BaseModel):
    distance_km: float = Field(..., ge=0)
    so2: float = Field(..., ge=0)
    downwind: bool = False
    turbidity: float = Field(..., ge=0)
    crop_sensitivity: Literal["high", "low"] = "low"


class PredictBody(BaseModel):
    features: FeaturesIn


app = FastAPI(title="PhosAlert irrigation", version="0.1.0")


def _score_local(f: IrrigationFeatures) -> int:
    t = try_irrigation_trained(f)
    if t is not None:
        return t
    return irrigation_risk_heuristic(f)


@app.post("/predict")
def predict(body: PredictBody) -> dict[str, Any]:
    """Contrat compatible avec ``trained/hf_remote.py`` (backend)."""
    fi = body.features
    f = IrrigationFeatures(
        distance_km=fi.distance_km,
        so2=fi.so2,
        downwind=fi.downwind,
        turbidity=fi.turbidity,
        crop_sensitivity=fi.crop_sensitivity,
    )
    return {"score": _score_local(f)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "phosalert-model"}

