# Field2Report Agent

Pipeline reproductible : **collecte → contrôle qualité → nettoyage →
analyse statistique → cartographie → rapport**, avec traçabilité
complète à chaque étape.

Conçu pour les enquêtes agricoles, études socioéconomiques et missions
de suivi-évaluation en Côte d'Ivoire / Afrique (données KoboToolbox, ODK,
GPS, Excel, CSV, fichiers géospatiaux).

## Principes (non négociables)

- **Jamais de données inventées.** Toute statistique, carte ou phrase du
  rapport provient d'un calcul ou d'une donnée réellement présente dans
  le jeu de données. Si une information manque, le rapport le dit
  explicitement — il ne la complète jamais par extrapolation silencieuse.
- **Données brutes toujours conservées**, séparées des données nettoyées
  (`data_raw/` vs sortie nettoyée dans `output/.../cleaned.csv`).
- **Règles de nettoyage documentées** dans le journal (`journal.log`) et
  dans le rapport lui-même (section "Méthodologie").
- **Distinction stricte observé / calculé / imputé** : chaque variable du
  dictionnaire des variables indique sa nature.
- **Biais signalés** : déséquilibres manifestes (ex: sex-ratio de
  l'échantillon, sur-représentation géographique) sont relevés dans le
  rapport, jamais corrigés silencieusement par pondération implicite.

## Étapes du pipeline

1. **Ingestion** — lecture CSV/Excel (export KoboToolbox/ODK) ou GeoJSON/
   GeoPackage avec coordonnées GPS.
2. **Contrôle qualité** — réutilise les contrôles du module
   `geodata_quality` pour la partie géospatiale (coordonnées valides,
   doublons) + contrôles spécifiques enquête (valeurs hors plage,
   réponses manquantes sur champs obligatoires, doublons de répondants).
3. **Nettoyage** — actions limitées et documentées (normalisation de
   casse/espaces, typage des colonnes) ; **aucune valeur n'est modifiée
   sans trace dans le journal.**
4. **Analyse statistique** — statistiques descriptives par variable et
   par groupe (ex: par commune/district), générées automatiquement à
   partir du dictionnaire de variables fourni.
5. **Cartographie** — carte(s) thématique(s) Matplotlib (points
   d'enquête, choroplèthe par zone si polygones fournis).
6. **Rapport** — document Word généré automatiquement (texte, tableaux,
   cartes intégrées), avec section méthodologie et limites.

## Usage

```bash
python scripts/run_pipeline.py sample_data/enquete_test.csv \
    --output-dir output/ \
    --lat-field latitude --lon-field longitude \
    --group-field commune \
    --numeric-fields age,surface_ha,rendement_kg_ha \
    --required-fields nom_repondant,commune \
    --dictionary sample_data/dictionnaire_variables.csv
```

Sorties dans `output/<nom>_<timestamp>/` :
- `cleaned.csv` — données nettoyées (brutes jamais modifiées)
- `journal.log` — chaque action de nettoyage/contrôle, horodatée
- `dictionnaire_variables.csv` — recopié/enrichi (nature de chaque champ)
- `tableaux_statistiques.xlsx` — stats descriptives par variable et par groupe
- `carte_enquete.png` — carte des points de collecte (+ choroplèthe si zones fournies)
- `rapport_final.docx` — rapport complet
