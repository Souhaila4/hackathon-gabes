# PhosAlert — Backend API (Gabès)

API Flask pour l’intelligence **air**, **eau**, **cartographie**, **irrigation**, prévisions type **NAFAS**, conseils **agricoles** et **tableau de bord** personnalisé par **rôle JWT** (`citoyen`, `agriculteur`, `chercheur_scientifique`).

Documentation détaillée du travail réalisé : **[DOCUMENTATION_TRAVAIL.md](./DOCUMENTATION_TRAVAIL.md)**.

## Prérequis

- Python 3.10+
- MongoDB (utilisateurs)
- Package modèle (dossier voisin) :

```bash
pip install -e ../phosalert-model
```

## Installation

```bash
cd phosalert-backend
pip install -r requirements.txt
```

Configurer `.env` (JWT, `MONGODB_URI`, etc.). Voir la doc travail pour `REQUIRE_JWT`, Swagger, Hugging Face.

## Lancer le serveur

```bash
python app.py
```

Par défaut : port **5000** (variable `PORT`).

## Endpoints utiles (aperçu)

| Méthode | Route | Description |
|---------|--------|-------------|
| GET | `/health` | Santé du service |
| GET | `/apidocs/` | Swagger UI |
| GET | `/api/dashboard` | Dashboard (contenu selon rôle JWT ; sans token → citoyen) |
| GET | `/api/nafas/predict` | Prévisions NAFAS (données dynamiques Open-Meteo) |
| POST | `/api/agriculture/recommend` | Recommandation agriculture (JSON : crop, latitude, longitude) |
| GET | `/api/agriculture/crops?lat=…&lon=…` | Liste cultures / scores |
| GET | `/api/map/zones` | Zones carte |
| POST | `/api/predict/irrigation` | Risque irrigation |

Liste complète : Swagger ou `DOCUMENTATION_TRAVAIL.md`.

## Tests locaux (services)

```bash
python services/nafas_service.py
python services/agriculture_service.py
python services/dashboard_service.py
```

## Données eau (CSV)

Le script Copernicus et les CSV sous `data/` sont décrits ci-dessous. Le **dashboard** et les services peuvent lire `data/gabes_water_quality_simulated.csv` (moyennes) pour l’eau côtière.

---

## Script Copernicus — `scripts/fetch_gabes_water.py`

Téléchargement de proxies **couleur océan / qualité de l’eau** pour le **golfe de Gabès** (Copernicus Marine), avec repli simulé si l’API ou les identifiants manquent.

### Compte Copernicus Marine

1. [data.marine.copernicus.eu](https://data.marine.copernicus.eu/)
2. Variables possibles : `COPERNICUSMARINE_USERNAME`, `COPERNICUSMARINE_PASSWORD`

### Exécution du script

```bash
python scripts/fetch_gabes_water.py
```

- Succès : écrit `data/gabes_water_quality.csv` (`data_source` = `copernicus`).
- Repli : `data/gabes_water_quality_simulated.csv` (`data_source` = `simulated`).

### Colonnes typiques (CSV)

| Colonne | Sens |
|---------|------|
| `CHL` | Chlorophylle (souvent µg/L) |
| `TUR` | Turbidité (FNU ou équivalent produit) |
| `SPM` | Matière en suspension |
| `risk_score` / `risk_level` / `color` | Score heuristique et bande |

Détails : voir `DOCUMENTATION_TRAVAIL.md` et le script.

---

**Dépôt** : [hackathon-gabes](https://github.com/Souhaila4/hackathon-gabes) (branche `backend`).
