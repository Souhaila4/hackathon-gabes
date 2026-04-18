"""Bilingual advisory chat backed by Claude Haiku with heuristic fallback."""

from __future__ import annotations

import os

import requests
from flask import Blueprint, jsonify, request

import phosalert_model
from services import openmeteo_service as owm

bp = Blueprint("chatbot", __name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
REQUEST_TIMEOUT_S = 10


def _pollution_context_block() -> str:
    """Compact bilingual context string built from live or simulated sensors."""
    aq, aq_ok = owm.fetch_air_quality_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
    wind, wind_ok = owm.fetch_wind_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
    if not aq_ok or aq.get("so2") is None:
        sim = phosalert_model.simulate_air_gabes(near_gct=True)
        aq = {**aq, **sim}
    if not wind_ok or wind.get("wind_direction") is None:
        sw = phosalert_model.simulate_wind()
        wind = {"wind_direction": sw["wind_direction_10m"], "wind_speed": sw["wind_speed_10m"]}
    wq = phosalert_model.simulate_water_gulf(near_industrial_plume=True)
    return (
        f"SO2={float(aq.get('so2') or 0):.1f} µg/m³, "
        f"vent {float(wind.get('wind_direction') or 0):.0f}° / {float(wind.get('wind_speed') or 0):.1f} km/h, "
        f"turbidité~{wq['turbidity']:.1f} FNU, chlorophylle~{wq['chlorophyll']:.1f} µg/L."
    )


def _fallback_reply(message: str, language: str) -> tuple[str, str | None]:
    """Short offline answer aligned with farmer/fisher priorities."""
    lower = message.lower()
    risk: str | None = None
    if any(k in lower for k in ("so2", "soufre", "الكبريت")):
        risk = "AIR"
    if any(k in lower for k in ("eau", "بحار", "ماء", "irrigation")):
        risk = "WATER"

    if language == "ar":
        text = (
            "البيانات تشير إلى ضغط صناعي قرب مجموعة منزلق: خفّفوا الري عند الرياح نحو المزرعة، "
            "وتجنبوا الصيد في الطبقة السطحية عندما تبدو المياه عكرة."
        )
        return text, risk

    text = (
        "Les panaches du GCT peuvent charger l’air en SO2 et les eaux en phosphates : "
        "avancez l’irrigation tôt le matin si le vent vient de l’usine, et évitez la pêche "
        "en mer trouble près du jet côtier."
    )
    return text, risk


@bp.post("/chat")
def chat():
    """
    Questions sur la pollution à Gabès (Claude si clé API configurée, sinon fallback).
    ---
    tags:
      - Chat
    summary: Chatbot conseil
    security:
      - Bearer: []
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            message:
              type: string
            language:
              type: string
              enum: [fr, ar]
            user_location:
              type: object
              properties:
                latitude:
                  type: number
                longitude:
                  type: number
    responses:
      200:
        description: Réponse et métadonnées
      500:
        description: Erreur serveur
    """
    try:
        body = request.get_json(silent=True) or {}
        message = str(body.get("message", "")).strip()
        language = str(body.get("language", "fr"))
        loc = body.get("user_location") or {}
        lat = float(loc.get("latitude", phosalert_model.GABES_LAT))
        lon = float(loc.get("longitude", phosalert_model.GABES_LON))

        if language not in ("fr", "ar"):
            language = "fr"

        ctx = _pollution_context_block()
        dist_km = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, lat, lon)

        system_prompt = (
            "Tu es un expert du complexe chimique tunisien (GCT) à Gabès (Ghannouch). "
            "Tu connais les impacts sanitaires et agricoles du SO2, NH3, NO2 et des phosphates "
            "sur les oliviers, palmiers-dattiers, maraîchage et petits pêcheurs du golfe. "
            "Réponds uniquement dans la langue demandée par l’utilisateur (français ou arabe standard tunisien). "
            "Réponse courte : 3 phrases maximum. Conseils concrets pour agriculteurs et pêcheurs. "
            f"Contexte chiffré actuel (indicatif) : {ctx} Distance utilisateur≈{dist_km:.1f} km du site GCT."
        )

        api_key = os.environ.get("CLAUDE_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            reply, related = _fallback_reply(message, language)
            return jsonify({"response": reply, "language": language, "related_risk": related}), 200

        user_block = f"Question: {message}\nLangue attendue: {language}\nCoordonnées: {lat:.5f},{lon:.5f}"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_block}],
        }

        try:
            r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_S)
            r.raise_for_status()
            data = r.json()
            parts = data.get("content") or []
            text = ""
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "text":
                    text += str(p.get("text", ""))
            text = text.strip() or "(vide)"
        except (requests.RequestException, ValueError, KeyError):
            text, related = _fallback_reply(message, language)
            return jsonify({"response": text, "language": language, "related_risk": related}), 200

        lower_msg = message.lower()
        related: str | None = None
        if any(k in lower_msg for k in ("so2", "air", "رياح", "هواء")):
            related = "AIR"
        elif any(k in lower_msg for k in ("eau", "water", "ماء", "بحر")):
            related = "WATER"

        return jsonify({"response": text, "language": language, "related_risk": related}), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc), "ok": False}), 500
