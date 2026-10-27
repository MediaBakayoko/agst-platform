"""
AGST Platform -- point d'entree FastAPI.

Orchestre 8 agents specialises derriere une API unique, avec isolation
stricte des donnees par client.

Lancer en local :
    uvicorn app.main:app --reload --port 8000

Lancer en production (ex: gunicorn + workers uvicorn) :
    gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000
"""
from __future__ import annotations

import logging
import time

# IMPORTANT : charger .env AVANT tout import de app.* -- plusieurs
# modules (app.core.auth notamment) lisent os.getenv() au moment de
# l'import, pas a l'execution. Si .env est charge trop tard, le
# serveur reste en DEV_MODE par erreur.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.routers import (
    academy_knowledge,
    consulting_business,
    data_science_geoai,
    eudr_forest_monitoring,
    field2report,
    files,
    geodata_quality,
    jobs,
    meal_project_performance,
    survey_intelligence,
)

logger = logging.getLogger("agst_platform")

# Limite de requetes par defaut -- protection minimale contre les abus
# avant tout deploiement public. A ajuster une fois le volume reel de
# clients connu (actuellement une valeur de depart raisonnable, pas
# mesuree en charge reelle).
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(
    title="AGST Platform",
    description=(
        "API d'orchestration des agents AGST (geodata_quality, field2report, "
        "eudr_forest_monitoring, consulting_business, meal_project_performance, "
        "data_science_geoai, academy_knowledge, survey_intelligence). "
        "Isolation stricte des donnees par client. "
        "Aucune action financiere/contractuelle/de deploiement automatique."
    ),
    version="0.2.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS : a restreindre a l'origine reelle du frontend avant tout usage
# client reel (actuellement '*' car l'origine Lovable finale n'est pas
# encore figee -- TODO explicite, ne pas oublier avant mise en production).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restreindre a l'origine Lovable/production avant mise en service reelle
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests_without_sensitive_data(request: Request, call_next):
    """Journalise chaque requete (methode, chemin, duree, code retour)
    sans jamais logger le corps de la requete ni les en-tetes
    d'authentification -- evite toute fuite de donnees personnelles ou
    de secrets dans les journaux techniques.
    """
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info("%s %s -> %d (%sms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Toute exception non prevue renvoie une erreur generique au
    client (jamais la trace complete, qui pourrait exposer des chemins
    serveur ou des details internes) -- la trace reelle reste dans les
    journaux serveur uniquement.
    """
    logger.exception("Erreur non geree sur %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur -- consultez les journaux serveur."})


app.include_router(geodata_quality.router)
app.include_router(field2report.router)
app.include_router(eudr_forest_monitoring.router)
app.include_router(consulting_business.router)
app.include_router(meal_project_performance.router)
app.include_router(data_science_geoai.router)
app.include_router(academy_knowledge.router)
app.include_router(survey_intelligence.router)
app.include_router(jobs.router)
app.include_router(files.router)


@app.get("/health")
def health():
    """Controle de sante minimal -- ne verifie pas encore les
    dependances externes (Supabase, Kobo) tant qu'elles ne sont pas
    connectees. A etendre une fois ces integrations actives.
    """
    return {"status": "ok", "service": "agst-platform", "version": app.version}
