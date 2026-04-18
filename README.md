# PhosAlert — Gabès water fetch (`scripts/fetch_gabes_water.py`)

This folder contains the PhosAlert Flask backend and a standalone script that downloads **ocean colour / water quality proxies** for the **Gulf of Gabès** from the **Copernicus Marine Service**, with a **simulated fallback** if the API or credentials are unavailable.

## 1. Copernicus Marine account

1. Open the Copernicus Marine Data Store: [https://data.marine.copernicus.eu/](https://data.marine.copernicus.eu/)
2. Register for a free account (username + password).
3. These credentials are used by the `copernicusmarine` Python toolbox (`copernicusmarine.login()`).

You can also set environment variables for automated runs (see the [toolbox documentation](https://toolbox-docs.marine.copernicus.eu/)):

- `COPERNICUSMARINE_USERNAME`
- `COPERNICUSMARINE_PASSWORD`

## 2. Install dependencies

The ML scoring package lives in the sibling folder **`phosalert-model`** (not inside this repo). Install it first (editable):

```bash
pip install -e ../phosalert-model
```

From this directory (`phosalert-backend`):

```bash
pip install -r requirements.txt
```

(`requirements.txt` inclut aussi les deps Copernicus via `requirements/gabes-water.txt`. Pour **uniquement** le script d’eau : `pip install -r requirements/gabes-water.txt`.)

## 3. Run the script

```bash
python scripts/fetch_gabes_water.py
```

- **Success (real data):** writes `data/gabes_water_quality.csv` with Copernicus-backed rows (`data_source` = `copernicus`).
- **Fallback:** on error, login failure, empty subset, or missing variables, writes `data/gabes_water_quality_simulated.csv` with research-based simulated values (`data_source` = `simulated`).

Optional reproducible noise for simulation:

```bash
set PHOSALERT_SEED=123
python scripts/fetch_gabes_water.py
```

## 4. Column meanings

Columns depend slightly on the NetCDF structure, but after processing you typically have:

| Column        | Meaning |
|---------------|---------|
| `CHL`         | Chlorophyll-like concentration (product-dependent units; often µg/L for level-3 BGC). |
| `TUR`         | Turbidity-related variable when exposed by the dataset (FNU or product-specific). |
| `SPM`         | Suspended particulate matter proxy (often mg/L or product-specific). |
| `risk_score`  | Heuristic 0–100 score from CHL/TUR/SPM thresholds (GCT/Gabès-oriented). |
| `risk_level`  | `CLEAN`, `SUSPECT`, or `CONTAMINATED`. |
| `color`       | UI hint: `green`, `orange`, `red`. |
| `advice_fr` / `advice_ar` | Short advisory text. |
| `risk_notes` | Concatenated threshold hits used for scoring (when present). |
| `data_source` | `copernicus`, `simulated`, or `simulated_emergency`. |

Simulated rows also include `date`, `zone_name`, `latitude`, `longitude` for named Gabès zones.

**Note:** Exact variable names in CMEMS products can differ; the script tries to map common synonyms into `CHL` / `TUR` / `SPM`. If the dataset ID or variables change, update `GABES_CONFIG` in `scripts/fetch_gabes_water.py`.

## 5. Using the CSV in the Flask API

1. Run `scripts/fetch_gabes_water.py` on a schedule or before deployment.
2. CSV générés sous `data/` (ex. `data/gabes_water_quality.csv`).
3. In `services/copernicus_service.py` (or a small loader module), read the CSV with `pandas.read_csv`, pick the row nearest to the user’s coordinates or the Gulf sampling point, and expose **turbidity / chlorophyll / risk** in `GET /api/water-quality` instead of pure simulation when the file is present.

Keep a fallback path so the API still returns JSON if the file is missing (same pattern as Open-Meteo / simulated data elsewhere in PhosAlert).

---

Repo : [hackathon-gabes](https://github.com/Souhaila4/hackathon-gabes) (branche `backend`).
