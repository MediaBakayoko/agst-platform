"""Route Academy & Knowledge : plans de cours, exercices, validation de code."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import AGENTS_ROOT
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse
from app.routers.consulting_business import _run_script

router = APIRouter(prefix="/agents/academy-knowledge", tags=["academy_knowledge"])

ACADEMY_SCRIPTS = AGENTS_ROOT / "academy_knowledge" / "scripts"


@router.post("/course-outline", response_model=JobCreatedResponse)
async def course_outline(
    titre: str = Form(...), niveau: str = Form(...), objectifs: str = Form(...),
    duree_heures: float = Form(...), client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    cli_args = ["--titre", titre, "--niveau", niveau, "--objectifs", objectifs,
                "--duree-heures", str(duree_heures), "--output-dir", str(job_dir)]
    meta = _run_script("course_outline_builder.py", "academy_knowledge.course_outline_builder", job_dir, client.client_id, job_id, cli_args, scripts_dir=ACADEMY_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="academy_knowledge.course_outline_builder", statut=meta["statut"],
                               message="Plan de cours genere (brouillon) -- relecture instructeur requise.")


@router.post("/validate-code", response_model=JobCreatedResponse)
async def validate_code(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    code_path = job_dir / file.filename
    code_path.write_bytes(await file.read())
    meta = _run_script("code_validator.py", "academy_knowledge.code_validator", job_dir, client.client_id, job_id,
                        [str(code_path), "--output-dir", str(job_dir)], scripts_dir=ACADEMY_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="academy_knowledge.code_validator", statut=meta["statut"],
                               message="Validation d'execution reelle terminee, voir /jobs/{job_id}.")
