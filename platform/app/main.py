"""
AGST Platform -- point d'entree FastAPI.

Orchestre 4 agents specialises (geodata_quality, field2report,
eudr_forest_monitoring, consulting_business) derriere une API unique,
avec isolation stricte des donnees par client.

Lancer en local :
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    academy_knowledge,
    consulting_business,
    data_science_geoai,
    eudr_forest_monitoring,
    field2report,
    geodata_quality,
    jobs,
    meal_project_performance,
)

app = FastAPI(
    title="AGST Platform",
    description=(
        "API d'orchestration des agents AGST (geodata_quality, field2report, "
        "eudr_forest_monitoring, consulting_business). "
        "Isolation stricte des donnees par client. "
        "Aucune action financiere/contractuelle automatique."
    ),
    version="0.1.0",
)

# CORS : a restreindre a l'origine de l'interface Lovable une fois connue.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restreindre avant tout usage client reel
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(geodata_quality.router)
app.include_router(field2report.router)
app.include_router(eudr_forest_monitoring.router)
app.include_router(consulting_business.router)
app.include_router(meal_project_performance.router)
app.include_router(data_science_geoai.router)
app.include_router(academy_knowledge.router)
app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "agst-platform"}
