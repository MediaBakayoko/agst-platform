# AGST Platform — Orchestrateur

API (FastAPI) qui orchestre les 4 agents spécialisés
(`geodata_quality`, `field2report`, `eudr_forest_monitoring`,
`consulting_business`) derrière une interface web unique, avec gestion
des utilisateurs et isolation stricte des données par client.

## Principes (non négociables)

- **Isolation multi-client totale** : un client ne voit jamais les
  données, fichiers ou résultats d'un autre. Toute requête est scopée
  par `client_id` dérivé du token d'authentification — jamais fourni
  librement par le client dans le corps de la requête.
- **Les agents n'accèdent qu'à ce qui leur est nécessaire** : chaque
  job d'agent reçoit un dossier de travail isolé
  (`storage/<client_id>/<job_id>/`), jamais un accès direct au stockage
  global.
- **Pas de facturation/paiement dans cette version** : l'architecture
  prévoit un modèle `Plan`/`Usage` mais aucun prestataire de paiement
  n'est connecté — à activer plus tard sur demande explicite, avant
  tout premier client réel.
- **Pas d'action financière/contractuelle automatique.**
- **Journalisation complète** : chaque job (agent appelé, client,
  paramètres, statut, durée) est tracé pour audit.

## Architecture

```
platform/
  app/
    main.py              # point d'entree FastAPI
    core/
      auth.py             # authentification (JWT, prevu pour Supabase Auth)
      storage.py           # isolation des fichiers par client_id
      job_runner.py         # execution des scripts agents en sous-processus isole
    routers/
      geodata_quality.py
      field2report.py
      eudr_forest_monitoring.py
      consulting_business.py
      jobs.py              # suivi des jobs (statut, resultats)
    models/
      schemas.py           # modeles Pydantic (requetes/reponses)
  tests/
```

## Stack

- **Backend** : FastAPI (Python) — même écosystème que les 4 agents,
  pas de pont de langage.
- **Auth + DB + storage** : Supabase (Postgres/PostGIS géré, Auth,
  Storage) — prévu, pas encore connecté dans cette version (nécessite
  les credentials Supabase du projet, à créer).
- **Interface utilisateur** : générée via Lovable, connectée à ce repo
  GitHub, consommant cette API.
- **Exécution des agents** : chaque appel d'agent tourne en
  sous-processus isolé (le CLI de chaque agent, inchangé), avec un
  dossier de travail dédié au job — aucune modification du code des
  agents n'a été nécessaire pour les orchestrer.

## Isolation multi-client : comment ça marche

1. Le client s'authentifie (JWT Supabase Auth, à connecter) →
   `client_id` extrait du token, jamais du corps de la requête.
2. Chaque requête créée un `job_id` unique et un dossier
   `storage/<client_id>/<job_id>/`.
3. Le fichier uploadé est écrit uniquement dans ce dossier.
4. Le script agent (`geodata_quality`, etc.) est appelé en
   sous-processus avec ce dossier comme `--output-dir`, jamais un accès
   au stockage global.
5. Le client ne peut lister/récupérer que les jobs dont le `client_id`
   correspond au sien (vérifié côté serveur, pas côté client).

## Lancer en local (développement)

```bash
cd platform
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API disponible sur `http://localhost:8000/docs` (Swagger auto-généré).

## Statut

🔧 Squelette fonctionnel : routes, isolation par client_id (via header
de dev en attendant Supabase Auth), exécution des 4 agents en
sous-processus, suivi de jobs. **Auth Supabase réelle, déploiement
cloud et facturation restent à faire avant tout client réel.**
