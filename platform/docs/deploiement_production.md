# Preparation au deploiement en production

**STATUT ACTUEL : aucun deploiement public effectue.** Le backend
tourne uniquement en local pour le developpement et les tests. Cette
page documente ce qui doit etre verifie AVANT de deployer sur
l'hebergement choisi (Hostinger mentionne par l'utilisateur, non
encore confirme compatible).

## Verification prealable de l'hebergement (a faire avant tout essai de deploiement)

L'offre Hostinger doit etre verifiee sur ces points avant d'y deployer
quoi que ce soit -- une offre d'hebergement web partage classique
(mutualise, PHP/MySQL) NE PEUT PAS executer FastAPI/Python en process
permanent :

| Critere | Exigence | A verifier sur l'offre Hostinger |
|---|---|---|
| Support Python/FastAPI | Process Python long-lived (pas CGI/PHP seul) | Necessite VPS ou "Cloud Hosting" Hostinger, pas l'hebergement web partage standard |
| Variables d'environnement | Configuration de secrets hors code | A confirmer selon le panel Hostinger choisi |
| Acces reseau sortant | Vers Supabase et Kobo (HTTPS sortant) | Generalement OK sur VPS, a verifier sur offre partagee |
| HTTPS | Certificat TLS pour le domaine de l'API | Let's Encrypt generalement disponible sur VPS |
| Journaux/supervision | Acces aux logs applicatifs, redemarrage auto en cas de crash | Necessite systemd/supervisor sur VPS ; absent sur hebergement partage |
| Taches planifiees/workers | Pour la synchronisation Kobo periodique (section 7 de la mission) | Necessite cron reel ou process planifie -- VPS requis |

**Conclusion probable (a confirmer avec le panel Hostinger reel avant
d'agir) : un VPS Hostinger est necessaire, pas l'hebergement web
mutualise standard.** Decision bloquee tant que l'utilisateur n'a pas
confirme/choisi l'offre exacte -- ne pas deployer en aveugle.

## Configuration de production preparee (code pret, non deploye)

- `Dockerfile` (nouveau, racine `platform/`) : image reproductible
  (Python 3.11-slim, gunicorn + workers uvicorn, HEALTHCHECK Docker
  natif sur `/health`). **Ecrit et relu, mais NON teste par
  execution reelle** -- `docker build` a echoue car le moteur Docker
  Desktop est installe mais son service est `STOPPED` (`sc query
  com.docker.service` confirme), et le demarrer necessite une
  elevation admin interactive que cette session ne peut pas
  declencher. Action utilisateur necessaire : demarrer Docker Desktop
  manuellement, puis relancer `docker build -f platform/Dockerfile -t
  agst-platform:test .` depuis la racine du depot pour valider
  reellement l'image avant toute utilisation.
- `app/main.py` : limite de requetes (slowapi, 60/min par IP --
  valeur de depart, a ajuster), gestionnaire d'erreur global (jamais
  de trace exposee au client), journalisation structuree sans donnees
  sensibles.
- `/health` : controle de sante basique (etendre pour verifier
  Supabase/Kobo une fois connectes).
- Lancement production recommande (sans Docker, directement) :
  ```bash
  pip install -r requirements.txt
  gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000
  ```
- Mesures reelles observees (2026-10-27, charge faible, test unique
  -- pas une charge soutenue) :
  - Processus uvicorn seul (orchestrateur FastAPI au repos, apres
    import des 8 routers) : **60 Mo RSS**, CPU ~0% (mesure directe
    via psutil sur le process reel).
  - Chaque job agent s'execute dans un sous-processus Python ephemere
    (timeout 600s, `job_runner.py`/`consulting_business._run_script`)
    -- le pic depend de l'agent appele.
  - **Pic reel mesure pour `geodata_quality`** (l'agent le plus lourd :
    geopandas + shapely + GDAL) sur un fichier `.gpkg` reel de test :
    **~193 Mo RSS cumules** (orchestrateur + sous-processus), job
    termine en **10,8 secondes**. C'est le cas le plus defavorable
    observe parmi les 8 agents (les autres n'utilisent que
    pandas/openpyxl/scikit-learn, plus legers -- non mesures
    individuellement, mais tous strictement inferieurs a ce pic selon
    l'audit des dependances par agent).
  - Import seul de geopandas+rasterio+scikit-learn+pandas+matplotlib
    dans un process Python frais : **+157 Mo** par rapport au process
    vide -- confirme que le cout vient des bibliotheques geospatiales/
    ML, pas du code AGST lui-meme.
- Variables d'environnement a definir en production (jamais en dur) :
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_DB_URL` (persistance jobs/fichiers), `KOBO_BASE_URL`,
  `KOBO_API_TOKEN` (une fois disponibles, voir
  `platform/supabase/README.md` section 7).

## CORS a restreindre avant mise en service reelle

`app/main.py` a actuellement `allow_origins=["*"]` -- **a restreindre
a l'origine exacte du frontend Lovable/production** des qu'elle est
connue et stable (actuellement non figee, le projet Lovable etant
encore en construction).

## Architecture de deploiement proposee (Hostinger VPS, non deployee)

**Prerequis confirme ci-dessus : un hebergement web mutualise
classique ne peut pas executer ce backend.** Un VPS (ou "Cloud
Hosting" Hostinger equivalent) est necessaire pour un process Python
long-lived, les taches planifiees de synchronisation Kobo, et l'acces
reseau sortant vers Supabase/Kobo.

### Topologie proposee (Docker Compose)

```
                    Internet (HTTPS)
                          |
                  [Caddy ou Nginx]  <- reverse proxy, TLS Let's Encrypt automatique
                          |
                  [agst-platform]   <- container FastAPI/gunicorn (ce depot)
                          |
                  Supabase (externe, deja hebergee par Supabase)
```

- **Reverse proxy** : Caddy recommande (configuration TLS automatique
  en 3 lignes, renouvellement Let's Encrypt sans intervention) plutot
  que Nginx+Certbot (plus de pieces a maintenir manuellement).
- **Container applicatif** : l'image `Dockerfile` deja ecrite
  (gunicorn + 2 workers uvicorn, `HEALTHCHECK` natif sur `/health`) --
  **non testee par execution reelle** (Docker Desktop local toujours
  `STOPPED`, meme blocage que documente precedemment), mais relue et
  coherente avec les mesures reelles ci-dessus.
- **Redemarrage automatique** : `restart: unless-stopped` dans
  `docker-compose.yml` + le `HEALTHCHECK` Docker existant -- un
  container qui echoue son healthcheck de facon repetee est redemarre
  par Docker lui-meme, sans intervention manuelle.
- **Journaux** : `--access-logfile -` / `--error-logfile -` deja
  configures dans le `Dockerfile` (sortie stdout/stderr du container,
  capturable par `docker logs` ou redirigee vers un fichier via
  `docker-compose` `logging:` driver). Le middleware applicatif
  (`app/main.py`) journalise deja chaque requete sans corps ni
  en-tetes d'auth -- a verifier qu'aucun secret ne fuite dans ces
  logs avant mise en service reelle (audit a refaire specifiquement
  sur les logs Kobo/Supabase une fois ces integrations actives).
- **Secrets** : fichier `.env` sur le VPS (jamais dans l'image Docker,
  jamais dans Git), monte via `env_file:` dans `docker-compose.yml`,
  permissions restreintes (`chmod 600`).
- **Domaine** : sous-domaine dedie (ex: `api.agst.<domaine>`) pointant
  vers l'IP du VPS, configure cote DNS Hostinger (ou autre registraire
  si le domaine est ailleurs).
- **Sauvegarde/restauration** : voir `docs/sauvegarde_restauration.md`
  pour la procedure actuelle (manuelle) -- **la persistance reelle des
  donnees de production vit desormais dans Supabase** (projet reel
  deja cree, migrations 0001-0004 appliquees), pas sur le disque du
  VPS -- donc la sauvegarde Supabase (gerer via le dashboard Supabase,
  plan de sauvegarde selon le tier) devient le point de sauvegarde
  principal, le disque VPS ne contenant que le stockage fichier local
  "best-effort" (deja duplique vers Supabase Storage) et les logs.

### Dimensionnement estime (a partir des mesures reelles ci-dessus)

**Hypothese de charge** : usage mono-organisation initial (un seul
client reel potentiel a ce jour), quelques dizaines de jobs/jour,
jamais plusieurs jobs `geodata_quality` simultanes au depart.

| Ressource | Besoin minimal estime | Justification |
|---|---|---|
| RAM | **2 Go** | Pic mesure reel ~193 Mo pour 1 job lourd ; marge pour 2-3 jobs concurrents + overhead OS/Docker (~500 Mo) + marge de securite. 1 Go serait limite avec 2 jobs geodata_quality simultanes. |
| CPU | **2 vCPU** | gunicorn configure avec 2 workers (`-w 2`) -- 1 vCPU par worker minimum pour eviter un goulot sur un job CPU-intensif (ex: scikit-learn model_trainer). |
| Disque | **20-40 Go** | Code + dependances (~500 Mo avec GDAL/geopandas) + stockage fichier local temporaire (purge recommandee, donnees dupliquees sur Supabase Storage) + logs + marge. |
| Bande passante | Faible-moderee | Essentiellement API JSON + upload/download de fichiers (XLSX/GPKG, quelques Mo chacun) -- pas de streaming video/lourd. |

**Correspondance Hostinger (gammes VPS publiees, a reverifier sur le
site au moment de l'achat -- prix et gammes changent)** : la gamme
VPS Hostinger la plus basse (generalement ~1 vCPU/4 Go RAM au moment
de la redaction) **depasse deja** le besoin minimal estime en RAM,
mais il faut confirmer le nombre de vCPU reel de l'offre choisie avant
achat -- ne pas se fier a ce document pour un prix exact, le
reverifier sur hostinger.com au moment de la decision. **Aucun achat
n'a ete effectue, aucune offre specifique n'a ete verifiee en direct
sur le site Hostinger pendant cette session** -- recommandation
basee uniquement sur le besoin technique mesure, pas sur un
catalogue consulte reellement.

## Reste a faire avant un deploiement reel

1. Confirmer avec l'utilisateur l'offre Hostinger exacte (VPS,
   nombre de vCPU/RAM reel) -- **non verifiee en direct cette
   session**, estimation ci-dessus basee sur le besoin mesure
   uniquement.
2. Demarrer Docker Desktop localement (ou sur le VPS directement) et
   executer reellement `docker build` + `docker run` au moins une
   fois avant la mise en service -- jamais fait a ce jour (blocage
   recurrent documente).
3. Restreindre CORS a l'origine frontend reelle (toujours `*`
   actuellement).
4. Decider du canal de notification email (aucun fournisseur choisi,
   voir `docs/notifications_prerequis.md`) -- pas bloquant pour le
   deploiement lui-meme, mais a traiter avant une annonce aux
   utilisateurs finaux.
5. Obtenir un compte/token KoboToolbox reel et refaire les tests
   Kobo en conditions reelles avant toute annonce de fonctionnalite
   Kobo active.
6. Tester le deploiement sur l'environnement de staging/VPS reel
   avant toute mise en production avec des clients -- jamais fait a
   ce jour (aucun VPS achete).
