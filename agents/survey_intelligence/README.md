# Survey Intelligence Agent

Conception, validation XLSForm, et contrôle qualité d'enquêtes
KoboToolbox — à partir d'une description de projet en langage naturel.
**Phase actuelle : construction sans intégration KoboToolbox réelle**
(voir section Limites). Réutilise `geodata_quality` (contrôles
géométrie/GPS) et `field2report` (nettoyage/stats) comme briques
internes plutôt que de les dupliquer.

## Principes (non négociables, hérités de `docs/governance.md`)

- **Jamais de cible, valeur de référence ou donnée inventée.** Toute
  cible/baseline manquante dans la description utilisateur reste vide
  dans la matrice, avec un signalement explicite — jamais une valeur
  par défaut.
- **Jamais de déploiement d'un formulaire non approuvé.** Le pipeline
  s'arrête après génération + validation ; le déploiement Kobo réel
  est une étape séparée, non implémentée dans cette phase.
- **Distinction stricte erreur bloquante / anomalie probable / valeur
  inhabituelle** dans le contrôle qualité — une valeur inhabituelle
  n'est jamais déclarée fausse automatiquement.
- **Fichiers sources jamais modifiés** ; toute sortie va dans
  `output/` (local) ou `storage/<client_id>/<job_id>/` (via la
  plateforme).

## Pipeline (5 modules)

1. **`project_intake.py`** — structure une description de projet en
   langage naturel (texte libre) en éléments explicites (contexte,
   objectifs, bénéficiaires, zone, activités/durée, indicateurs déjà
   définis, besoins de collecte). Signale chaque élément non détecté —
   ne complète jamais par une supposition.
2. **`indicator_matrix_builder.py`** — à partir du projet structuré +
   d'indicateurs fournis par l'utilisateur (CSV), génère la matrice
   XLSX (définition, formule, unité, source de vérification,
   fréquence, désagrégation, cible si fournie, questions nécessaires,
   règles de qualité). Toute cible absente reste vide, signalée.
3. **`xlsform_builder.py`** — génère un XLSForm (`survey`/`choices`/
   `settings`, 3 feuilles) à partir de la matrice approuvée.
4. **`xlsform_validator.py`** — valide la cohérence du XLSForm généré
   *avant* toute approbation : types de questions valides, références
   de `choice_filter`/`relevant`/`constraint` existantes, pas de nom de
   question dupliqué, listes de choix non vides.
5. **`survey_quality_checks.py`** — contrôle qualité de soumissions
   (CSV, format export Kobo) : champs obligatoires, doublons, valeurs
   aberrantes (IQR), cohérence inter-questions (règles fournies),
   dates, GPS (réutilise la logique de `field2report.cleaning` et
   `geodata_quality`). Génère `registre_alertes.csv` avec gravité,
   justification, action recommandée.

## Ce qui N'EST PAS fait dans cette phase (volontairement)

- **Pas de connecteur KoboToolbox réel** (pas de token, pas d'appel API
  v2/KPI) — nécessite un compte Kobo (voir README racine, section
  Prérequis).
- **Pas de Supabase** — la persistance partagée entre jobs reste le
  système de fichiers (`storage/`), comme les 7 autres agents.
- **Pas de notifications** (email/SMS) — le registre d'alertes est un
  fichier consultable, pas un système de push.

Ces interfaces sont posées en points d'extension explicites (voir
`kobo_connector_stub.py` et `README.md` section "Point d'extension
Kobo") pour être branchées plus tard sans réécrire le moteur.

## Usage

```bash
# 1. Structurer la description de projet
python scripts/project_intake.py sample_data/description_projet_test.txt --output-dir output/

# 2. Construire la matrice d'indicateurs
python scripts/indicator_matrix_builder.py \
    --project output/project_xxx/project_structured.json \
    --indicators sample_data/indicateurs_matrice_test.csv \
    --output-dir output/

# 3. Générer le XLSForm
python scripts/xlsform_builder.py \
    --matrix output/matrix_xxx/matrice_indicateurs.xlsx \
    --output-dir output/

# 4. Valider le XLSForm
python scripts/xlsform_validator.py output/xlsform_xxx/formulaire.xlsx --output-dir output/

# 5. Contrôle qualité sur soumissions synthétiques
python scripts/survey_quality_checks.py sample_data/soumissions_test.csv \
    --required-fields nom_repondant,commune \
    --gps-fields latitude,longitude \
    --output-dir output/
```

## Limites assumées

- `xlsform_builder.py` génère un XLSForm **structurellement valide**,
  pas un formulaire pédagogiquement optimisé — relecture humaine
  recommandée avant déploiement réel.
- Le contrôle de "cohérence inter-questions" dans
  `survey_quality_checks.py` applique des règles explicites fournies
  par l'utilisateur (ex: `age_minimum < age_maximum`) — il ne devine
  jamais de règle métier non spécifiée.
- Sans intégration Kobo réelle, le workflow s'arrête à la génération
  d'un XLSForm téléchargeable — la création/déploiement de projet Kobo
  reste une étape manuelle (upload sur kf.kobotoolbox.org) ou une
  phase ultérieure (voir Prérequis Kobo dans le README racine).
