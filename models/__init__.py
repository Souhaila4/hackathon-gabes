"""
Couche **Model** : constantes métier et formes de données (sans dépendance Flask).

MVVM (adapté API REST) :
- **Model** : `models/`
- **ViewModel** : `viewmodels/` (logique, agrégation, format des réponses JSON)
- **View** : `routes/` + handlers dans `app.py` (HTTP uniquement)
- **Repository** : `repositories/` (persistance MongoDB)
"""

from models.gabes_zones import GABES_ZONES_SPEC
from models.user_roles import (
    DEFAULT_USER_ROLE,
    ROLE_LABELS_FR,
    VALID_USER_ROLES,
    UserRole,
    parse_role,
    role_or_default,
)

__all__ = [
    "GABES_ZONES_SPEC",
    "DEFAULT_USER_ROLE",
    "ROLE_LABELS_FR",
    "VALID_USER_ROLES",
    "UserRole",
    "parse_role",
    "role_or_default",
]
