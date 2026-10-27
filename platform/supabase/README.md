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

Etapes manuelles restantes (necessitent une decision utilisateur pour
creer des comptes Auth de test) :
1. Creer un utilisateur de test via Supabase Auth.
2. L'ajouter a une `organisation` de test via `membres_organisation`.
3. Verifier via l'API REST Supabase (ou le client Python) qu'il peut
   lire ses propres projets et ANOMALIES mais recoit une liste vide
   (pas une erreur serveur masquant les donnees -- RLS doit filtrer,
   pas planter) pour l'organisation d'un autre utilisateur.
4. Creer un 2e utilisateur dans une 2e organisation, repeter le test
   en sens inverse.
5. Redemarrer le service et confirmer que les donnees persistent
   (test de redemarrage demande par la mission).

Tant que ces etapes n'ont pas ete executees avec un vrai projet
Supabase, l'integration reste "implementee mais non testee en
production" -- jamais annoncee comme active.

## 6. Strategie de stockage des fichiers generes/importes

Deux categories de fichiers, deux strategies distinctes :

- **Fichiers generes par les agents** (matrice XLSX, XLSForm,
  registre d'alertes XLSX/CSV) : destines a **Supabase Storage**, un
  bucket par organisation (`org-<organisation_id>`), avec policies de
  storage miroir des policies RLS SQL (un utilisateur ne peut lire/
  ecrire que dans le bucket de son organisation). La colonne
  `formulaires.stockage_path` et une future colonne equivalente sur
  `anomalies`/un futur `rapports` stockent la cle Storage, jamais le
  contenu binaire en base.
- **Fichiers sources importes par l'utilisateur** (description de
  projet, CSV de soumissions) : memes bucket/policies -- jamais
  stockes a la racine commune, toujours sous un prefixe
  `org-<organisation_id>/projet-<projet_id>/`.
- **Transition depuis le mode fichier local actuel** : le code
  `platform/app/core/storage.py` isole deja par `client_id` -- la
  migration vers Supabase Storage remplacera `STORAGE_ROOT / client_id`
  par un prefixe de bucket equivalent, sans changer la logique
  d'isolation deja en place (meme principe, autre backend).
- **URLs de telechargement** : signees et a duree limitee (Supabase
  Storage `createSignedUrl`), jamais d'URL publique permanente pour
  un fichier contenant des donnees de projet/beneficiaires.

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
