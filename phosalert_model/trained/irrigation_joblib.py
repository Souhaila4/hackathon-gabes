"""
Inférence irrigation depuis un pipeline **scikit-learn** sérialisé en joblib.

Aucune dépendance au serveur Flask. Config via ``PHOSALERT_TRAINED_IRRIGATION_MODEL_PATH``.

**Ordre des features pour ``predict``** :

1. distance_km, 2. so2, 3. downwind (0/1), 4. turbidity, 5. crop_high (0/1)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from phosalert_model.heuristics import IrrigationFeatures

_log = logging.getLogger(__name__)
_pipeline: Any | None = None
_warned_missing_file = False


def try_irrigation_trained(f: IrrigationFeatures) -> int | None:
    """Score 0–100 si un modèle est chargé, sinon ``None`` (l’appelant utilisera l’heuristique)."""
    global _pipeline, _warned_missing_file

    path = os.environ.get("PHOSALERT_TRAINED_IRRIGATION_MODEL_PATH", "").strip()
    if not path:
        return None

    p = Path(path)
    if not p.is_file():
        if not _warned_missing_file:
            _log.warning("PHOSALERT_TRAINED_IRRIGATION_MODEL_PATH fichier introuvable: %s", path)
            _warned_missing_file = True
        return None

    if _pipeline is None:
        import joblib

        _pipeline = joblib.load(p)
        _log.info("Modèle irrigation chargé: %s", path)

    x = [
        [
            float(f.distance_km),
            float(f.so2),
            1.0 if f.downwind else 0.0,
            float(f.turbidity),
            1.0 if f.crop_sensitivity == "high" else 0.0,
        ]
    ]
    y = _pipeline.predict(x)[0]
    return int(round(float(y)))
