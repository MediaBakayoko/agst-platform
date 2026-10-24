# MEAL & Project Performance Agent

Appui à la conception, au suivi et à l'évaluation de projets de
développement : cadres logiques, fiches d'indicateurs, calcul des taux
d'avancement, tableaux de bord et rapports de suivi. Complète
`field2report` (traitement de données brutes) en se concentrant sur le
**cadre de résultats et la performance d'indicateurs**.

## Principes (non négociables)

- **Jamais d'invention** : aucun indicateur, cible, baseline, résultat
  ou preuve n'est inventé. Toute valeur calculée vient d'une donnée
  réellement fournie.
- **Distinction stricte activité / extrant (output) / résultat
  (outcome) / impact** — ne jamais les confondre dans un rapport.
- **Jamais de corrélation présentée comme causalité.** Si deux séries
  évoluent ensemble, le rapport le dit comme observation, jamais comme
  preuve d'effet.
- **Jamais de conclusion d'impact sans preuve appropriée** — l'agent
  peut calculer un taux d'atteinte de cible, jamais conclure "le projet
  a eu un impact" sans méthode d'évaluation adaptée (hors périmètre de
  cet outil).
- **Données manquantes/obsolètes/non représentatives toujours
  signalées**, jamais masquées pour présenter un indicateur comme
  complet.
- **Pas de certification de résultats officiels ni de soumission
  bailleur automatique** — validation humaine requise.

## Ce que l'agent fait

1. **Cadre de résultats** (`results_framework.py`) — à partir d'une
   liste d'indicateurs fournie (CSV), génère les fiches indicateur
   structurées (définition, formule, source, fréquence, responsable) et
   signale tout champ obligatoire manquant.
2. **Calcul de performance** (`indicator_calculator.py`) — à partir des
   valeurs réelles observées (CSV) et des cibles définies, calcule le
   taux d'atteinte par indicateur et par période, avec formule explicite
   journalisée pour chaque calcul.
3. **Tableau de bord** (`dashboard_builder.py`) — génère un Excel de
   suivi (indicateurs x périodes, taux d'atteinte, statut
   atteint/en_retard/non_atteint) + graphique de progression.
4. **Registre de recommandations** (`recommendation_tracker.py`) —
   CSV de suivi des actions correctives (constat, recommandation,
   responsable, échéance, statut).

## Usage

```bash
python scripts/results_framework.py sample_data/indicateurs_test.csv --output-dir output/
python scripts/indicator_calculator.py \
    --indicators sample_data/indicateurs_test.csv \
    --values sample_data/valeurs_observees_test.csv \
    --output-dir output/
python scripts/dashboard_builder.py \
    --calculated output/valeurs_observees_test_*/indicateurs_calcules.csv \
    --output-dir output/
python scripts/recommendation_tracker.py add \
    --registry sample_data/recommandations.csv \
    --constat "Taux de collecte < 70% sur l'indicateur X" \
    --recommandation "Renforcer la formation des enquêteurs" \
    --responsable "Chef de projet" --echeance 2026-12-01 --statut "ouverte"
```

## Limites assumées

- Le calcul de taux d'atteinte est une mesure de progression contre une
  cible déclarée — il ne constitue pas une évaluation d'impact (design
  expérimental/quasi-expérimental hors périmètre de cet outil).
- Toute valeur d'indicateur sans donnée source correspondante reste
  vide dans le tableau de bord, jamais interpolée.
