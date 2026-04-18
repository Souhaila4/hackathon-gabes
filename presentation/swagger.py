"""Configuration Swagger / OpenAPI (Flasgger) pour PhosAlert."""

from __future__ import annotations

import os

from flasgger import Swagger


def _env_swagger_enabled() -> bool:
    v = os.environ.get("SWAGGER_ENABLED", "true")
    return v.strip().lower() in ("1", "true", "yes", "on")


SWAGGER_CONFIG: dict = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

SWAGGER_TEMPLATE: dict = {
    "swagger": "2.0",
    "info": {
        "title": "PhosAlert API",
        "description": (
            "Gateway REST pour l’intelligence air & eau (Gabès). "
            "Authentification JWT (`/api/auth/*`). "
            "Certaines routes exigent un en-tête `Authorization: Bearer <token>` si `REQUIRE_JWT=true`."
        ),
        "version": "1.0.0",
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT : préfixe `Bearer ` suivi du access_token ou refresh_token selon l’endpoint.",
        }
    },
    "tags": [
        {"name": "Health", "description": "Sonde liveness"},
        {"name": "Auth", "description": "Inscription, login, refresh, profil"},
        {"name": "Carte", "description": "Carte des zones et risques"},
        {"name": "Dashboard", "description": "Agrégat écran d’accueil"},
        {"name": "Air", "description": "Qualité de l’air et vent (Open-Meteo)"},
        {"name": "Eau", "description": "Qualité de l’eau"},
        {"name": "Prédiction", "description": "Risque irrigation"},
        {"name": "Chat", "description": "Assistant conversationnel"},
    ],
}


def init_swagger(app) -> Swagger | None:
    """Enregistre Swagger UI (``/apidocs/``) et le JSON ``/apispec_1.json``."""
    if not _env_swagger_enabled():
        return None
    return Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)


def is_swagger_path(path: str) -> bool:
    """Routes à exclure de ``REQUIRE_JWT`` (UI et spec Swagger)."""
    if not path:
        return False
    p = path.rstrip("/") or "/"
    if p.startswith("/apidocs"):
        return True
    if p.startswith("/flasgger_static"):
        return True
    if "apispec" in p and p.endswith(".json"):
        return True
    return False
