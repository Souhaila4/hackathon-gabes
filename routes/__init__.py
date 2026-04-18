"""
Couche **View** (HTTP) : blueprints Flask ; la logique métier est dans ``viewmodels/``.
"""

from routes.air_quality import bp as air_bp
from routes.auth import bp as auth_bp
from routes.chatbot import bp as chat_bp
from routes.prediction import bp as predict_bp
from routes.water_quality import bp as water_bp


def register_routes(app) -> None:
    """Attach all API blueprints to the Flask application."""
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(air_bp, url_prefix="/api")
    app.register_blueprint(water_bp, url_prefix="/api")
    app.register_blueprint(predict_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")


__all__ = ["register_routes", "air_bp", "auth_bp", "water_bp", "predict_bp", "chat_bp"]
