"""
Moteur d'alertes — fusion NAFAS, qualité de l'air, eau, vent (données dynamiques).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services import dashboard_service as ds


WHO_SO2 = ds.WHO_LIMITS_UGM3["SO2"]


def _score_to_alert_level(score: int) -> str:
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "DANGEROUS"
    if score >= 25:
        return "MODERATE"
    return "SAFE"


def _hour_so2_risk(so2: float) -> str:
    if so2 > WHO_SO2 * 2:
        return "DANGEROUS"
    if so2 > WHO_SO2:
        return "MODERATE"
    return "SAFE"


def run_alert_engine() -> dict[str, Any]:
    """
    Agrège les entrées temps réel et produit scores zones, alertes, prévision 48h.
    """
    air = ds._fetch_current_air()
    wind = ds._fetch_wind()
    water = ds._fetch_water_dynamic()
    nafas = ds._fetch_nafas_safe()
    raw_zones = ds._calculate_zones(air, wind)

    zone_scores: list[dict[str, Any]] = []
    for z in raw_zones:
        sc = int(z["risk_score"])
        lvl = _score_to_alert_level(sc)
        zone_scores.append(
            {
                "id": z["id"],
                "name": z["name"],
                "risk_score": sc,
                "risk_level": lvl,
                "color": z["color"],
                "is_safe": z["is_safe"],
                "distance_gct_km": z["distance_gct_km"],
            }
        )

    zone_scores.sort(key=lambda x: x["risk_score"], reverse=True)
    highest = zone_scores[0] if zone_scores else {"name": "N/A", "risk_score": 0, "risk_level": "SAFE"}

    critical_zones = len([z for z in zone_scores if z["risk_level"] in ("CRITICAL", "DANGEROUS")])
    safe_zones = len([z for z in zone_scores if z["is_safe"]])

    affected_population = min(
        950_000,
        max(0, critical_zones * 18_000 + (8 - safe_zones) * 4_500),
    )

    overall = highest["risk_level"]
    if air["risk_level"] == "DANGEROUS" and overall == "SAFE":
        overall = "MODERATE"

    forecast_48h: list[dict[str, Any]] = []
    for row in air.get("forecast_48h", [])[:48]:
        so2v = float(row.get("so2") or 0.0)
        forecast_48h.append(
            {
                "time": row.get("time"),
                "so2": so2v,
                "risk_level": _hour_so2_risk(so2v),
            }
        )

    alerts: list[dict[str, Any]] = []
    if air["so2_ugm3"] > WHO_SO2:
        alerts.append(
            {
                "level": "DANGEROUS",
                "title_fr": f"SO2 dépasse le seuil indicatif ({air['so2_ugm3']:.1f} µg/m³)",
            }
        )
    if water.get("contamination_level") == "CONTAMINATED":
        alerts.append(
            {
                "level": "CRITICAL",
                "title_fr": f"Eau côtière / fichier — turbidité élevée ({water.get('turbidity_FNU')} FNU)",
            }
        )
    if nafas and nafas.get("ok") and nafas.get("exceeds_WHO"):
        alerts.append(
            {
                "level": "CRITICAL",
                "title_fr": "NAFAS : dépassement seuils OMS sur la fenêtre 48h",
            }
        )

    model_weights = {
        "air": 0.30,
        "nafas": 0.25,
        "water": 0.20,
        "wind": 0.15,
        "weather": 0.10,
    }

    return {
        "summary": {
            "overall_level": overall,
            "critical_zones": critical_zones,
            "safe_zones": safe_zones,
            "affected_population": affected_population,
            "highest_risk_zone": highest["name"],
        },
        "zone_scores": zone_scores,
        "alerts": alerts,
        "forecast_48h": forecast_48h,
        "model_weights": model_weights,
        "air_snapshot": {
            "so2_ugm3": air["so2_ugm3"],
            "risk_level": air["risk_level"],
        },
        "nafas_ok": bool(nafas and nafas.get("ok")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    print("Testing Alert Engine...\n")
    print("=" * 50)

    try:
        print("Step 1: Collecting inputs...")
        print("   -> NAFAS predictions")
        print("   -> Water quality")
        print("   -> Wind data (Open-Meteo)")
        print("   -> Weather / air (Open-Meteo)")

        result = run_alert_engine()

        print("\nAlert Engine completed successfully!")
        print("=" * 50)

        s = result["summary"]
        print("\nSUMMARY:")
        print(f"   Overall level      : {s['overall_level']}")
        print(f"   Critical zones     : {s['critical_zones']}")
        print(f"   Safe zones         : {s['safe_zones']}")
        print(f"   Affected population: {s['affected_population']:,}")
        print(f"   Highest risk zone  : {s['highest_risk_zone']}")

        print("\nZONE SCORES:")
        for z in sorted(result["zone_scores"], key=lambda x: x["risk_score"], reverse=True):
            mark = (
                "[!]" if z["risk_level"] == "CRITICAL"
                else "[+]" if z["risk_level"] == "DANGEROUS"
                else "[~]" if z["risk_level"] == "MODERATE"
                else "[ok]"
            )
            print(
                f"   {mark} {z['name']:28} score={z['risk_score']:3}/100 level={z['risk_level']}"
            )

        print(f"\nALERTS ({len(result['alerts'])}):")
        if result["alerts"]:
            for a in result["alerts"]:
                print(f"   [{a['level']}] {a['title_fr']}")
        else:
            print("   No alerts — conditions acceptable")

        forecast = result["forecast_48h"]
        if forecast:
            critical_hours = sum(
                1 for f in forecast if f["risk_level"] in ("CRITICAL", "DANGEROUS")
            )
            print("\nFORECAST 48H:")
            print(f"   Total hours       : {len(forecast)}")
            print(f"   High risk hours   : {critical_hours}")
            print(f"   First hour risk   : {forecast[0]['risk_level']}")

        print("\nMODEL WEIGHTS:")
        for k, v in result["model_weights"].items():
            print(f"   {k:10} : {v}")

        print(f"\nGenerated at: {result['generated_at']}")
        print("\nAlert Engine — NAFAS+Water+Wind+Weather OK!")

    except requests.exceptions.ConnectionError as e:
        print(f"\nNetwork error: {e}")
        print("   Check internet connection")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("\nAPI timeout — Open-Meteo unreachable")
        print("   Try again in a few seconds")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
