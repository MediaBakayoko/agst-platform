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

Tant que ces 5 etapes n'ont pas ete executees avec un vrai projet
Supabase, l'integration reste "implementee mais non testee en
production" -- jamais annoncee comme active.

## Ce qui est deja prepare cote code

- `platform/supabase/migrations/0001_survey_intelligence_schema.sql` --
  schema complet (organisations, membres, projets, indicateurs,
  formulaires, soumissions, anomalies, synchronisations) avec RLS par
  organisation.
- `platform/app/core/auth.py` -- squelette JWT deja pret, bascule
  automatique dès que `SUPABASE_JWT_SECRET` est configure (voir code,
  non modifie par cette mission -- deja fonctionnel structurellement,
  jamais teste avec un vrai token Supabase).
