"""
Couche **ViewModel** : logique applicative et structure des réponses JSON.

Les routes (View) appellent ces classes/fonctions et renvoient ``jsonify(...)``.
"""

from viewmodels.auth_viewmodel import AuthViewModel
from viewmodels.dashboard_viewmodel import DashboardViewModel
from viewmodels.map_viewmodel import MapZonesViewModel

__all__ = ["AuthViewModel", "DashboardViewModel", "MapZonesViewModel"]
