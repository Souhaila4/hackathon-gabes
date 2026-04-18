"""
Couche **View** (HTTP) : auth — délègue au ViewModel (``AuthViewModel``).
"""

from __future__ import annotations

import core.extensions as extensions
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from repositories.user_repository import UserRepository
from viewmodels.auth_viewmodel import AuthViewModel

bp = Blueprint("auth", __name__)


def _auth_vm() -> AuthViewModel:
    db = extensions.mongo_db
    if db is None:
        raise RuntimeError("MongoDB not initialized")
    return AuthViewModel(UserRepository(db))


@bp.post("/auth/register")
def register():
    """
    Créer un compte et recevoir les tokens JWT.
    ---
    tags:
      - Auth
    summary: Inscription
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
              format: email
            password:
              type: string
              description: Au moins 8 caractères
            role:
              type: string
              enum: [citoyen, agriculteur, chercheur_scientifique]
              description: "Optionnel — défaut citoyen. Alias acceptés : farmer, citizen, researcher, chercheur"
    responses:
      201:
        description: Compte créé ; access_token et refresh_token
      400:
        description: Validation
      409:
        description: E-mail déjà utilisé
    """
    body = request.get_json(silent=True) or {}
    payload, code = _auth_vm().register(
        str(body.get("email", "")),
        str(body.get("password", "")),
        body.get("role"),
    )
    return jsonify(payload), code


@bp.post("/auth/login")
def login():
    """
    Obtenir access_token et refresh_token.
    ---
    tags:
      - Auth
    summary: Connexion
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: Tokens émis
      400:
        description: Champs manquants
      401:
        description: Identifiants invalides
    """
    body = request.get_json(silent=True) or {}
    payload, code = _auth_vm().login(str(body.get("email", "")), str(body.get("password", "")))
    return jsonify(payload), code


@bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    Rafraîchir le access_token avec le refresh_token.
    ---
    tags:
      - Auth
    summary: Refresh token
    security:
      - Bearer: []
    description: "En-tête Authorization avec le refresh JWT (pas l'access)."
    responses:
      200:
        description: Nouveau access_token
      401:
        description: Refresh invalide ou utilisateur absent
    """
    uid = get_jwt_identity()
    payload, code = _auth_vm().refresh(str(uid) if uid is not None else "")
    return jsonify(payload), code


@bp.get("/auth/me")
@jwt_required()
def me():
    """
    Profil utilisateur courant (access_token).
    ---
    tags:
      - Auth
    summary: Profil / moi
    security:
      - Bearer: []
    responses:
      200:
        description: id, email, role, role_label, created_at
      404:
        description: Utilisateur introuvable
    """
    uid = get_jwt_identity()
    payload, code = _auth_vm().me(str(uid) if uid is not None else "")
    return jsonify(payload), code
