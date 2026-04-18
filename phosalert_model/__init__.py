"""
Package **phosalert_model** — scoring, simulations et inférence (modèles entraînés).

Structure :
- ``api`` : façade unique pour le **backend** (import recommandé).
- ``heuristics`` : règles & simulations (baseline, sans fichier .pkl).
- ``trained`` : pipelines joblib / sklearn optionnels.
- ``constants`` : coordonnées Gabès / GCT.

Le serveur Flask ne doit pas dépendre de ``heuristics`` ou ``trained`` directement :
utiliser ``import phosalert_model`` (alias de ``api``).
"""

from __future__ import annotations

from phosalert_model.api import *  # noqa: F403
from phosalert_model.api import __all__ as __all__
