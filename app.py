"""
PhosAlert API — Flask gateway for Gabès air & water intelligence.

Architecture MVVM (adaptée REST) :
- **View** : ce fichier (handlers ``/health``, ``/api/map/zones``) + ``routes/`` (dont ``/api/dashboard``)
- **ViewModel** : ``viewmodels/``
- **Model** : ``models/`` (constantes métier)
- **Repository** : ``repositories/`` (MongoDB)
- **Services** : ``services/`` (Open-Meteo, etc.)
- **Modèle ML** : package installé depuis le dossier voisin ``../phosalert-model`` (déployable sur Hugging Face) ; **aucun** code modèle dans ce dépôt
- **Swagger** : UI ``/apidocs/`` — spec JSON ``/apispec_1.json`` (voir ``presentation/swagger.py``)
- **Infrastructure** : ``core/extensions.py`` (MongoDB, JWT)
"""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import verify_jwt_in_request

from core.extensions import init_mongo, jwt
from presentation.swagger import init_swagger, is_swagger_path
from routes import register_routes
from viewmodels import MapZonesViewModel

load_dotenv()


def _env_truthy(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _register_jwt_error_handlers(jwt_manager) -> None:
    """Return JSON errors consistent with the rest of the API."""

    @jwt_manager.expired_token_loader
    def _expired(_jwt_header, _jwt_payload):  # noqa: ANN001
        return jsonify({"ok": False, "error": "Token expiré."}), 401

    @jwt_manager.invalid_token_loader
    def _invalid(reason: str):
        return jsonify({"ok": False, "error": reason or "Token invalide."}), 422

    @jwt_manager.unauthorized_loader
    def _missing(reason: str):
        return jsonify({"ok": False, "error": reason or "Authentification requise."}), 401


def create_app() -> Flask:
    """Application factory configuring CORS and route blueprints."""
    app = Flask(__name__)

    secret = os.environ.get("SECRET_KEY") or "dev-insecure-change-me"
    jwt_secret = os.environ.get("JWT_SECRET_KEY") or secret
    app.config["SECRET_KEY"] = secret
    app.config["JWT_SECRET_KEY"] = jwt_secret
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_EXPIRES_MINUTES", "15"))
    )
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(
        days=int(os.environ.get("JWT_REFRESH_EXPIRES_DAYS", "30"))
    )

    app.config["MONGODB_URI"] = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
    app.config["MONGODB_DB_NAME"] = os.environ.get("MONGODB_DB_NAME", "phosalert")

    init_mongo(app)
    jwt.init_app(app)
    _register_jwt_error_handlers(jwt)

    CORS(app, resources={r"/*": {"origins": "*"}})
    register_routes(app)

    from routes.alerts import alerts_bp

    app.register_blueprint(alerts_bp, url_prefix="/api")

    @app.before_request
    def _optional_jwt_gate() -> None:
        """Si REQUIRE_JWT est activé, exige un JWT valide sur les routes API hors auth et health."""
        if request.method == "OPTIONS":
            return None
        if not _env_truthy("REQUIRE_JWT", default=False):
            return None
        path = request.path or ""
        if is_swagger_path(path):
            return None
        if path == "/health" or path.rstrip("/") == "/health":
            return None
        if path.startswith("/api/auth"):
            return None
        # Dashboard : JWT optionnel (rôle citoyen par défaut sans token)
        if path.rstrip("/") == "/api/dashboard":
            return None
        if path.startswith("/api"):
            verify_jwt_in_request()
        return None

    @app.get("/health")
    def health():
        """
        Santé du service.
        ---
        tags:
          - Health
        summary: Liveness
        description: Sonde sans auth ; métadonnées environnement.
        responses:
          200:
            description: Service OK
            schema:
              type: object
              properties:
                status:
                  type: string
                  example: ok
                service:
                  type: string
                environment:
                  type: string
          500:
            description: Erreur interne
        """
        try:
            return jsonify(
                {
                    "status": "ok",
                    "service": "phosalert-backend",
                    "environment": os.environ.get("FLASK_ENV", "development"),
                }
            ), 200
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "detail": str(exc)}), 500

    @app.get("/api/map/zones")
    def map_zones():
        """
        Carte des zones autour du GCT avec score de risque dynamique.
        ---
        tags:
          - Carte
        summary: Marqueurs carte pollution
        security:
          - Bearer: []
        responses:
          200:
            description: Zones, vent, source données
          500:
            description: Erreur serveur
        """
        payload, code = MapZonesViewModel().build_payload()
        return jsonify(payload), code

    init_swagger(app)

    return app


def _print_registered_routes(app: Flask) -> None:
    """Pretty-print HTTP paths for operators on startup (une ligne par chemin, méthodes fusionnées)."""
    from collections import defaultdict

    merged: dict[str, set[str]] = defaultdict(set)
    for rule in app.url_map.iter_rules():
        merged[rule.rule] |= {m for m in rule.methods if m not in ("HEAD", "OPTIONS")}
    rows = [(path, ",".join(sorted(methods))) for path, methods in merged.items()]
    rows.sort(key=lambda x: x[0])
    print("PhosAlert API — routes disponibles :")
    for path, methods in rows:
        print(f"  • [{methods}] {path}")


app = create_app()


if __name__ == "__main__":
    import socket

    def find_free_port(preferred: int = 8080) -> int:
        """Premier port libre à partir de ``preferred`` (jusqu'à +19)."""
        for port in range(preferred, preferred + 20):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("", port))
                    return port
            except OSError:
                continue
        return preferred + 20

    _print_registered_routes(app)

    if os.environ.get("PORT"):
        port = int(os.environ["PORT"])
    else:
        port = find_free_port(8080)

    print(f"\nStarting PhosAlert on port {port}")
    print(f"   Local  : http://127.0.0.1:{port}")
    print(f"   Network: http://0.0.0.0:{port}")
    print(f"   Swagger: http://127.0.0.1:{port}/apidocs/\n")

    app.run(
        debug=True,
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )
