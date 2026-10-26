# Survey Intelligence Agent

Conception, validation XLSForm, deploiement et controle qualite
d'enquetes KoboToolbox -- a partir d'une description de projet en
langage naturel. Reutilise `geodata_quality` (controles geometrie/GPS)
et `field2report` (nettoyage/stats) comme briques internes plutot que
de les dupliquer.

## Principes (non negociables, herites de `docs/governance.md`)

- **Jamais de cible, valeur de reference ou donnee inventee.** Toute
  cible/baseline manquante reste vide dans la matrice, avec un
  signalement explicite -- jamais une valeur par defaut.
- **Jamais de deploiement d'un formulaire non approuve.**
  `kobo_connector.deploy_project()` refuse explicitement
  (`PermissionError`) sans `confirmed_by_human=True`.
- **Distinction stricte erreur bloquante / anomalie probable / valeur
  inhabituelle** dans le controle qualite -- une valeur inhabituelle
  n'est jamais declaree fausse automatiquement.
- **Fichiers sources jamais modifies** ; toute sortie va dans
  `output/` (local) ou `storage/<client_id>/<job_id>/` (via la
  plateforme).

## Pipeline (6 modules)

1. **`project_intake.py`** -- structure une description de projet en
   langage naturel en elements explicites (contexte, objectifs,
   beneficiaires, zone, activites/duree, indicateurs deja definis,
   besoins de collecte). Signale chaque element non detecte.
2. **`indicator_matrix_builder.py`** -- genere la matrice XLSX
   professionnelle (objectif, resultat associe, type d'indicateur,
   definition, formule, numerateur/denominateur, unite, valeur de
   reference, cible, source de verification, methode/frequence de
   collecte, desagregation, question necessaire, regle de qualite,
   limites methodologiques, statut de validation). Toute cible/
   baseline absente reste vide, signalee en feuille "A completer".
3. **`xlsform_builder.py`** -- genere un XLSForm (`survey`/`choices`/
   `settings`) a partir de la matrice approuvee. Supporte : types
   courants, listes de choix, `relevant` (logique conditionnelle),
   `constraint`/`constraint_message`, groupes `repeat` (begin/end
   repeat), `calculate` (champs derives), metadonnees enqueteur
   optionnelles (today/deviceid/username).
4. **`xlsform_validator.py`** -- valide le XLSForm *avant* toute
   approbation, en deux couches : (a) conversion reelle via `pyxform`
   (bibliotheque officielle ODK/Kobo) -- rejette si le formulaire ne
   serait pas accepte par un vrai serveur Kobo ; (b) controles maison
   complementaires (noms uniques, references `relevant` valides,
   groupes repeat bien fermes, listes de choix non vides). La
   validation XML finale d'ODK (necessite Java) n'est pas executee
   dans cet environnement -- signale explicitement, jamais masque.
5. **`survey_quality_checks.py`** -- controle qualite de soumissions
   (CSV, format export Kobo) : champs obligatoires, doublons, valeurs
   aberrantes (IQR), coherence inter-questions, dates (plausibilite),
   GPS (validite + zone du projet), duree d'entretien suspecte,
   soumission modifiee depuis la derniere analyse (idempotence par
   hash). Genere `registre_alertes.csv/.xlsx` avec gravite,
   justification, indicateur potentiellement affecte, action
   recommandee, statut de resolution (6 valeurs).
6. **`kobo_connector.py`** -- connecteur HTTP reel (API Kobo v2) :
   `check_connection`, `list_accessible_projects` (paginee),
   `create_project`, `import_xlsform`, `deploy_project` (refuse sans
   approbation humaine), `fetch_submissions` (paginee),
   `sync_submissions` (idempotent, detecte nouvelle/modifiee/
   inchangee via hash). Retry/backoff sur erreurs serveur, pas de
   retry sur erreur client. Token jamais journalise.

## Statut de chaque integration externe

| Integration | Statut | Preuve |
|---|---|---|
| Moteur matrice/XLSForm/qualite | **Teste reellement** | 23 tests pytest + pipeline CLI + API bout-en-bout |
| Validation XLSForm (pyxform) | **Teste reellement** (sans la passe Java/ODK Validate) | Conversion XLSForm->XForm reussie sur formulaire complexe |
| Connecteur Kobo (HTTP, retry, pagination, idempotence) | **Teste contre un serveur mock** (`responses`), jamais contre un vrai Kobo | 12 tests pytest `test_kobo_connector.py` |
| Deploiement Kobo reel | **En attente d'acces** -- aucun compte/token Kobo disponible | -- |
| Supabase (persistance partagee, RLS) | **Migrations preparees, non appliquees** | `platform/supabase/migrations/0001_survey_intelligence_schema.sql` |

## Usage (sans Kobo -- mode autonome)

```bash
# 1. Structurer la description de projet
python scripts/project_intake.py sample_data/description_projet_test.txt --output-dir output/

# 2. Construire la matrice d'indicateurs
python scripts/indicator_matrix_builder.py \
    --project output/project_xxx/project_structured.json \
    --indicators sample_data/indicateurs_matrice_complexe_test.csv \
    --output-dir output/

# 3. Generer le XLSForm (avec logique conditionnelle/repeats si presents dans la matrice)
python scripts/xlsform_builder.py \
    --matrix output/matrix_xxx/matrice_indicateurs.xlsx \
    --output-dir output/ --add-enumerator-metadata

# 4. Valider le XLSForm (pyxform + controles maison)
python scripts/xlsform_validator.py output/xlsform_xxx/formulaire.xlsx --output-dir output/

# 5. Controle qualite sur soumissions (synthetiques ou export Kobo reel)
python scripts/survey_quality_checks.py sample_data/soumissions_test_etendu.csv \
    --required-fields nom_repondant,commune \
    --numeric-fields age,surface_ha \
    --gps-fields latitude,longitude \
    --dedup-key-fields nom_repondant,commune \
    --date-fields date_visite --project-start-date 2026-01-01 --project-end-date 2026-12-31 \
    --zone-bbox "4.0,5.5,-7.0,-6.0" \
    --interview-start-field debut_entretien --interview-end-field fin_entretien \
    --submission-id-field id_soumission --previous-hashes-file output/hashes_sync.json \
    --output-dir output/
```

## Usage (avec Kobo -- une fois credentials disponibles)

```python
from kobo_connector import KoboConnector, KoboCredentials, SyncState

creds = KoboCredentials(base_url="https://kf.kobotoolbox.org/api/v2/", api_token="...")  # jamais en dur, variable d'env
connector = KoboConnector(credentials=creds)

connector.check_connection()  # leve KoboAPIError si echec
projects = connector.list_accessible_projects()

# Apres approbation humaine explicite du formulaire genere :
asset = connector.create_project("Suivi cacao San-Pedro")
connector.import_xlsform(asset["uid"], Path("output/xlsform_xxx/formulaire.xlsx"))
connector.deploy_project(asset["uid"], confirmed_by_human=True)  # refuse sans ce flag

# Synchronisation idempotente (repetable sans duplication) :
state = SyncState.load(Path("output/sync_state.json"))
result = connector.sync_submissions(asset["uid"], state)
state.save(Path("output/sync_state.json"))
```

## Dependances

```
pip install pandas openpyxl fastapi uvicorn pytest pyxform requests responses
```
(`responses` uniquement necessaire pour les tests du connecteur Kobo.)

## Limites assumees

- `xlsform_builder.py` genere un XLSForm **structurellement valide**,
  pas un formulaire pedagogiquement optimise -- relecture humaine
  recommandee avant deploiement reel.
- Les regles de coherence inter-questions sont limitees aux operateurs
  `<,<=,>,>=,==,!=` -- pas de logique conditionnelle arbitraire au-dela
  de `relevant`.
- `kobo_connector.py` n'a jamais ete execute contre un vrai serveur
  Kobo -- seule la logique HTTP (via mock) est verifiee reellement.
- Pas de notifications (email/SMS) -- le registre d'alertes est un
  fichier consultable, pas un systeme de push (voir
  `docs/notifications_prerequis.md` pour l'architecture prevue).
- Supabase : migrations SQL pretes, jamais appliquees a un vrai
  projet -- voir `platform/supabase/README.md`.
