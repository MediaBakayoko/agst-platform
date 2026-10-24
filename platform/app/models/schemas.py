"""Modeles Pydantic des reponses API (requetes : multipart/form-data, voir routers)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobCreatedResponse(BaseModel):
    job_id: str
    agent: str
    statut: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    agent: str
    client_id: str
    statut: str
    duree_secondes: Optional[float] = None
    code_retour: Optional[int] = None
    erreur: Optional[str] = None
    fichiers_sortie: list[str] = []


class JobListResponse(BaseModel):
    client_id: str
    jobs: list[str]
