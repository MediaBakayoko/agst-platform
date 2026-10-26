# AGST Platform

Plateforme de services géospatiaux, statistiques et GeoAI développée par AGST
(Média Marcel Bakayoko) — Côte d'Ivoire / Afrique de l'Ouest.

Monorepo réunissant des agents spécialisés en géomatique/data appelables
indépendamment, et une plateforme d'orchestration (en construction, en
dernier) qui les relie derrière une interface web unique avec gestion
multi-client.

## Agents

| Agent | Rôle | Statut |
|---|---|---|
| [`geodata_quality`](agents/geodata_quality/) | Contrôle qualité et validation topologique des données géospatiales | ✅ moteur testé |
| [`field2report`](agents/field2report/) | Pipeline collecte terrain → analyse → rapport | ✅ moteur testé |
| [`eudr_forest_monitoring`](agents/eudr_forest_monitoring/) | Contrôle parcelles + détection changement forestier (EUDR) | ✅ moteur testé |
| [`consulting_business`](agents/consulting_business/) | Préparation offres techniques/financières, suivi de missions | ✅ moteur testé |
| [`meal_project_performance`](agents/meal_project_performance/) | Cadre de résultats, indicateurs, tableaux de bord de suivi-évaluation | ✅ moteur testé |
| [`data_science_geoai`](agents/data_science_geoai/) | Statistiques, tests d'hypothèses, modèles ML/GeoAI reproductibles | ✅ moteur testé |
| [`academy_knowledge`](agents/academy_knowledge/) | Plans de cours, exercices, validation de code pour AGST Academy | ✅ moteur testé |
| [`survey_intelligence`](agents/survey_intelligence/) | Conception/validation XLSForm KoboToolbox + contrôle qualité des soumissions | ✅ moteur testé (sans intégration Kobo réelle, voir Prérequis) |
| [`platform`](platform/) (orchestrateur) | API FastAPI + isolation multi-client reliant les 8 agents | ✅ testé en conditions réelles (8/8 agents, upload→job→isolation→téléchargement) |

Règles communes à tous les agents : voir [`docs/governance.md`](docs/governance.md).

**Reste à faire avant un premier client réel** : connexion Supabase Auth
réelle (squelette JWT prêt, désactivé), hébergement cloud (dev local
pour l'instant), interface Lovable connectée à ce repo, facturation
(non activée, architecture prévue), intégration KoboToolbox réelle
(voir section Prérequis ci-dessous).

## Prérequis pour les intégrations externes (non encore faites)

### KoboToolbox (pour `survey_intelligence`)
1. Compte sur [kf.kobotoolbox.org](https://kf.kobotoolbox.org) (ou
   serveur Kobo privé/auto-héberge).
2. Token API v2 : *Account Settings → API Token*.
3. URL de base de l'API (`https://kf.kobotoolbox.org/api/v2/` ou
   équivalent pour un serveur privé).
4. Une fois obtenus : implémenter les méthodes de
   `agents/survey_intelligence/scripts/kobo_connector_stub.py`
   (actuellement toutes lèvent `NotImplementedError`) et stocker le
   token côté serveur uniquement (jamais dans un prompt/log), en
   suivant le pattern déjà en place dans
   `platform/app/core/auth.py` (variable d'environnement, jamais en dur).

### Supabase (pour la plateforme)
1. Créer un projet sur [supabase.com](https://supabase.com).
2. Récupérer `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`
   (ce dernier active automatiquement le mode JWT réel dans
   `platform/app/core/auth.py`, qui bascule hors du mode développement
   `X-Client-Id`).
3. Remplacer le stockage fichier (`platform/storage/`) par
   Postgres/Storage Supabase si une persistance partagée entre
   plusieurs machines est nécessaire (actuellement : système de
   fichiers local, suffisant pour un seul serveur).

### Déploiement backend (pour que Lovable/un frontend externe y accède)
1. Choisir un hébergeur (Railway, Render, VPS, ou l'offre Hostinger
   envisagée — vérifier qu'elle permet d'exécuter un process Python
   long-lived, pas seulement de l'hébergement web statique/PHP).
2. Déployer `platform/` avec `uvicorn app.main:app` derrière un process
   manager (ex: `gunicorn -k uvicorn.workers.UvicornWorker`) et HTTPS.
3. Restreindre `allow_origins` dans `platform/app/main.py` (actuellement
   `*`, marqué TODO) à l'origine réelle du frontend Lovable.
4. Donner l'URL publique obtenue à Lovable pour relier le frontend à ce
   backend.

## Principes communs à tous les agents

- **Jamais d'invention** : aucune donnée, résultat ou expérience n'est
  inventé ; tout output est traçable à une source réelle.
- **Jamais de correction/suppression silencieuse** : les fichiers sources
  ne sont jamais modifiés sans autorisation explicite ; les anomalies sont
  signalées, pas corrigées automatiquement.
- **Séparation des préoccupations** : chaque agent est autonome
  (utilisable en standalone, scriptable), la plateforme ne fait
  qu'orchestrer et exposer une interface.
- **Isolation multi-client** (plateforme) : aucune donnée ou résultat d'un
  client n'est jamais exposé à un autre.

## Stack prévue

- Agents : Python (GeoPandas, Shapely, Rasterio, GDAL/OGR, pandas,
  openpyxl, python-docx)
- Plateforme : Supabase (Postgres/PostGIS, auth, storage) + interface
  générée via Lovable (connectée à ce repo GitHub)
- Dév/test : en local pour l'instant ; hébergement cloud à prévoir avant
  tout accès client réel 24/7.
