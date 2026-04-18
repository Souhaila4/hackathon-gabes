#!/usr/bin/env python3
"""
Fetch Gulf of Gabès water quality proxies (CHL, turbidity proxy, SPM) via Copernicus Marine,
with simulated fallback for PhosAlert.
"""

from __future__ import annotations

import os
from pathlib import Path

import copernicusmarine
import numpy as np
import pandas as pd


# ── CONFIGURATION ─────────────────────────────────────────────────────────────
GABES_CONFIG = {
    "dataset_id": "OCEANCOLOUR_MED_BGC_HR_L3_NRT_009_205",
    "variables": ["CHL", "TUR", "SPM"],
    "minimum_longitude": 9.8,
    "maximum_longitude": 10.5,
    "minimum_latitude": 33.5,
    "maximum_latitude": 34.2,
    "start_datetime": "2026-04-11",
    "end_datetime": "2026-04-18",
}

GCT_LOCATION = {
    "latitude": 33.88,
    "longitude": 10.09,
    "name": "Zone Industrielle GCT Ghannouch",
}

# Sorties dans ``phosalert-backend/data/`` (racine du projet = parent du dossier ``scripts``)
_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"
_DATA.mkdir(parents=True, exist_ok=True)
OUTPUT_REAL = str(_DATA / "gabes_water_quality.csv")
OUTPUT_SIMULATED = str(_DATA / "gabes_water_quality_simulated.csv")


def emergency_fallback_dataframe() -> pd.DataFrame:
    """Single-row simulated sample so the script always produces a CSV."""
    df = pd.DataFrame(
        [
            {
                "date": "2026-04-18",
                "zone_name": "Gabès — secours",
                "latitude": GCT_LOCATION["latitude"],
                "longitude": GCT_LOCATION["longitude"],
                "CHL": 6.5,
                "TUR": 11.0,
                "SPM": 17.0,
                "data_source": "simulated_emergency",
            }
        ]
    )
    df = add_risk_classification(df)
    df.to_csv(OUTPUT_SIMULATED, index=False)
    print_summary(df, source="SIMULATED Emergency Fallback")
    return df


def _normalize_variable_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to CHL / TUR / SPM when Copernicus uses variants."""
    rename_map: dict[str, str] = {}
    cols_upper = {str(c).upper(): c for c in df.columns}

    # Common CMEMS synonym patterns for this family of products
    synonyms = [
        ("CHL", ["CHL", "CHLA", "CHLOR_A", "CHLOROPHYLL"]),
        ("TUR", ["TUR", "KD490", "TURBIDITY"]),
        ("SPM", ["SPM", "TSM"]),
    ]

    for target, keys in synonyms:
        if target in cols_upper.values():
            continue
        for k in keys:
            ku = k.upper()
            if ku in cols_upper:
                rename_map[str(cols_upper[ku])] = target
                break

    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def fetch_gabes_water_quality() -> pd.DataFrame:
    """
    Fetch real water quality data for Gulf of Gabès from Copernicus Marine Service.

    Returns:
        DataFrame with CHL, TUR, SPM values (and risk columns after classification).
    """
    print("=" * 50)
    print("🌊 PhosAlert — Fetching Gabès Water Quality")
    print("=" * 50)

    try:
        print("\n📡 Connecting to Copernicus Marine...")
        print("⚠️  Enter your Copernicus Marine credentials (or rely on cached login)")
        print("    Tip: set COPERNICUSMARINE_USERNAME / COPERNICUSMARINE_PASSWORD for scripts non-interactifs.")
        copernicusmarine.login()

        print("\n⬇️  Downloading Gabès zone data...")
        print(f"   Dataset : {GABES_CONFIG['dataset_id']}")
        print(f"   Variables: {GABES_CONFIG['variables']}")
        print(
            f"   Zone     : Lat {GABES_CONFIG['minimum_latitude']}"
            f"-{GABES_CONFIG['maximum_latitude']},"
            f" Lon {GABES_CONFIG['minimum_longitude']}"
            f"-{GABES_CONFIG['maximum_longitude']}"
        )
        print(f"   Period   : {GABES_CONFIG['start_datetime']} to {GABES_CONFIG['end_datetime']}")
        print(f"   Référence GCT : {GCT_LOCATION['name']} ({GCT_LOCATION['latitude']}, {GCT_LOCATION['longitude']})")

        data = copernicusmarine.open_dataset(
            dataset_id=GABES_CONFIG["dataset_id"],
            variables=GABES_CONFIG["variables"],
            minimum_longitude=GABES_CONFIG["minimum_longitude"],
            maximum_longitude=GABES_CONFIG["maximum_longitude"],
            minimum_latitude=GABES_CONFIG["minimum_latitude"],
            maximum_latitude=GABES_CONFIG["maximum_latitude"],
            start_datetime=GABES_CONFIG["start_datetime"],
            end_datetime=GABES_CONFIG["end_datetime"],
        )

        print("\n🔄 Processing data...")
        df = data.to_dataframe().reset_index()
        df = _normalize_variable_columns(df)

        required = ["CHL", "TUR", "SPM"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Colonnes attendues manquantes après chargement : {missing}")

        df = df.dropna(subset=["CHL", "TUR", "SPM"], how="any")
        if df.empty:
            raise ValueError("Jeu de données vide après suppression des NA — voir granule ou fenêtre temporelle.")

        df["data_source"] = "copernicus"

        df = add_risk_classification(df)

        df.to_csv(OUTPUT_REAL, index=False)

        print_summary(df, source="REAL Copernicus Data")

        return df

    except Exception as e:
        print(f"\n⚠️  Copernicus API Error: {e}")
        print("🔄 Switching to simulated data...")
        try:
            return generate_simulated_data()
        except Exception as sim_err:  # noqa: BLE001 — dernier filet de sécurité
            print(f"\n⚠️  Simulation Error: {sim_err}")
            print("🔄 Using minimal emergency fallback row...")
            return emergency_fallback_dataframe()


def add_risk_classification(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add risk level based on GCT pollution thresholds for Gulf of Gabès specifically.

    Thresholds based on published research on GCT impact:
    - CHL > 5 µg/L  = high eutrophication (phosphate from GCT)
    - TUR > 10 FNU  = contaminated (industrial discharge)
    - SPM > 15 mg/L = heavy suspension (GCT waste)
    """

    def classify_risk(row: pd.Series) -> pd.Series:
        score = 0
        reasons: list[str] = []

        chl = float(row.get("CHL", 0) or 0)
        tur = float(row.get("TUR", 0) or 0)
        spm = float(row.get("SPM", 0) or 0)

        if chl > 5:
            score += 40
            reasons.append("High chlorophyll — phosphate contamination")
        elif chl > 3:
            score += 20
            reasons.append("Moderate chlorophyll")

        if tur > 10:
            score += 40
            reasons.append("High turbidity — industrial discharge")
        elif tur > 5:
            score += 20
            reasons.append("Moderate turbidity")

        if spm > 15:
            score += 20
            reasons.append("High suspended matter")

        notes = "; ".join(reasons)

        if score >= 60:
            level = "CONTAMINATED"
            color = "red"
            advice_fr = "Ne pas utiliser cette eau"
            advice_ar = "لا تستخدم هذا الماء"
        elif score >= 30:
            level = "SUSPECT"
            color = "orange"
            advice_fr = "Utiliser avec précaution"
            advice_ar = "استخدم بحذر"
        else:
            level = "CLEAN"
            color = "green"
            advice_fr = "Eau utilisable normalement"
            advice_ar = "الماء صالح للاستخدام"

        return pd.Series(
            {
                "risk_score": score,
                "risk_level": level,
                "color": color,
                "advice_fr": advice_fr,
                "advice_ar": advice_ar,
                "risk_notes": notes,
            }
        )

    risk_data = df.apply(classify_risk, axis=1)
    return pd.concat([df, risk_data], axis=1)


def generate_simulated_data() -> pd.DataFrame:
    """
    Generate realistic simulated data based on published research on GCT pollution in Gulf of Gabès.

    Values based on:
    - Katlane et al. 2012: Chlorophyll & turbidity in Gulf of Gabès
    - EU Study 2018: GCT discharge impact on Mediterranean
    """
    print("\n📊 Generating simulated Gabès water quality data...")
    print("   Based on: Katlane et al. 2012, EU GCT Study 2018")

    dates = pd.date_range(
        start="2026-04-11",
        end="2026-04-18",
        freq="D",
    )

    zones = [
        {
            "name": "Zone GCT Ghannouch",
            "latitude": 33.88,
            "longitude": 10.09,
            "chl_base": 7.0,
            "tur_base": 13.0,
            "spm_base": 18.0,
        },
        {
            "name": "Port de Gabès",
            "latitude": 33.89,
            "longitude": 10.11,
            "chl_base": 5.5,
            "tur_base": 9.5,
            "spm_base": 14.0,
        },
        {
            "name": "Chott Essalem",
            "latitude": 33.87,
            "longitude": 10.08,
            "chl_base": 6.0,
            "tur_base": 11.0,
            "spm_base": 16.0,
        },
        {
            "name": "Zone Agricole Nord",
            "latitude": 33.95,
            "longitude": 10.07,
            "chl_base": 2.5,
            "tur_base": 4.0,
            "spm_base": 6.0,
        },
        {
            "name": "Plage de Gabès",
            "latitude": 33.90,
            "longitude": 10.12,
            "chl_base": 4.5,
            "tur_base": 7.5,
            "spm_base": 11.0,
        },
    ]

    rows: list[dict[str, object]] = []
    rng = np.random.default_rng(int(os.environ.get("PHOSALERT_SEED", "42")))
    for date in dates:
        for zone in zones:
            variation = float(rng.uniform(-0.5, 0.5))

            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "zone_name": zone["name"],
                    "latitude": zone["latitude"],
                    "longitude": zone["longitude"],
                    "CHL": round(zone["chl_base"] + variation, 2),
                    "TUR": round(zone["tur_base"] + variation, 2),
                    "SPM": round(zone["spm_base"] + variation, 2),
                    "data_source": "simulated",
                }
            )

    df = pd.DataFrame(rows)
    df = add_risk_classification(df)

    df.to_csv(OUTPUT_SIMULATED, index=False)

    print_summary(df, source="SIMULATED Data (based on research)")
    return df


def print_summary(df: pd.DataFrame, source: str = "") -> None:
    """Print a clear summary of water quality data."""
    print("\n" + "=" * 50)
    print(f"✅ WATER QUALITY SUMMARY — {source}")
    print("=" * 50)

    print(f"\n📊 Total records : {len(df)}")

    if "CHL" in df.columns:
        print("\n🌿 Chlorophylle (CHL):")
        print(f"   Average : {df['CHL'].mean():.2f} µg/L")
        print(f"   Max     : {df['CHL'].max():.2f} µg/L")
        print(f"   Min     : {df['CHL'].min():.2f} µg/L")

    if "TUR" in df.columns:
        print("\n💧 Turbidité (TUR):")
        print(f"   Average : {df['TUR'].mean():.2f} FNU")
        print(f"   Max     : {df['TUR'].max():.2f} FNU")
        print(f"   Min     : {df['TUR'].min():.2f} FNU")

    if "SPM" in df.columns:
        print("\n🏭 Matières suspension (SPM):")
        print(f"   Average : {df['SPM'].mean():.2f} mg/L")

    if "risk_level" in df.columns:
        print("\n⚠️  Risk Distribution:")
        risk_counts = df["risk_level"].value_counts()
        for level, count in risk_counts.items():
            emoji = "🔴" if level == "CONTAMINATED" else "🟠" if level == "SUSPECT" else "🟢"
            print(f"   {emoji} {level}: {count} records")

    print("\n💾 Data saved to CSV successfully")
    print("=" * 50)


if __name__ == "__main__":
    df = fetch_gabes_water_quality()

    print("\n🎯 First 5 rows of data:")
    cols = [c for c in ["CHL", "TUR", "SPM", "risk_level", "advice_fr"] if c in df.columns]
    print(df[cols].head())

    print("\n✅ PhosAlert water data ready!")
    print(f"   Use {OUTPUT_REAL} or {OUTPUT_SIMULATED} in your Flask API")
