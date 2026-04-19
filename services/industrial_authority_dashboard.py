"""
Tableaux de bord **Industriel (GCT)** et **Autorité (ANPE)** — données agrégées
(Open-Meteo Gabès + modèle zones + métadonnées de conformité indicative).

Les seuils « Tunisie » ci-dessous sont des placeholders documentaires pour prototype ;
l’application réelle doit être alignée sur textes réglementaires officiels.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from services.dashboard_service import (
    AIR_QUALITY_URL,
    WHO_LIMITS_UGM3,
    _fetch_current_air,
    _fetch_water_dynamic,
    _fetch_wind,
)
from services.gabes_zone_scores import build_unified_zone_rows

GCT_LAT = 33.88
GCT_LON = 10.09
GABES_LAT = 33.8869
GABES_LON = 10.0982

# Limites nationales indicatives (µg/m³) — placeholders hackathon ; à remplacer par valeurs légales.
TN_LIMITS_UGM3 = {"SO2": 350.0, "NO2": 200.0, "NH3": 200.0}

# ─── Métadonnées statiques par rôle (démo / distinction UX — pas de données métier inventées chiffrées) ───


def _regulatory_bridge_gct_perspective() -> dict[str, Any]:
    """Relation ANPE ↔ GCT : même schéma logique, vue côté site industriel."""
    return {
        "relationship_id": "ANPE_GCT_REG_CHAIN_v1",
        "summary_fr": (
            "PhosAlert relie l’inspection (ANPE) et l’exploitant (GCT) : notification traçable, "
            "réponse documentée — deux écrans, une chaîne de confiance."
        ),
        "counterpart_role": "autorite",
        "your_role_in_flow_fr": "Réception des avis, mise en œuvre technique, preuve de suivi.",
        "flow_steps": [
            {
                "step": 1,
                "actor_role": "autorite",
                "label_fr": "Constat / courrier ANPE",
                "icon": "gavel",
            },
            {
                "step": 2,
                "actor_role": "system",
                "label_fr": "Enregistrement PhosAlert (MongoDB)",
                "icon": "storage",
            },
            {
                "step": 3,
                "actor_role": "industriel",
                "label_fr": "Inbox GCT + actions correctives",
                "icon": "factory",
            },
        ],
        "api_hooks_fr": "POST /api/regulatory/notices (ANPE) → GET …/inbox (GCT).",
    }


def _regulatory_bridge_anpe_perspective() -> dict[str, Any]:
    """Même relation, vue côté autorité."""
    return {
        "relationship_id": "ANPE_GCT_REG_CHAIN_v1",
        "summary_fr": (
            "Interface inspection : les avis émis alimentent le dossier numérique partagé "
            "visible côté site pour alignement public / technique."
        ),
        "counterpart_role": "industriel",
        "your_role_in_flow_fr": "Qualifier la non-conformité, formaliser l’avis, suivre le calendrier.",
        "flow_steps": [
            {
                "step": 1,
                "actor_role": "autorite",
                "label_fr": "Rapport terrain & notification",
                "icon": "assignment",
            },
            {
                "step": 2,
                "actor_role": "system",
                "label_fr": "Horodatage & historique « sent »",
                "icon": "timeline",
            },
            {
                "step": 3,
                "actor_role": "industriel",
                "label_fr": "Accusé de réception implicite (inbox)",
                "icon": "mark_email_read",
            },
        ],
        "api_hooks_fr": "Émission : POST /api/regulatory/notices · Suivi : GET …/sent.",
    }


def _digital_twin_demo_stub() -> dict[str, Any]:
    """Idée prototype : jumeau « état / risque » sans simuler de SCADA réel."""
    return {
        "concept_fr": "Jumeau contextuel Gabès — agrège air, vent et zones modèle (démo statique).",
        "layers_static_fr": [
            "Couche émissions (SO₂, NH₃, NO₂)",
            "Couche vent & dispersion simplifiée",
            "Couche pression sociétale (zones sensibles)",
        ],
        "roadmap_fr": "Phase 2 : boucle SCADA / IoT site + maillage 3D facultatif.",
        "demo_badge_fr": "Innovation — proof of concept",
    }


def _static_role_identity_industriel() -> dict[str, Any]:
    return {
        "profile_kind": "industrial_operator",
        "organization_fr": "Groupe chimique tunisien — site Gabès (GCT)",
        "organization_short": "GCT",
        "role_badge_fr": "Exploitant — pilotage émissions & conformité",
        "tagline_fr": "Réduire l’impact, prouver la réponse réglementaire.",
        "accent_token": "industrial_steel",
        "how_you_differ_fr": (
            "Seul ce profil combine relevés site, score conformité indicative et "
            "boîte de réception des avis ANPE dans l’app."
        ),
        "static_highlights_fr": [
            "Vue « infrastructure » : leviers techniques (FGD, NH₃, phosphogypse).",
            "Même carte de fond que les citoyens, mais centrée obligation de résultat.",
        ],
        "demo_contact_placeholder_fr": "Cellule environnement site — démo hackathon",
    }


def _static_role_identity_autorite() -> dict[str, Any]:
    return {
        "profile_kind": "regulatory_authority",
        "organization_fr": "Agence nationale de protection de l’environnement — perspective Gabès",
        "organization_short": "ANPE",
        "role_badge_fr": "Autorité — inspection & obligation de contrôle",
        "tagline_fr": "Prioriser les populations exposées, formaliser la chaîne décisionnelle.",
        "accent_token": "authority_teal",
        "how_you_differ_fr": (
            "Seul ce profil peut émettre des notifications formelles vers le dossier industriel "
            "depuis PhosAlert (démo technique)."
        ),
        "static_highlights_fr": [
            "Vue synthèse non-conformités liée aux seuils indicatifs OMS.",
            "Plan d’actions et générateur de rapport structuré pour la démo.",
        ],
        "demo_contact_placeholder_fr": "Pôle inspection Gabès — démo hackathon",
    }


def _fetch_air_hourly_days(past_days: int, forecast_days: int = 1) -> dict[str, Any] | None:
    params = {
        "latitude": GABES_LAT,
        "longitude": GABES_LON,
        "hourly": "sulphur_dioxide,nitrogen_dioxide,ammonia",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    try:
        resp = requests.get(AIR_QUALITY_URL, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError, KeyError):
        return None


def _seven_day_so2_hourly() -> list[dict[str, Any]]:
    raw = _fetch_air_hourly_days(past_days=7, forecast_days=0)
    if not raw or "hourly" not in raw:
        return []
    hourly = raw["hourly"]
    times: list[str] = hourly["time"]
    so2: list[Any] = hourly["sulphur_dioxide"]
    out = []
    for i in range(len(times)):
        out.append(
            {
                "time": times[i],
                "so2": float(so2[i] or 0.0) if i < len(so2) else 0.0,
            }
        )
    return out


def _ratio_vs_who(pollutant: str, value: float) -> float:
    lim = WHO_LIMITS_UGM3.get(pollutant, 1.0)
    if lim <= 0:
        return 0.0
    return round(value / lim, 2)


def build_industriel_dashboard() -> dict[str, Any]:
    air = _fetch_current_air()
    wind = _fetch_wind()
    water = _fetch_water_dynamic()
    so2 = float(air["so2_ugm3"])
    nh3 = float(air["nh3_ugm3"])
    no2 = float(air["no2_ugm3"])
    zones = build_unified_zone_rows(so2, float(wind["direction_deg"]), float(wind["speed_kmh"]))

    series_7d = _seven_day_so2_hourly()
    daily_peaks: list[dict[str, Any]] = []
    if series_7d:
        by_day: dict[str, list[float]] = {}
        for row in series_7d:
            d = row["time"][:10]
            by_day.setdefault(d, []).append(row["so2"])
        for d in sorted(by_day.keys())[-7:]:
            vals = by_day[d]
            daily_peaks.append({"date": d, "so2_max": round(max(vals), 2), "so2_avg": round(sum(vals) / len(vals), 2)})

    pollutants = [
        {
            "id": "SO2",
            "name_fr": "Dioxyde de soufre",
            "name_ar": "ثاني أكسيد الكبريت",
            "unit": "µg/m³",
            "current": so2,
            "who_limit": WHO_LIMITS_UGM3["SO2"],
            "tn_limit_indicative": TN_LIMITS_UGM3["SO2"],
            "ratio_who": _ratio_vs_who("SO2", so2),
            "status": "ALERT" if so2 > WHO_LIMITS_UGM3["SO2"] else "OK",
            "color": "red" if so2 > WHO_LIMITS_UGM3["SO2"] else "green",
        },
        {
            "id": "NH3",
            "name_fr": "Ammoniac",
            "name_ar": "أمونياك",
            "unit": "µg/m³",
            "current": nh3,
            "who_limit": WHO_LIMITS_UGM3["NH3"],
            "tn_limit_indicative": TN_LIMITS_UGM3["NH3"],
            "ratio_who": _ratio_vs_who("NH3", nh3),
            "status": "ALERT" if nh3 > WHO_LIMITS_UGM3["NH3"] else "OK",
            "color": "red" if nh3 > WHO_LIMITS_UGM3["NH3"] else "orange",
        },
        {
            "id": "NO2",
            "name_fr": "Dioxyde d’azote",
            "name_ar": "ثاني أكسيد النيتروجين",
            "unit": "µg/m³",
            "current": no2,
            "who_limit": WHO_LIMITS_UGM3["NO2"],
            "tn_limit_indicative": TN_LIMITS_UGM3["NO2"],
            "ratio_who": _ratio_vs_who("NO2", no2),
            "status": "ALERT" if no2 > WHO_LIMITS_UGM3["NO2"] else "OK",
            "color": "red" if no2 > WHO_LIMITS_UGM3["NO2"] else "green",
        },
    ]

    solutions = [
        {
            "id": "fgd",
            "title_fr": "Désulfuration FGD (flue gas desulfurization)",
            "title_ar": "إزالة الكبريت من الغازات",
            "priority": "CRITICAL",
            "summary_fr": "Réduction majeure des émissions SO₂ ; priorité si ratio OMS > 2.",
            "cost_range_musd": "40–120",
            "timeline_months": "18–36",
            "so2_reduction_pct_estimate": 85,
        },
        {
            "id": "nh3_abatement",
            "title_fr": "Captage et traitement NH₃ (scrubbers / optimisation urée)",
            "title_ar": "تخفيض الأمونياك",
            "priority": "URGENT",
            "summary_fr": "Réduit les pics NH₃ et risques sanitaires à l’échelle locale.",
            "cost_range_musd": "8–25",
            "timeline_months": "12–24",
            "so2_reduction_pct_estimate": 0,
        },
        {
            "id": "pg_management",
            "title_fr": "Plan phosphogypse (stockage / mer / valorisation)",
            "title_ar": "إدارة الفوسفوجيبس",
            "priority": "IMPORTANT",
            "summary_fr": "Réduction déversements côtiers ; impact marin et cadmium.",
            "cost_range_musd": "15–50",
            "timeline_months": "24–60",
            "so2_reduction_pct_estimate": 0,
        },
    ]

    score_base = 100
    if so2 > WHO_LIMITS_UGM3["SO2"]:
        score_base -= min(40, int((so2 / WHO_LIMITS_UGM3["SO2"]) * 15))
    if nh3 > WHO_LIMITS_UGM3["NH3"]:
        score_base -= 25
    if no2 > WHO_LIMITS_UGM3["NO2"]:
        score_base -= 20
    compliance_score = max(0, min(100, score_base))

    impact_zones = [
        {
            "zone_id": z["id"],
            "name_fr": z["name"],
            "risk_level": z["risk_level"],
            "population_indicative": 12000 + z["id"] * 800,
            "health_note_fr": "Irritation respiratoire possible si vent vers le nord-est.",
        }
        for z in zones[:5]
    ]

    return {
        "role": "industriel",
        "module": "industrial_gct",
        "role_identity": _static_role_identity_industriel(),
        "regulatory_bridge": _regulatory_bridge_gct_perspective(),
        "digital_twin_demo": _digital_twin_demo_stub(),
        "screen_emissions": {
            "title_fr": "Émissions temps réel — site GCT (réf. Gabès)",
            "title_ar": "الانبعاثات اللحظية",
            "air_quality": air,
            "wind": wind,
            "pollutants": pollutants,
            "morning_brief_fr": (
                f"Relevé : SO₂ {so2} µg/m³ (OMS {WHO_LIMITS_UGM3['SO2']}). "
                "Si ratio > 3× OMS : réduire charges sources / vérifier FGD."
            ),
        },
        "screen_violation_detail_template": {
            "pollutants": pollutants,
            "series_so2_7d": daily_peaks,
            "who_limits": WHO_LIMITS_UGM3,
            "tn_limits_indicative": TN_LIMITS_UGM3,
            "map_center": {"latitude": GCT_LAT, "longitude": GCT_LON},
            "impact_radius_km_default": 12,
        },
        "screen_infrastructure_plan": {"solutions": solutions},
        "screen_compliance": {
            "score": compliance_score,
            "breakdown": {
                "SO2": max(0, 100 - int(_ratio_vs_who("SO2", so2) * 25)),
                "NH3": max(0, 100 - int(_ratio_vs_who("NH3", nh3) * 30)),
                "NO2": max(0, 100 - int(_ratio_vs_who("NO2", no2) * 20)),
            },
            "history_30d_placeholder": True,
            "projection_with_fgd_fr": "Avec FGD opérationnel à −85 % SO₂, score projeté ≈ "
            f"{min(100, compliance_score + 35)}.",
        },
        "screen_impact_gabes": {
            "water_coastal": water,
            "zones": impact_zones,
            "marine_note_fr": "Indicateurs côtiers (turbidité / métaux) : suivi renforcé recommandé.",
            "economic_note_fr": "Coût sanitaire et agricole indicatif lié aux pics — à modéliser localement.",
        },
        "screen_solution_detail_example": {
            "id": "fgd",
            "technical_fr": "Unité FGD humide : absorption SO₂ par suspension calcaire ; boues contrôlées.",
            "before_so2_t_per_year_indicative": 18000,
            "after_so2_reduction_pct": 85,
            "roi_note_fr": "ROI typique 5–12 ans selon coût énergie et contraintes site.",
        },
        "alerts": _alerts_industrial(so2, nh3, no2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": ["Open-Meteo", "phosalert_model zones", "Indicative TN limits (placeholder)"],
    }


def _alerts_industrial(so2: float, nh3: float, no2: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    aid = 1
    if so2 > WHO_LIMITS_UGM3["SO2"]:
        out.append(
            {
                "id": aid,
                "type": "SO2_EXCEEDANCE_SITE",
                "level": "DANGEROUS",
                "color": "red",
                "title_fr": f"SO₂ dépassement OMS : {so2:.1f} µg/m³",
                "title_ar": f"تجاوز ثاني أكسيد الكبريت {so2:.1f}",
                "roles": ["industriel"],
            }
        )
        aid += 1
    if nh3 > WHO_LIMITS_UGM3["NH3"]:
        out.append(
            {
                "id": aid,
                "type": "NH3_EXCEEDANCE_SITE",
                "level": "WARNING",
                "color": "orange",
                "title_fr": f"NH₃ élevé : {nh3:.2f} µg/m³",
                "roles": ["industriel"],
            }
        )
    return out


def build_autorite_dashboard() -> dict[str, Any]:
    air = _fetch_current_air()
    wind = _fetch_wind()
    so2 = float(air["so2_ugm3"])
    nh3 = float(air["nh3_ugm3"])
    no2 = float(air["no2_ugm3"])

    violations = []
    vid = 1
    if so2 > WHO_LIMITS_UGM3["SO2"]:
        violations.append(
            {
                "id": vid,
                "pollutant": "SO2",
                "current_ugm3": so2,
                "who_limit": WHO_LIMITS_UGM3["SO2"],
                "ratio_who": _ratio_vs_who("SO2", so2),
                "severity": "HIGH",
                "duration_days_estimate": 1,
                "law_article_fr": "Code environnement (Tunisie) — exercice d’inspection (réf. à préciser sur site).",
                "who_ref": "WHO Air Quality Guidelines",
                "recommended_action_fr": "Mise en demeure technique + plan de réduction sous 90 j.",
                "color": "red",
            }
        )
        vid += 1
    if nh3 > WHO_LIMITS_UGM3["NH3"]:
        violations.append(
            {
                "id": vid,
                "pollutant": "NH3",
                "current_ugm3": nh3,
                "who_limit": WHO_LIMITS_UGM3["NH3"],
                "ratio_who": _ratio_vs_who("NH3", nh3),
                "severity": "MEDIUM",
                "duration_days_estimate": 1,
                "law_article_fr": "Nuisances et dangers — mesures de réduction NH₃.",
                "who_ref": "WHO",
                "recommended_action_fr": "Contrôle des installations urée / scrubbers.",
                "color": "orange",
            }
        )

    overview = {
        "active_violations": len(violations),
        "compliance_score_gct_indicative": max(0, 100 - int(len(violations) * 22)),
        "population_at_risk_indicative": 85000 if violations else 12000,
        "trend_week_fr": "En dégradation" if violations else "Stable",
        "wind": wind,
    }

    timeline = []
    for i in range(7):
        d = (datetime.now(timezone.utc) - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        timeline.append(
            {
                "date": d,
                "events": (
                    [{"type": "VIOLATION", "pollutant": "SO2"}]
                    if i == 6 and violations
                    else []
                ),
            }
        )

    return {
        "role": "autorite",
        "module": "authority_anpe",
        "role_identity": _static_role_identity_autorite(),
        "regulatory_bridge": _regulatory_bridge_anpe_perspective(),
        "digital_twin_demo": _digital_twin_demo_stub(),
        "screen_overview": overview,
        "screen_violations_list": {"violations": violations, "sort_options": ["severity", "duration", "pollutant"]},
        "screen_violation_legal": {"items": violations},
        "screen_population_map": {
            "center": {"latitude": GABES_LAT, "longitude": GABES_LON},
            "zones_file": "zones from model",
            "wind_direction_deg": wind["direction_deg"],
            "vulnerable_sites_fr": ["Hôpital régional", "Écoles centre-ville", "Zones agricoles Sud"],
        },
        "screen_timeline": {"days": timeline},
        "screen_action_plan": {
            "actions": [
                {
                    "id": 1,
                    "title_fr": "Notification formelle GCT",
                    "deadline_days": 15,
                    "status": "pending",
                    "doc_fr": "Courrier recommandé + synthèse mesures",
                },
                {
                    "id": 2,
                    "title_fr": "Contrôle sur site NH₃",
                    "deadline_days": 30,
                    "status": "pending",
                    "doc_fr": "PV inspection",
                },
            ]
        },
        "screen_report_generator": {
            "template_id": "ANPE_GABES_V1",
            "fields_auto": ["violations", "who_limits", "wind", "timestamp"],
            "disclaimer_fr": "Rapport indicatif hackathon — valider sources officielles.",
        },
        "air_quality": air,
        "alerts": _alerts_autorite(violations),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": ["Open-Meteo", "WHO limits (indicative)"],
    }


def _alerts_autorite(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not violations:
        return []
    return [
        {
            "id": 1,
            "type": "INSPECTION_REQUIRED",
            "level": "WARNING",
            "color": "orange",
            "title_fr": f"{len(violations)} non-conformité(s) active(s) — Gabès / GCT",
            "roles": ["autorite"],
        }
    ]
