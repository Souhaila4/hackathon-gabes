"""
Serveur HTTP minimal (FastAPI) pour un **Space Hugging Face** ou conteneur Docker.

Usage (après ``pip install ".[serve]"``) ::
    uvicorn phosalert_model.serve:app --host 0.0.0.0 --port 7860

Ne pas définir ``PHOSALERT_HF_INFERENCE_URL`` sur la machine qui héberge le modèle
(évite une boucle). Le score utilise joblib + repli heuristique via ``irrigation_risk_score``
sans appel HTTP sortant si l’URL HF n’est pas set.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from phosalert_model.heuristics import (
    IrrigationFeatures,
    irrigation_risk_heuristic,
    is_downwind_of_gct,
    risk_level_label_from_score,
)
from phosalert_model.trained.irrigation_joblib import try_irrigation_trained

try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise ImportError("Installez les extras : pip install 'phosalert-model[serve]'") from exc


class FeaturesIn(BaseModel):
    distance_km: float = Field(..., ge=0)
    so2: float = Field(..., ge=0)
    downwind: bool = False
    turbidity: float = Field(..., ge=0)
    crop_sensitivity: Literal["high", "low"] = "low"


class MeteoIn(BaseModel):
    """Facteurs météo optionnels (information / calcul du vent par rapport au GCT)."""

    wind_speed_kmh: float | None = Field(None, ge=0, description="Vent : vitesse (km/h).")
    wind_direction_deg: float | None = Field(
        None,
        ge=0,
        le=360,
        description="Vent météo : direction **d'où il souffle** (degrés, 0–360).",
    )
    temperature_c: float | None = Field(None, description="Température (°C).")
    relative_humidity_pct: float | None = Field(None, ge=0, le=100, description="Humidité relative (%).")


class PredictBody(BaseModel):
    features: FeaturesIn
    meteo: MeteoIn | None = None
    farm_latitude: float | None = Field(None, ge=-90, le=90, description="Parcelle : latitude (pour calcul vent ↓ GCT).")
    farm_longitude: float | None = Field(
        None, ge=-180, le=180, description="Parcelle : longitude (pour calcul vent ↓ GCT)."
    )


app = FastAPI(title="PhosAlert irrigation", version="0.1.0")


def _resolve_downwind(fi: FeaturesIn, body: PredictBody) -> tuple[bool, str]:
    """Si parcelle + direction du vent sont fournis, calcule ``downwind`` géographiquement."""
    m = body.meteo
    if (
        body.farm_latitude is not None
        and body.farm_longitude is not None
        and m is not None
        and m.wind_direction_deg is not None
    ):
        d = is_downwind_of_gct(
            body.farm_latitude,
            body.farm_longitude,
            float(m.wind_direction_deg),
        )
        return d, "computed_from_wind"
    return fi.downwind, "features"


@app.get("/")
def root() -> dict[str, Any]:
    """Point d’entrée Space Hugging Face — liens utiles."""
    return {
        "service": "phosalert-model",
        "docs": "/docs",
        "health": "/health",
        "predict": "POST /predict",
        "body_example": {
            "features": {
                "distance_km": 12.0,
                "so2": 45.0,
                "downwind": True,
                "turbidity": 8.0,
                "crop_sensitivity": "high",
            },
            "meteo": {
                "wind_speed_kmh": 18.5,
                "wind_direction_deg": 225.0,
                "temperature_c": 26.0,
                "relative_humidity_pct": 62.0,
            },
            "farm_latitude": 33.89,
            "farm_longitude": 10.1,
        },
        "notes": {
            "predicted_at": "horodatage ISO UTC dans la réponse POST /predict",
            "meteo": "optionnel ; renvoyé tel quel + sert au calcul downwind si lat/lon + wind_direction_deg",
        },
    }


def _score_local(f: IrrigationFeatures) -> int:
    t = try_irrigation_trained(f)
    if t is not None:
        return t
    return irrigation_risk_heuristic(f)


@app.post("/predict")
def predict(body: PredictBody) -> dict[str, Any]:
    """Contrat compatible avec ``trained/hf_remote.py`` (backend) — champs extra ignorés côté client legacy."""
    fi = body.features
    down_eff, down_src = _resolve_downwind(fi, body)
    f = IrrigationFeatures(
        distance_km=fi.distance_km,
        so2=fi.so2,
        downwind=down_eff,
        turbidity=fi.turbidity,
        crop_sensitivity=fi.crop_sensitivity,
    )
    score = _score_local(f)
    out: dict[str, Any] = {
        "score": score,
        "risk_level": risk_level_label_from_score(score),
        "predicted_at": datetime.now(timezone.utc).isoformat(),
        "downwind_effective": down_eff,
        "downwind_source": down_src,
    }
    if body.meteo is not None:
        meta = body.meteo.model_dump(exclude_none=True)
        if meta:
            out["meteo"] = meta
    if body.farm_latitude is not None and body.farm_longitude is not None:
        out["farm"] = {"latitude": body.farm_latitude, "longitude": body.farm_longitude}
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "phosalert-model"}

