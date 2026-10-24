"""Route de suivi des jobs : statut, liste, telechargement des resultats.
Toujours scope par client_id authentifie -- jamais d'acces croise entre
clients.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.auth import ClientIdentity, get_current_client
from app.core.storage import job_dir_for, list_jobs_for
from app.models.schemas import JobListResponse, JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def list_jobs(client: ClientIdentity = Depends(get_current_client)):
    return JobListResponse(client_id=client.client_id, jobs=list_jobs_for(client.client_id))


@router.get("/{job_id}", response_model=JobStatusResponse)
def job_status(job_id: str, client: ClientIdentity = Depends(get_current_client)):
    try:
        job_dir = job_dir_for(client.client_id, job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job introuvable pour ce client")

    meta_path = job_dir / "job_meta.json"
    if not meta_path.exists():
        raise HTTPException(404, "Metadonnees de job introuvables")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    output_files = [
        p.name for p in job_dir.rglob("*")
        if p.is_file() and p.name != "job_meta.json" and p.name != "input"
    ]

    return JobStatusResponse(
        job_id=job_id,
        agent=meta.get("agent", ""),
        client_id=client.client_id,
        statut=meta.get("statut", "inconnu"),
        duree_secondes=meta.get("duree_secondes"),
        code_retour=meta.get("code_retour"),
        erreur=meta.get("erreur"),
        fichiers_sortie=output_files,
    )


@router.get("/{job_id}/files/{filename}")
def download_job_file(job_id: str, filename: str, client: ClientIdentity = Depends(get_current_client)):
    try:
        job_dir = job_dir_for(client.client_id, job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job introuvable pour ce client")

    matches = [p for p in job_dir.rglob("*") if p.is_file() and p.name == filename]
    if not matches:
        raise HTTPException(404, "Fichier introuvable dans ce job")
    return FileResponse(str(matches[0]), filename=filename)
