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

- `app/main.py` : limite de requetes (slowapi, 60/min par IP --
  valeur de depart, a ajuster), gestionnaire d'erreur global (jamais
  de trace exposee au client), journalisation structuree sans donnees
  sensibles.
- `/health` : controle de sante basique (etendre pour verifier
  Supabase/Kobo une fois connectes).
- Lancement production recommande :
  ```bash
  pip install -r requirements.txt
  gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000
  ```
- Variables d'environnement a definir en production (jamais en dur) :
  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
  `SUPABASE_SERVICE_ROLE_KEY` (si taches serveur), credentials Kobo
  par organisation (stockage cote serveur, voir
  `agents/survey_intelligence/scripts/kobo_connector.py`).

## CORS a restreindre avant mise en service reelle

`app/main.py` a actuellement `allow_origins=["*"]` -- **a restreindre
a l'origine exacte du frontend Lovable/production** des qu'elle est
connue et stable (actuellement non figee, le projet Lovable etant
encore en construction).

## Reste a faire avant un deploiement reel

1. Confirmer avec l'utilisateur l'offre Hostinger exacte (VPS ou
   autre) et verifier les criteres ci-dessus.
2. Connecter Supabase (migrations pretes, voir
   `platform/supabase/README.md`).
3. Restreindre CORS a l'origine frontend reelle.
4. Mettre en place une sauvegarde automatique (actuellement manuelle,
   voir `docs/sauvegarde_restauration.md`).
5. Tester le deploiement sur un environnement de staging avant la
   mise en production reelle avec des clients.
