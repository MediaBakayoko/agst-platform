# Procedure de rollback (deploiement Docker)

**STATUT : procedure documentee et verifiable, testee par simulation
locale le 2026-10-28 (build + run + health reel, voir
`deploiement_production.md`). Jamais executee sur un VPS reel (aucun
VPS achete a ce jour).**

## Principe

Chaque image buildee est taguee avec un identifiant unique (jamais
seulement `latest`), pour pouvoir revenir instantanement a la version
precedente sans rebuild.

## Avant deploiement d'une nouvelle version

```bash
# Tag avec le hash du commit couvrant exactement le code deploye
GIT_SHA=$(git rev-parse --short HEAD)
docker build -f platform/Dockerfile -t agst-platform:$GIT_SHA -t agst-platform:latest .

# Conserver explicitement la version precedente avant de la remplacer
docker tag agst-platform:latest agst-platform:previous
```

## Deploiement

```bash
docker compose -f platform/deploy/docker-compose.yml up -d
# Attendre le healthcheck (jusqu'a ~45s : start_period 10s + 3 retries x timeout 5s)
docker compose -f platform/deploy/docker-compose.yml ps
curl -f https://<DOMAINE>/health || echo "ECHEC HEALTHCHECK -- rollback immediat"
```

## Rollback (si /health echoue ou comportement anormal signale)

```bash
# Revenir au tag precedent, sans rebuild
docker tag agst-platform:previous agst-platform:latest
docker compose -f platform/deploy/docker-compose.yml up -d --force-recreate agst-platform
curl -f https://<DOMAINE>/health
```

## Verification post-rollback

1. `GET /health` repond 200.
2. `docker compose logs agst-platform --tail=50` ne montre aucune
   exception repetee.
3. Un job existant reste accessible (`GET /jobs/<job_id>` avec
   l'identite du proprietaire) -- confirme que le rollback n'a pas
   casse l'acces aux donnees deja persistees (Supabase, externe au
   conteneur, n'est jamais affecte par un rollback applicatif).

## Limite actuelle

- Pas encore de registre d'images distant (Docker Hub prive ou
  equivalent) -- les tags `previous`/`latest` vivent uniquement sur le
  VPS lui-meme. Si le disque du VPS est perdu, il faut rebuild depuis
  le commit Git correspondant (voir tag `$GIT_SHA` conserve dans
  l'historique Git, pas seulement dans Docker).
- Aucune automatisation CI/CD a ce jour -- chaque etape ci-dessus est
  manuelle, executee par un operateur humain via SSH sur le VPS.
