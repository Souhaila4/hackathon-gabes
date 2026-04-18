"""ViewModel tableau de bord — délégation vers ``services.dashboard_service``."""

from __future__ import annotations

from typing import Any

from models.user_roles import VALID_USER_ROLES
from services.dashboard_service import (
    build_agriculteur_dashboard,
    build_chercheur_dashboard,
    build_citoyen_dashboard,
)


def normalize_dashboard_role(raw: str | None) -> str:
    r = (raw or "citoyen").strip()
    return r if r in VALID_USER_ROLES else "citoyen"


def build_dashboard_payload(
    role: str,
    *,
    crop: str = "olive",
    lat: float | None = None,
    lon: float | None = None,
) -> tuple[dict[str, Any], int]:
    """Construit le JSON dashboard pour un rôle canonique."""
    key = normalize_dashboard_role(role)
    if key == "agriculteur":
        return build_agriculteur_dashboard(crop=crop, lat=lat, lon=lon), 200
    if key == "chercheur_scientifique":
        return build_chercheur_dashboard(), 200
    return build_citoyen_dashboard(), 200


class DashboardViewModel:
    """Rétrocompatibilité tests / appels internes : vue citoyen par défaut."""

    def build_payload(self) -> tuple[dict[str, Any], int]:
        return build_citoyen_dashboard(), 200
