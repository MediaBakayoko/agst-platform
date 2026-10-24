# Academy & Knowledge Agent

Conception de contenus pédagogiques pratiques (QGIS, télédétection,
GEE, Python, PostGIS, GeoAI, statistiques agricoles, MEAL) pour AGST
Academy, et organisation de la connaissance technique interne
(scripts réutilisables, notes, retours d'expérience projet).

## Principes (non négociables)

- **Jamais de certification, accréditation ou partenariat
  institutionnel inventé.** Le contenu produit est un support de
  formation, jamais présenté comme une certification officielle sans
  base réelle.
- **Code d'exemple testé** : tout extrait de code d'un module est
  exécuté réellement avant publication ; `code_validator.py` vérifie
  qu'il tourne sans erreur.
- **Sources citées** pour toute information technique factuelle ou
  évolutive (versions logicielles, API...).
- **Licences respectées** : jeux de données et logiciels utilisés dans
  les exercices doivent être libres de droit ou explicitement autorisés
  — signalé si l'origine n'est pas claire.
- **Pas de publication de données d'apprenants** (présence, notes,
  retours) sans autorisation explicite.
- **Relecture par un instructeur qualifié requise** avant diffusion
  officielle d'un module important — cet agent produit des brouillons.

## Modules

1. **`course_outline_builder.py`** — à partir d'objectifs
   d'apprentissage et du niveau des apprenants (débutant/intermédiaire/
   avancé), génère un plan de cours structuré (modules, durée indicative,
   prérequis) — signale les objectifs trop vagues pour être traduits en
   plan concret plutôt que d'improviser un contenu.
2. **`exercise_builder.py`** — génère un exercice pratique à partir
   d'un modèle (titre, contexte, données nécessaires, étapes, critère de
   réussite) ; vérifie que les données mentionnées existent réellement
   dans `sample_data/` avant de les référencer.
3. **`code_validator.py`** — exécute un extrait de code Python fourni
   dans un environnement isolé et rapporte succès/échec réel — jamais
   de validation déclarée sans exécution effective.
4. **`learning_tracker.py`** — registre CSV de suivi des apprenants
   (présence, évaluation, retour) — anonymisable, jamais publié sans
   autorisation.

## Usage

```bash
python scripts/course_outline_builder.py \
    --titre "Introduction a Google Earth Engine" \
    --niveau debutant \
    --objectifs "Comprendre les collections d'images,Calculer un NDVI,Exporter un resultat" \
    --duree-heures 12 \
    --output-dir output/

python scripts/exercise_builder.py \
    --titre "Calcul de NDVI sur Sentinel-2" \
    --contexte "Zone agricole pres de Bouake" \
    --donnees-requises sample_data/exemple_zone.geojson \
    --output-dir output/

python scripts/code_validator.py sample_data/exemple_code.py --output-dir output/

python scripts/learning_tracker.py add --registry sample_data/suivi_apprenants.csv \
    --apprenant "ID_001" --module "Introduction GEE" --statut "complete" --note 85
```

## Limites assumées

- `course_outline_builder.py` structure un plan, il ne rédige pas le
  contenu pédagogique complet de chaque module — cela reste un travail
  de rédaction humaine assistée, pas une génération intégrale
  automatique.
- La validation de code (`code_validator.py`) vérifie que le code
  s'exécute sans erreur, pas qu'il est pédagogiquement optimal.
