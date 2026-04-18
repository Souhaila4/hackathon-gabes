"""
Modèles **entraînés** (HF, joblib, etc.) — séparés des heuristiques.

- ``hf_remote`` : inférence via URL (Hugging Face).
- ``irrigation_joblib`` : pipeline scikit-learn local optionnel.
"""

from phosalert_model.trained.hf_remote import try_irrigation_hf_remote
from phosalert_model.trained.irrigation_joblib import try_irrigation_trained

__all__ = ["try_irrigation_hf_remote", "try_irrigation_trained"]
