# GeoData Quality Agent

Agent de contrôle qualité, validation topologique et fiabilisation des
bases de données géospatiales (GeoPackage, Shapefile, GeoJSON, CSV
géolocalisé). Produit un rapport Excel structuré et, si demandé, une
couche cartographique des anomalies.

## Principes (non négociables)

- **Ne modifie jamais le fichier source.** Toute sortie va dans
  `output/`, jamais à côté/à la place du fichier d'entrée.
- **Ne corrige ni ne supprime jamais automatiquement une géométrie ou une
  entité.** Le rôle de l'agent est de *signaler*, pas de réparer.
- **Distingue les erreurs certaines des anomalies à examiner** (voir
  colonne `severite` du rapport : `erreur` vs `a_verifier`).
- **Vérifie le CRS avant tout calcul de surface/distance** ; si le CRS
  est géographique (degrés), reprojette dans un CRS adapté (UTM local)
  uniquement pour le calcul, jamais pour la sortie.

## Contrôles effectués

| Contrôle | Description | Sévérité |
|---|---|---|
| Géométrie invalide | `geom.is_valid` échoue (auto-intersection, etc.) | erreur |
| Géométrie vide/nulle | géométrie manquante ou vide | erreur |
| Doublons géométriques | géométries identiques (ou quasi, tolérance configurable) | a_verifier |
| Doublons attributaires | lignes identiques sur un sous-ensemble de champs clés | a_verifier |
| Chevauchements | polygones qui se superposent (hors attendu) | a_verifier |
| Champs manquants | valeurs nulles/vides sur des champs jugés obligatoires | erreur |
| Incohérence de type | champ numérique attendu contenant du texte, etc. | erreur |
| Anomalie de superficie | aire hors bornes plausibles (configurable), ou surface déclarée vs SIG trop divergente | a_verifier |
| CRS manquant/suspect | couche sans CRS défini, ou CRS incohérent avec la zone | erreur |

## Usage

```bash
python scripts/run_quality_check.py <input_file> \
    --output-dir output/ \
    --required-fields nom,surface_ha \
    --area-field surface_ha \
    --area-tolerance-pct 20 \
    --dup-tolerance-m 0
```

Sorties produites dans `output/<nom_fichier>_<timestamp>/` :
- `rapport_qualite.xlsx` — rapport multi-feuilles (résumé, anomalies détaillées par type, paramètres utilisés)
- `anomalies.gpkg` — couche géographique des entités en anomalie (si au moins une géométrie concernée)
- `journal.log` — journal du traitement (horodaté, paramètres, étapes)

## Limites assumées

- Les contrôles de "chevauchement attendu vs anormal" nécessitent un
  jugement métier — l'agent signale tout chevauchement, c'est à
  l'utilisateur de juger s'il est normal (ex: parcelles mitoyennes) ou
  anormal (doublon de saisie).
- La détection de doublons attributaires dépend des champs clés fournis ;
  sans spécification, seule la géométrie est utilisée.
