# Supabase -- Projet reel connecte (2026-10-27)

**STATUT ACTUEL : projet reel cree et lie
(`agst-survey-intelligence`, ref `qtqrqatrdrrlqdtgulio`, region
eu-central-1), migration 0001 appliquee avec succes cote distant
(`supabase migration list` confirme `local=0001, remote=0001`).**

Verifie reellement par connexion directe (psycopg2) :
- 8 tables presentes dans `public` (organisations, membres_organisation,
  projets, indicateurs, formulaires, soumissions, anomalies, synchronisations).
- RLS active sur les 8 tables (`rowsecurity = true`).
- 8 politiques RLS presentes (`pg_policies`).
- Ecriture + lecture + suppression reelles testees avec succes
  (ligne de test creee puis nettoyee, aucune donnee residuelle).
- 4 des 5 tests automatises de `tests/0001_rls_isolation_tests.sql`
  executes contre la base distante -- tous passes (tables presentes,
  RLS actif, pas de valeur par defaut inventee sur cible/valeur_reference,
  contrainte CHECK de gravite fonctionnelle).

**Reste a faire (necessite une decision utilisateur, pas un blocage
technique) :** le test 3 (isolation reelle entre 2 organisations via
RLS) necessite de creer 2 comptes de test via Supabase Auth -- non
fait car cela cree des utilisateurs reels dans le projet, meme si de
test. A faire sur confirmation.

**L'orchestrateur FastAPI n'est pas encore branche sur cette base** --
`job_runner.py`/`storage.py` utilisent toujours le stockage fichier
local. Brancher Supabase comme backend de persistance est un chantier
distinct (migration du code, pas seulement de la base), pas encore
commence.

## 1. Projet Supabase (deja fait)

Projet `agst-survey-intelligence` (ref `qtqrqatrdrrlqdtgulio`, region
eu-central-1) deja cree sous l'organisation Supabase de l'utilisateur,
via `npx supabase projects create`. Mot de passe de base de donnees
genere aleatoirement (32 caracteres), stocke uniquement dans
`platform/.supabase_db_password.local` (exclu de git, verifie via
`git check-ignore`) -- jamais commite, jamais affiche en clair dans ce
document ou dans un log.

## 2. Migrations (deja appliquees)

```bash
npx supabase link --project-ref qtqrqatrdrrlqdtgulio --password <mdp>
npx supabase db push --password <mdp> --yes
```
Confirme reellement via `npx supabase migration list` :
`local=0001, remote=0001`.

## 3. Credentials recuperees (deja fait pour ce projet)

Via `npx supabase projects api-keys --project-ref qtqrqatrdrrlqdtgulio --reveal` :
- `SUPABASE_URL` = `https://qtqrqatrdrrlqdtgulio.supabase.co`
- `SUPABASE_ANON_KEY` -- cle publique (OK cote frontend, mais pas un
  secret suffisant seule : l'autorisation reelle vient des policies RLS)
- `SUPABASE_SERVICE_ROLE_KEY` -- **secret serveur uniquement, jamais
  dans le frontend**, reserve aux operations d'administration
  explicites (ex: taches planifiees de synchronisation Kobo)

Note : `SUPABASE_JWT_SECRET` (HS256 legacy) n'est plus necessaire ---
voir section 4, l'authentification utilise desormais la verification
JWT moderne via JWKS (cles publiques ES256), pas de secret partage.

## 4. Backend branche (deja fait)

`platform/.env` (non commite, cree et verifie via `git check-ignore`) :
```
SUPABASE_URL=https://qtqrqatrdrrlqdtgulio.supabase.co
SUPABASE_ANON_KEY=<cle reelle>
SUPABASE_SERVICE_ROLE_KEY=<cle reelle>
```

`app/main.py` charge desormais `.env` via `python-dotenv` AVANT tout
import de `app.*` (necessaire car `auth.py` lit `os.getenv` a
l'import). `app/core/auth.py` reecrit pour verifier les JWT Supabase
via JWKS (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, ES256) --
plus de secret partage HS256, approche moderne. Dès que
`SUPABASE_URL` est present, le serveur bascule automatiquement hors
du mode developpement et exige un Bearer token Supabase reel.

**Verifie reellement** (2026-10-27) :
- Serveur lance avec `.env` present -> une requete avec seulement
  `X-Client-Id` (ancien mode dev) est bien rejetee
  (`{"detail":"Token Supabase manquant"}`) : la bascule fonctionne.
- 5 tests unitaires (`tests/test_auth_jwt.py`) avec une paire de cles
  ES256 de test (pas un vrai compte Supabase, pour eviter de creer
  des utilisateurs reels sans necessite) : token valide accepte,
  token expire rejete, token signe avec une MAUVAISE cle rejete
  (simulation d'attaque), mode dev toujours fonctionnel sans
  SUPABASE_URL, requete sans Authorization rejetee. Tous passes.
- **Non encore teste** : verification d'un vrai token emis par
  Supabase Auth pour un vrai utilisateur (necessite de creer un
  compte reel -- pas fait sans confirmation explicite
  supplementaire, cf. section 5).

Installer le client Python :
```bash
pip install supabase
```

## 5. Tests executes reellement contre la base distante

4 des 5 tests de `platform/supabase/tests/0001_rls_isolation_tests.sql`
ont ete executes directement via psycopg2 contre la base distante du
projet `agst-survey-intelligence` (2026-10-27), tous passes :
1. Toutes les tables attendues existent -- OK.
2. RLS est active sur les 8 tables sensibles -- OK.
3. Isolation reelle entre 2 organisations -- **NON execute** (bloc
   commente -- necessite de creer 2 utilisateurs de test via
   Supabase Auth au prealable, non fait sans confirmation explicite
   car cela cree des comptes reels dans le projet).
4. Aucune colonne `cible`/`valeur_reference` n'a de valeur par defaut
   non-NULL -- OK.
5. Les contraintes CHECK rejettent une valeur de statut invalide -- OK.

Une ecriture + lecture + suppression reelle (hors ces tests, directe)
a aussi ete executee avec succes pour confirmer la mecanique de base,
en plus des tests SQL.

Etapes executees reellement (2026-10-27, comptes de test jetables
crees via l'API admin, confirmes supprimes apres) :
1. Compte test cree, authentifie via le flux Auth normal (signup +
   login), JWT obtenu sans jamais etre expose en log/chat.
2. Route protegee de l'orchestrateur appelee avec ce JWT -- 200 OK.
3. Job cree, persistance confirmee dans la table `jobs` (rattachement
   exact au bon `client_id` = uuid Auth reel).
4. JWT absent / invalide / forge -- tous rejetes (401), teste
   reellement via de vrais appels HTTP.
5. Acces croise entre 2 clients de test -- 404, isolation confirmee
   au niveau applicatif (RLS teste separement via psycopg2 direct,
   voir section 5 ci-dessus pour le detail test par test).
6. DB Supabase injoignable (host invalide simule) -- echec absorbe
   proprement par `jobs_db.record_job_in_db`, aucune exception,
   serveur reste fonctionnel.
7. Comptes et donnees de test supprimes (identite verifiee par email
   avant suppression, cascade FK confirmee a 0 ligne residuelle).

Reste non teste : le scenario complet d'isolation RLS multi-organisation
du schema 0001 (2 utilisateurs dans 2 organisations distinctes,
lecture croisee de `projets`/`anomalies`) -- teste uniquement pour la
table `jobs` (isolation par `client_id` direct, plus simple). A faire
si un vrai second client utilise le modele organisationnel.

## 6. Supabase Storage -- implemente et teste reellement

**Bucket** `agst-files` (prive, `public=false`) cree via l'API Storage
(`POST /storage/v1/bucket`), limite de taille 25 Mo, types MIME
autorises limites a xlsx/csv/json/txt/pdf/docx.

**Table `fichiers`** (migration `0003_fichiers_storage.sql`) : une
ligne par fichier, avec `client_id`, `job_id` (reference libre, pas de
FK stricte), `projet_id` optionnel, `categorie`, cle de stockage non
previsible (uuid, jamais le nom original), checksum SHA-256, taille,
type MIME. RLS par `client_id = auth.uid()`.

**Defense en profondeur** : en plus de la table `fichiers` (controle
d'autorisation applicatif, fait par le backend a CHAQUE lecture/
ecriture/suppression), 4 policies RLS existent directement sur
`storage.objects` -- chaque objet doit etre stocke sous un prefixe
`<client_id>/...` et `auth.uid()` doit correspondre exactement. La cle
`service_role` (utilisee par le backend pour parler a Storage) n'est
JAMAIS consideree comme un remplacement de ce controle applicatif --
`get_file_metadata()` verifie toujours `client_id` avant toute
operation, meme si techniquement le backend pourrait tout lire avec
cette cle.

**Module** `platform/app/core/storage_backend.py` : `upload_file`,
`get_file_metadata`, `get_signed_download_url` (5 min par defaut),
`delete_file` (suppression LOGIQUE uniquement), `sync_job_output_files`
(upload best-effort des fichiers de sortie d'un job, jamais bloquant).

**Routes** `platform/app/routers/files.py` : `POST /files/upload`,
`GET /files/{id}/metadata`, `GET /files/{id}/download` (redirige vers
URL signee), `DELETE /files/{id}`.

**Teste reellement (2026-10-27)**, cycle complet via l'API HTTP avec
2 comptes de test jetables :
- upload -> metadata -> download (contenu verifie identique) -> OK
- acces croise entre 2 clients (metadata ET download) -> 404 les deux
- fichier inexistant -> 404 ; sans JWT -> 401
- suppression logique -> fichier non lisible apres, OK
- fichier > 25 Mo -> `FileTooLarge` ; extension interdite -> `UnsupportedFileType`
- 8 tests unitaires (`tests/test_storage_backend.py`) sur la logique
  sans reseau (validation, cle non previsible, config manquante)

**Risque reel identifie par le test** (pas suppose) : la suppression
d'un compte Supabase Auth declenche la cascade SQL sur `fichiers`
(ligne supprimee), mais ne supprime JAMAIS l'objet physique dans
Supabase Storage (systeme distinct, aucune cascade automatique).
Confirme par test reel : objet retrouve dans le bucket apres
suppression du compte et de sa ligne `fichiers`. **Tache de purge
periodique des objets Storage orphelins non implementee** -- a
prevoir avant toute suppression de compte en production.

**Bug reel trouve et corrige pendant le test** : `mimetypes.guess_type()`
renvoyait `application/vnd.ms-excel` pour un `.csv` sur cet
environnement Windows, rejete par le bucket (configure pour
`text/csv` strict) -- remplace par une table `EXTENSION_TO_MIME`
explicite, plus fiable que la detection systeme.

**Migration des fichiers locaux existants** : aucune migration
automatique des fichiers deja presents dans `platform/storage/` --
decision explicite de ne PAS migrer/supprimer les originaux locaux
(coherent avec la contrainte de la mission). Le mode local
(`app.core.storage`) reste pleinement fonctionnel et independant ;
`sync_job_output_files` ajoute une copie Supabase en best-effort sans
jamais remplacer ni supprimer les fichiers locaux.

**Branche sur les 8 agents (2026-10-27)** :
- 3 routes `survey_intelligence` (`indicator-matrix`, `xlsform-build`,
  `quality-check`) : synchronisation ciblee par categorie explicite
  (`matrice_indicateurs`/`xlsform`/`registre_alertes`), branchee
  directement dans `app/routers/survey_intelligence.py`.
- **5 agents restants etendus cette session**, via les 2 points
  d'entree partages (pas de duplication de code) :
  - `job_runner.run_agent_job()` -- `AGENT_STORAGE_CATEGORY` mappe
    `geodata_quality`, `field2report`, `eudr_forest_monitoring` ->
    categorie `rapport`.
  - `consulting_business._run_script()` -- `AGENT_PREFIX_STORAGE_CATEGORY`
    mappe les prefixes `consulting_business`, `academy_knowledge`,
    `data_science_geoai`, `meal` -> categorie `rapport`
    (`survey_intelligence.*` deliberement exclu de ce mapping pour
    eviter un double-upload avec ses 3 routes dediees ci-dessus).
- Extensions format : `ALLOWED_EXTENSIONS`/`EXTENSION_TO_MIME` elargis
  a `.gpkg` (GeoPackage, geodata_quality) et `.png` (cartes/graphiques,
  field2report/eudr_forest_monitoring/meal_project_performance).
- **Bug reel trouve et corrige** : le bucket `agst-files` avait ete
  cree avec une liste `allowed_mime_types` figee aux 6 types d'origine
  -- l'upload d'un `.gpkg` (`geodata_quality`) echouait reellement avec
  `415 invalid_mime_type` tant que le bucket lui-meme n'a pas ete mis a
  jour via `PUT /storage/v1/bucket/agst-files` (en plus du changement
  cote code) -- **les deux doivent toujours etre synchronises**.
- **Teste reellement (2026-10-27)**, comptes de test jetables crees
  et supprimes :
  - `academy_knowledge.course_outline_builder` (via `_run_script`) :
    job + fichier `plan_cours.json` confirmes en base.
  - `geodata_quality` (via `run_agent_job`, fichier `.gpkg` reel) :
    job + 2 fichiers (`.gpkg` + `.xlsx`) confirmes en base apres le
    fix du bucket (echec partiel observe UNE fois avant le fix, due a
    un flaky reseau TLS independant de ce bug -- "best-effort"
    documente, reproduit en relancant le meme appel avec succes).
  - `meal.results_framework` et `data_science_geoai.data_inspector`
    (via `_run_script`) : jobs + fichiers confirmes en base.
  - **Isolation croisee** : un 2e compte de test recoit 404 sur
    `/files/{id}/metadata` ET `/files/{id}/download` pour un fichier
    genere par `meal_project_performance` appartenant au 1er compte.
  - **Telechargement autorise** : le proprietaire reel telecharge
    avec succes (contenu verifie non vide, pas de trace d'erreur
    exposee).
  - 4 tests unitaires nouveaux (`tests/test_storage_agents_extension.py`)
    verifient la completude des mappings et le declenchement
    conditionnel de la synchronisation (jamais pour
    `survey_intelligence.*` via ce chemin, toujours pour les autres
    agents connus).
- **Risque reseau observe (pas un bug de code)** : plusieurs echecs
  TLS intermittents (`SSLEOFError`) sur les appels vers
  `*.supabase.co` pendant cette session de test, non reproductibles a
  volonte -- la nature best-effort de `sync_job_output_files` (jamais
  bloquant) a absorbe ces echecs sans impact sur les jobs eux-memes;
  signale comme risque d'environnement reseau, pas de code.
- **Frontend** : aucun changement necessaire cette etape (aucune des
  5 routes etendues n'etait deja consommee par une page frontend
  specifique a ces fichiers) -- `npm run lint`/`npm run build` relances
  par precaution, toujours 0 erreur.

## Ce qui est deja prepare cote code

- `platform/supabase/migrations/0001_survey_intelligence_schema.sql` --
  schema complet (organisations, membres, projets, indicateurs,
  formulaires, soumissions, anomalies, synchronisations) avec RLS par
  organisation. **Applique reellement** (voir sections 1-2).
- `platform/supabase/migrations/0002_jobs_tracking.sql` -- table
  `jobs` generique (tous les 8 agents, pas seulement survey_intelligence),
  RLS par `client_id = auth.uid()`. **Applique reellement** (meme
  procedure `supabase db push`, confirme via connexion directe :
  table presente, RLS active).
- `platform/app/core/jobs_db.py` (nouveau) -- ecriture best-effort de
  chaque job termine dans la table `jobs`, complementaire au fichier
  `job_meta.json` qui reste la source de verite. Echoue toujours
  proprement (jamais d'exception remontee) si `SUPABASE_DB_URL`
  absent, si la connexion echoue, ou si `client_id` n'est pas un UUID
  Supabase Auth valide (mode developpement) -- **teste reellement** :
  echec propre confirme avec un UUID syntaxiquement valide mais
  inexistant dans `auth.users` (violation de contrainte FK attendue,
  aucun crash). **Non teste** : ecriture reussie de bout en bout avec
  un vrai utilisateur Auth existant -- necessite de creer un compte
  de test, pas fait sans confirmation explicite (demandee, sans
  reponse dans le delai).
- `platform/app/core/job_runner.py` -- appelle `jobs_db.record_job_in_db`
  apres chaque job, dans un bloc `try/except` qui absorbe toute
  erreur -- ne peut jamais faire echouer un job agent.
- `platform/app/core/auth.py` -- **reecrit et branche reellement**.
  Verifie les JWT Supabase via JWKS (ES256, cles publiques, pas de
  secret partage). Bascule confirmee par test reel : avec `.env`
  present, une requete avec seulement `X-Client-Id` (ancien mode dev)
  est rejetee par le serveur reellement lance.
- `platform/app/main.py` -- charge `.env` via `python-dotenv` avant
  tout import de `app.*` (necessaire car plusieurs modules lisent
  `os.getenv` a l'import).
- `platform/.env` (non commite, cree avec les vraies cles du projet
  `agst-survey-intelligence`) : `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL` (connexion directe
  Postgres, utilisee par `jobs_db.py`).
