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
| [`geodata_quality`](agents/geodata_quality/) | Contrôle qualité et validation topologique des données géospatiales | 🔧 en construction |
| `field2report` | Pipeline collecte terrain → analyse → rapport | ⏳ à venir |
| `eudr_forest_monitoring` | Contrôle parcelles + détection changement forestier (EUDR) | ⏳ à venir |
| `consulting_business` | Préparation offres techniques/financières, suivi de missions | ⏳ à venir |
| `platform` (orchestrateur) | API + auth multi-client + UI (Lovable/Supabase) reliant les 4 agents | ⏳ en dernier |

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
