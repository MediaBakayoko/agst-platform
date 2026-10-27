# Image de production pour l'orchestrateur AGST Platform.
# Testee reellement en local (docker build + docker run + /health) --
# voir platform/docs/deploiement_production.md pour la preuve
# d'execution. Reutilisable sur tout hebergeur supportant Docker
# (ou directement sans Docker via gunicorn, voir meme doc).

FROM python:3.11-slim

WORKDIR /app

# Dependances systeme minimales (geopandas/GDAL utilises par
# geodata_quality -- necessaires au build meme si l'agent n'est pas
# appele sur toutes les requetes).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY platform/requirements.txt ./platform/requirements.txt
COPY platform/requirements-agents.txt ./platform/requirements-agents.txt
RUN pip install --no-cache-dir -r platform/requirements.txt \
    && pip install --no-cache-dir -r platform/requirements-agents.txt \
    && pip install --no-cache-dir gunicorn

COPY agents/ ./agents/
COPY platform/ ./platform/

WORKDIR /app/platform

EXPOSE 8000

# Healthcheck Docker natif -- verifie reellement /health, pas
# seulement que le process tourne.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "2", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
