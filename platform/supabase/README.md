# Supabase -- Procedure de configuration (NON ENCORE CONNECTE)

**STATUT ACTUEL : migrations preparees, code NON teste contre un vrai
projet Supabase.** Aucun credential Supabase n'est disponible a ce
jour. Ne pas annoncer cette integration comme operationnelle avant un
test reel.

## 1. Creer le projet Supabase

1. Compte sur [supabase.com](https://supabase.com) (gratuit pour demarrer).
2. "New project" -> nom (ex: `agst-survey-intelligence`), region proche
   (Europe de l'Ouest recommandee pour la latence Cote d'Ivoire/France).
3. Noter le mot de passe de base de donnees genere (a stocker dans un
   gestionnaire de secrets, jamais en clair dans un fichier versionne).

## 2. Appliquer les migrations

Avec la CLI Supabase (`npm install -g supabase`) :
```bash
supabase link --project-ref <ref-du-projet>
supabase db push
```
Ou directement coller le contenu de
`platform/supabase/migrations/0001_survey_intelligence_schema.sql`
dans le SQL Editor du dashboard Supabase.

## 3. Recuperer les credentials

Dans Project Settings -> API :
- `SUPABASE_URL` (ex: `https://xxxx.supabase.co`)
- `SUPABASE_ANON_KEY` (cle publique -- OK cote frontend, mais n'est PAS
  un secret suffisant seule : l'autorisation reelle vient des policies
  RLS, pas de cette cle)
- `SUPABASE_JWT_SECRET` (Project Settings -> API -> JWT Settings) --
  **secret serveur uniquement**, jamais dans le frontend
- `SUPABASE_SERVICE_ROLE_KEY` -- **secret serveur uniquement, jamais
  dans le frontend**, utilise seulement pour des operations
  d'administration explicites (ex: taches planifiees de
  synchronisation Kobo tournant cote serveur)

## 4. Configurer le backend

Variables d'environnement (`platform/.env`, jamais committe) :
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_JWT_SECRET=...
SUPABASE_SERVICE_ROLE_KEY=...
```
Dès que `SUPABASE_JWT_SECRET` est present, `platform/app/core/auth.py`
bascule automatiquement hors du mode developpement (`X-Client-Id`) et
exige un Bearer token Supabase reel.

Installer le client Python :
```bash
pip install supabase
```

## 5. Tester reellement avant de declarer l'integration active

Un fichier de tests SQL est prepare :
`platform/supabase/tests/0001_rls_isolation_tests.sql` -- a executer
dans le SQL Editor Supabase (environnement de test, jamais directement
sur une base de production) une fois la migration appliquee. Il
verifie automatiquement :
1. Toutes les tables attendues existent.
2. RLS est active sur les 8 tables sensibles.
3. Isolation reelle entre 2 organisations (bloc commente -- necessite
   de creer 2 utilisateurs de test au prealable et de remplacer les
   UUID placeholders avant de decommenter).
4. Aucune colonne `cible`/`valeur_reference` n'a de valeur par defaut
   non-NULL (verifie qu'aucune donnee n'est inventee au niveau schema).
5. Les contraintes CHECK rejettent une valeur de statut invalide.

Etapes manuelles complementaires (non automatisables sans vrais comptes) :
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
  organisation.
- `platform/app/core/auth.py` -- squelette JWT deja pret, bascule
  automatique dès que `SUPABASE_JWT_SECRET` est configure (voir code,
  non modifie par cette mission -- deja fonctionnel structurellement,
  jamais teste avec un vrai token Supabase).
