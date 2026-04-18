# Documentation du travail réalisé — PhosAlert (backend & modèle)

Ce document décrit **l’ensemble du travail réalisé** sur le projet PhosAlert pour l’intelligence air & eau autour de Gabès : de l’API Flask jusqu’au découplage du modèle et au dépôt GitHub. Il inclut les **évolutions récentes** (NAFAS dynamique, agriculture, tableau de bord par rôle JWT).

---

## 1. Contexte et objectif

- **PhosAlert** : API REST pour agréger données météo / qualité de l’air (Open-Meteo), eau, cartographie des zones à risque, prédiction d’irrigation, prévisions type NAFAS, conseils agricoles, chatbot conseil.
- **Objectifs techniques** : authentification sécurisée, base de données pour les utilisateurs, documentation API, architecture claire (MVVM), séparation stricte **backend** vs **modèle ML**, possibilité de déployer le modèle sur **Hugging Face** et de le consommer depuis le backend.

---

## 2. Authentification JWT + MongoDB

- **JWT** (Flask-JWT-Extended) : tokens **access** et **refresh**.
- **Stockage utilisateurs** : **MongoDB** (collection `users`).
- **Endpoints** :
  - `POST /api/auth/register` — email, mot de passe (≥ 8 caractères), rôle optionnel.
  - `POST /api/auth/login`
  - `POST /api/auth/refresh` — header `Authorization: Bearer <refresh_token>`
  - `GET /api/auth/me` — profil avec token d’accès.
- **Sécurité optionnelle** : variable `REQUIRE_JWT` — si `true`, toutes les routes `/api/*` sauf `/api/auth/*` exigent un JWT (routes Swagger exclues).
- **Cas particulier** : `GET /api/dashboard` utilise un **JWT optionnel** (`@jwt_required(optional=True)`). La route est **exclue** du `verify_jwt_in_request()` global lorsque `REQUIRE_JWT=true`, afin de permettre l’accès sans token (rôle par défaut **citoyen**) tout en acceptant un Bearer pour personnaliser le contenu.

Fichiers principaux : `routes/auth.py`, `viewmodels/auth_viewmodel.py`, `repositories/user_repository.py`, `core/extensions.py` (Mongo + JWT), `app.py` (`before_request`).

---

## 3. Rôles utilisateurs

Trois rôles métier (clés stables en base et dans le JWT, via `additional_claims`) :

| Clé | Libellé |
|-----|---------|
| `citoyen` | Citoyen (défaut si non précisé) |
| `agriculteur` | Agriculteur |
| `chercheur_scientifique` | Chercheur scientifique |

Alias acceptés à l’inscription (ex. `farmer` → `agriculteur`). Les comptes créés avant l’ajout du champ sont traités comme **citoyen**.

**Utilisation côté API** : le champ `role` dans le JWT pilote notamment le contenu de **`GET /api/dashboard`** (voir section 8).

Fichier : `models/user_roles.py`.

---

## 4. Architecture MVVM (adaptée à une API REST)

| Couche | Dossier / rôle |
|--------|----------------|
| **View** | `routes/` (blueprints Flask), handlers dans `app.py` pour `/health`, `/api/map/zones` uniquement. **`/api/dashboard`** est défini dans `routes/dashboard.py`. |
| **ViewModel** | `viewmodels/` — logique de réponse JSON (carte, auth, délégation dashboard). |
| **Model** | `models/` — constantes métier (zones Gabès, rôles). |
| **Repository** | `repositories/` — accès MongoDB (`UserRepository`). |
| **Services** | `services/` — intégrations externes et orchestration (Open-Meteo, NAFAS dynamique, agriculture, dashboard agrégé, Copernicus). |
| **Infrastructure** | `core/extensions.py` — initialisation MongoDB et JWT. |
| **Présentation API** | `presentation/swagger.py` — configuration Flasgger / OpenAPI (tags : Health, Auth, Carte, Dashboard, Air, Eau, Prédiction, Chat, **NAFAS**, **Agriculture**). |

---

## 5. Documentation Swagger

- **Flasgger** : interface **Swagger UI** sur `/apidocs/`, spec JSON `/apispec_1.json`.
- **Désactivation** : `SWAGGER_ENABLED=false`.
- Fichier : `presentation/swagger.py`.

---

## 6. Backend / modèle ML (`phosalert_model` vendorisé)

- Le **package Python `phosalert_model`** est présent **dans ce dépôt** sous **`phosalert_model/`** (à la racine du backend), sans chemin externe ni `pip install -e`.
- `app.py` préfixe `sys.path` avec la racine du projet pour que l’import fonctionne sur Railway / Gunicorn même si le répertoire de travail diffère.
- Le backend utilise `import phosalert_model` pour scores, géodésie, simulations, etc.
- **Façade unique** : `phosalert_model/api.py`.
- **Heuristiques** : `phosalert_model/heuristics.py` (baseline sans fichier entraîné).
- **Modèles entraînés** :
  - **Joblib local** : `PHOSALERT_TRAINED_IRRIGATION_MODEL_PATH`.
  - **Hugging Face** : `PHOSALERT_HF_INFERENCE_URL` + `PHOSALERT_HF_TOKEN` / `HF_TOKEN` — appel HTTP prioritaire pour le score irrigation (`phosalert_model/trained/hf_remote.py`).
- **Ordre d’inférence irrigation** : Hugging Face → joblib → heuristique.
- **Serveur FastAPI optionnel** pour un Space HF : `phosalert_model/serve.py` (extras `[serve]`).

---

## 7. Organisation des dossiers (backend)

| Élément | Emplacement |
|---------|-------------|
| Point d’entrée Flask | `app.py` (racine) |
| Dépendances | `requirements.txt` (optionnel : `requirements/gabes-water.txt` pour le script Copernicus seul) |
| Infrastructure | `core/` |
| Swagger | `presentation/` |
| Script Copernicus (hors API) | `scripts/fetch_gabes_water.py` |
| CSV générés / exemples | `data/` (ex. `gabes_water_quality_simulated.csv` utilisé par le dashboard) |
| Fichiers sensibles | `.env` (ignoré par Git — voir `.gitignore`) |

---

## 8. Tableau de bord personnalisé par rôle (`GET /api/dashboard`)

- **Fichiers** : `services/dashboard_service.py`, `routes/dashboard.py`, `viewmodels/dashboard_viewmodel.py`.
- **Comportement** :
  - Sans JWT ou rôle non reconnu : contenu **citoyen** (zones sûres, alertes santé, qualité air/vent/eau).
  - `agriculteur` : irrigation, précipitations 7 jours (Open-Meteo `daily`), recommandations via `services/agriculture_service.py`, cultures alternatives, facteurs de décision.
  - `chercheur_scientifique` : séries historiques 24 h, comparaisons seuils indicatifs, données NAFAS brutes, statistiques, zones complètes.
- **Données** : air et vent **Open-Meteo** (URLs documentées dans le code), eau depuis **CSV** `data/gabes_water_quality_simulated.csv` (moyennes) ou repli **simulation phosalert** si fichier absent, **NAFAS** via `fetch_dynamic_nafas()`.
- **Query (agriculteur)** : `?crop=olive&lat=33.88&lon=10.05`.
- La réponse inclut `jwt_role` (rôle effectivement appliqué).

---

## 9. Module NAFAS (prévisions pollution 48 h)

- **Service** : `services/nafas_service.py` — données **100 % dynamiques** via Open-Meteo (qualité de l’air + conversion µg/m³ → mol/m², vent pour zones de dépôt).
- **Repli** : si l’API air est indisponible, réponse structurée `ok: false` / `data_source: unavailable` (pas de valeurs inventées).
- **Variable AOD** : `aerosol_optical_depth` (nom officiel Open-Meteo).
- **Routes** (`routes/nafas.py`, préfixe `/api`) :
  - `GET /api/nafas/predict`
  - `GET /api/nafas/alerts`
  - `GET /api/nafas/deposition-map`
- **Variable d’environnement optionnelle** : `NAFAS_API_URL` (si un serveur LSTM externe est ajouté plus tard ; le flux actuel est Open-Meteo).

---

## 10. Module Agriculture

- **Service** : `services/agriculture_service.py` — `recommend_agriculture`, `crops_for_location` (Open-Meteo + `phosalert_model`).
- **Routes** (`routes/agriculture.py`) :
  - `POST /api/agriculture/recommend` — JSON : `crop`, `latitude`, `longitude`
  - `GET /api/agriculture/crops` — query : `lat`, `lon`
- **Cultures** : `olive`, `dates`, `vegetables`, `cereals`.

---

## 11. Intégrations métier (synthèse)

| Domaine | Fichier / module |
|---------|------------------|
| Open-Meteo (air, vent, historique, précipitations) | `services/openmeteo_service.py`, `services/nafas_service.py`, `services/dashboard_service.py`, `services/agriculture_service.py` |
| NAFAS / dashboard | `services/nafas_service.py`, `services/dashboard_service.py` |
| Agriculture | `services/agriculture_service.py` |
| Copernicus | `services/copernicus_service.py` (stub / extension possible) |
| Eau (API) | `routes/water_quality.py` (chaîne Copernicus → marine → simulation) |
| Chatbot | `routes/chatbot.py` — Anthropic (`CLAUDE_API_KEY`) avec repli heuristique |

---

## 12. Déploiement du code sur GitHub

- Dépôt : **[hackathon-gabes](https://github.com/Souhaila4/hackathon-gabes)**.
- Branche poussée pour le backend : **`backend`**.
- URL de la branche : [https://github.com/Souhaila4/hackathon-gabes/tree/backend](https://github.com/Souhaila4/hackathon-gabes/tree/backend).
- Le code du modèle / heuristiques est versionné dans **`phosalert_model/`** sur ce dépôt.

---

## 13. Installation et exécution

1. Cloner le repo (ex. branche `main` ou `backend`).
2. Depuis `phosalert-backend` :
   ```bash
   pip install -r requirements.txt
   ```
3. Copier `.env.example` vers `.env` si présent, et renseigner secrets (JWT, MongoDB, clés API, URLs HF si besoin).
4. Lancer :
   ```bash
   python app.py
   ```

### Tests rapides (ligne de commande)

```bash
python services/nafas_service.py
python services/agriculture_service.py
python services/dashboard_service.py
```

---

## 14. Fichiers utilitaires peu utilisés par l’API

- `utils/response_formatter.py` : helpers JSON non branchés aux routes actuelles.
- `scripts/fetch_gabes_water.py` : **outil CLI** Copernicus — pas importé par `app.py`.

---

## 15. Liste des routes API principales (référence)

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/health` | Santé du service |
| GET | `/api/map/zones` | Marqueurs carte |
| GET | `/api/dashboard` | Tableau de bord (rôle JWT ; optionnel) |
| GET | `/api/nafas/predict`, `/alerts`, `/deposition-map` | NAFAS dynamique |
| POST | `/api/agriculture/recommend` | Recommandation culture |
| GET | `/api/agriculture/crops` | Cultures / adéquation |
| … | `/api/air-quality`, `/api/wind`, `/api/water-quality`, … | Voir Swagger `/apidocs/` |
| … | `/api/auth/*`, `/api/predict/irrigation`, `/api/chat` | Auth, irrigation, chat |

---

## 16. Synthèse « de A à Z » (historique + évolutions)

1. API Flask (air, eau, carte, prédiction, chatbot).  
2. Auth **JWT** + **MongoDB**, **trois rôles**.  
3. Architecture **MVVM**, **Swagger** (Flasgger).  
4. Package **`phosalert_model/`** (vendorisé, joblib, Hugging Face, heuristiques).  
5. Réorganisation **`core/`**, **`presentation/`**, **`scripts/`**, **`data/`**.  
6. Push GitHub, branche **`backend`**.  
7. **Évolutions documentées ici** :  
   - **NAFAS** : routes dédiées, service dynamique Open-Meteo.  
   - **Agriculture** : service + routes recommend / crops.  
   - **Dashboard** : `services/dashboard_service.py`, blueprint `routes/dashboard.py`, contenu selon **rôle JWT**, exclusion JWT obligatoire pour cette route dans `app.py`.  
   - Tags Swagger **NAFAS** et **Agriculture**.

---

*Document mis à jour pour le projet PhosAlert — hackathon Gabès.*
