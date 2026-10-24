# Data Science & GeoAI Agent

Analyses statistiques, modèles de machine learning et prototypes
géospatiaux reproductibles, pour des problématiques agricoles,
environnementales, climatiques, socioéconomiques et territoriales.
Complète `geodata_quality`, `field2report` et `eudr_forest_monitoring`
en se concentrant sur le **raisonnement statistique et la modélisation
avancée**, pas sur le nettoyage de base ou la cartographie de routine.

## Principes (non négociables)

- **Jamais de résultat statistique, précision de modèle ou conclusion
  fabriquée.** Toute métrique vient d'un calcul réel sur les données
  fournies.
- **Hypothèses vérifiées avant tout test/modèle** (normalité, taille
  d'échantillon, indépendance...) — signalées dans le rapport, jamais
  supposées silencieusement.
- **Pas de fuite de données (data leakage)** : split train/test
  effectué avant tout calcul de métrique, jamais de fit sur
  l'ensemble puis évaluation sur le même ensemble sans le dire.
- **Jamais de certitude prédictive** : intervalles de confiance /
  erreurs de validation toujours rapportés à côté de toute prédiction.
- **Déséquilibre de classes et représentativité vérifiés** et
  signalés si pertinent — jamais masqués.
- **Distinction stricte exploratoire / validé** : une corrélation
  observée en exploration n'est jamais présentée comme une conclusion
  validée.
- **Jamais de déploiement en production sans test et accord humain.**
  Cet agent produit des prototypes et notebooks, pas des pipelines de
  production.

## Modules

1. **`data_inspector.py`** — audit d'un jeu de données : structure,
   complétude, types, valeurs aberrantes (IQR), corrélations —
   dictionnaire de données en sortie.
2. **`statistical_tests.py`** — tests statistiques usuels
   (normalité Shapiro-Wilk, corrélation Pearson/Spearman, t-test,
   ANOVA) avec vérification des hypothèses préalables et
   avertissement explicite si les conditions ne sont pas remplies.
3. **`model_trainer.py`** — entraînement et validation de modèles de
   régression/classification (scikit-learn), avec split train/test,
   métriques de validation, comparaison à une baseline naïve (jamais
   de modèle présenté sans comparaison à un point de référence simple).
4. **`report_builder.py`** — rapport Word technique reprenant
   hypothèses, métriques, limites et incertitudes.

## Usage

```bash
# 1. Audit du jeu de donnees
python scripts/data_inspector.py sample_data/dataset_test.csv --output-dir output/

# 2. Tests statistiques
python scripts/statistical_tests.py sample_data/dataset_test.csv \
    --test correlation --field-x rendement_kg_ha --field-y surface_ha \
    --output-dir output/

# 3. Modele (exemple : regression)
python scripts/model_trainer.py sample_data/dataset_test.csv \
    --target rendement_kg_ha --features surface_ha,age_plantation \
    --model-type regression --output-dir output/
```

## Limites assumées

- Les modèles produits sont des **prototypes évalués**, pas des
  systèmes de production — un déploiement opérationnel nécessite des
  tests supplémentaires et une validation humaine explicite.
- L'intégration GeoAI (rasters satellite, GEE) suppose des données déjà
  extraites en tabulaire ou raster local — ce module ne télécharge pas
  lui-même d'imagerie.
