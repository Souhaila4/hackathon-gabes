"""Rôles applicatifs PhosAlert (profil utilisateur)."""

from __future__ import annotations

from typing import Literal

UserRole = Literal["citoyen", "agriculteur", "chercheur_scientifique"]

DEFAULT_USER_ROLE: UserRole = "citoyen"

VALID_USER_ROLES: frozenset[str] = frozenset({"citoyen", "agriculteur", "chercheur_scientifique"})

# Libellés pour UI / docs
ROLE_LABELS_FR: dict[str, str] = {
    "citoyen": "Citoyen",
    "agriculteur": "Agriculteur",
    "chercheur_scientifique": "Chercheur scientifique",
}

# Alias acceptés à l'inscription / mise à jour
_ROLE_ALIASES: dict[str, UserRole] = {
    "citizen": "citoyen",
    "farmer": "agriculteur",
    "scientist": "chercheur_scientifique",
    "researcher": "chercheur_scientifique",
    "chercheur": "chercheur_scientifique",
}


def parse_role(raw: str | None) -> UserRole | None:
    """
    Retourne un rôle canonique ou ``None`` si la valeur est invalide.
    Chaîne vide → ``None`` (appelant peut appliquer la valeur par défaut).
    """
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v:
        return None
    if v in _ROLE_ALIASES:
        return _ROLE_ALIASES[v]
    if v in VALID_USER_ROLES:
        return v  # type: ignore[return-value]
    return None


def role_or_default(doc: dict) -> UserRole:
    """Rôle stocké en base, ou citoyen pour les comptes créés avant cette fonctionnalité."""
    r = doc.get("role")
    if isinstance(r, str) and r in VALID_USER_ROLES:
        return r  # type: ignore[return-value]
    return DEFAULT_USER_ROLE
