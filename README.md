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
| [`platform`](platform/) (orchestrateur) | API FastAPI + isolation multi-client reliant les 7 agents | ✅ testé en conditions réelles (7/7 agents, upload→job→isolation→téléchargement) |

Règles communes à tous les agents : voir [`docs/governance.md`](docs/governance.md).

**Reste à faire avant un premier client réel** : connexion Supabase Auth
réelle (squelette JWT prêt, désactivé), hébergement cloud (dev local
pour l'instant), interface Lovable connectée à ce repo, facturation
(non activée, architecture prévue).

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
