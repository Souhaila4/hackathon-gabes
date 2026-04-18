"""ViewModel tableau de bord agrégé (Flutter home)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import phosalert_model
from services import openmeteo_service as owm

from viewmodels.map_viewmodel import build_zone_markers, fetch_air_wind_bundle


class DashboardViewModel:
    """Payload JSON pour ``GET /api/dashboard``."""

    def build_payload(self) -> tuple[dict[str, Any], int]:
        try:
            aq, wind, ds = fetch_air_wind_bundle()

            so2 = float(aq.get("so2") or 0.0)
            no2 = float(aq.get("no2") or 0.0)
            nh3 = float(aq.get("nh3") or 0.0)
            band, a_score, adv_fr, adv_ar = phosalert_model.air_risk_from_so2(so2)

            air_summary = {
                "so2": round(so2, 2),
                "no2": round(no2, 2),
                "nh3": round(nh3, 2),
                "risk_level": band,
                "risk_score": a_score,
                "color": phosalert_model.air_color(band),
                "advice_fr": adv_fr,
                "advice_ar": adv_ar,
                "wind_direction": round(float(wind.get("wind_direction") or 0.0), 2),
                "wind_speed": round(float(wind.get("wind_speed") or 0.0), 2),
                "data_source": ds,
            }

            wsim = phosalert_model.simulate_water_gulf(near_industrial_plume=True)
            turb = float(wsim["turbidity"])
            chl = float(wsim["chlorophyll"])
            marine, marine_ok = owm.fetch_marine_snapshot(phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
            wds = "simulated"
            if marine_ok and marine.get("chlorophyll") is not None:
                chl = float(marine["chlorophyll"])
                wds = "live"

            wband, wscore = phosalert_model.water_contamination_level(turb, chl)

            phosphate_risk = phosalert_model.haversine_km(
                phosalert_model.GCT_LAT, phosalert_model.GCT_LON, phosalert_model.GABES_LAT, phosalert_model.GABES_LON
            ) < 12.0

            water_summary = {
                "turbidity": round(turb, 2),
                "chlorophyll": round(chl, 2),
                "contamination_level": wband,
                "risk_score": wscore,
                "color": phosalert_model.water_color(wband),
                "phosphate_risk": phosphate_risk,
                "advice_fr": "Surveillez les apports si le panache industriel est orienté vers la mer.",
                "advice_ar": "راقب جودة الري عند انبعاثات قرب الخليج",
                "data_source": wds,
            }

            cop = phosalert_model.haversine_km(phosalert_model.GCT_LAT, phosalert_model.GCT_LON, phosalert_model.GABES_LAT, phosalert_model.GABES_LON)
            downwind = phosalert_model.is_downwind_of_gct(phosalert_model.GABES_LAT, phosalert_model.GABES_LON, float(wind.get("wind_direction") or 0.0))
            sens = phosalert_model.crop_phosphate_sensitivity("vegetables")
            irr_score = phosalert_model.irrigation_risk_score(
                phosalert_model.IrrigationFeatures(
                    distance_km=cop,
                    so2=so2,
                    downwind=downwind,
                    turbidity=turb,
                    crop_sensitivity=sens,
                )
            )
            irrigation_alert = {
                "irrigate_today": irr_score < 55,
                "risk_score": irr_score,
                "risk_level": "FAIBLE" if irr_score < 40 else ("MODÉRÉ" if irr_score < 70 else "ÉLEVÉ"),
                "best_time": "06:00-08:00" if irr_score < 55 else "avoid",
                "advice_fr": "Privilégiez l’irrigation au lever si le risque global reste modéré.",
                "advice_ar": "أفضل وقت: 6 صباحاً - 8 صباحاً إذا كان الخطر محدوداً",
            }

            hist, hist_ok = owm.fetch_air_quality_history(phosalert_model.GABES_LAT, phosalert_model.GABES_LON, past_days=1)
            trend = hist if hist_ok else []
            trend_ds = "live" if hist_ok and trend else "simulated"
            if not trend:
                base = phosalert_model.simulate_air_gabes(near_gct=True)["so2"]
                trend = [{"hour": h % 24, "so2": round(base + (h % 5) * 1.2, 2)} for h in range(24)]

            wd_deg = float(wind.get("wind_direction") or 0.0)
            scored_zones = sorted(
                build_zone_markers(so2, wd_deg),
                key=lambda z: int(z.get("risk_score", 0)),
                reverse=True,
            )
            top3 = scored_zones[:3]
            aggregate_source = "live" if ds == "live" and trend_ds == "live" else "simulated"
            last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            body = {
                "air_quality": air_summary,
                "water_quality": water_summary,
                "irrigation_alert": irrigation_alert,
                "top_zones": top3,
                "so2_trend_24h": trend[-24:],
                "last_updated": last_updated,
                "data_source": aggregate_source,
            }
            return body, 200
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "ok": False}, 500
