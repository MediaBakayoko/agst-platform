"""Route Data Science & GeoAI : audit de donnees, tests statistiques, modelisation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import AGENTS_ROOT
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse
from app.routers.consulting_business import _run_script

router = APIRouter(prefix="/agents/data-science-geoai", tags=["data_science_geoai"])

DS_SCRIPTS = AGENTS_ROOT / "data_science_geoai" / "scripts"


@router.post("/inspect", response_model=JobCreatedResponse)
async def inspect(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    data_path = job_dir / file.filename
    data_path.write_bytes(await file.read())
    meta = _run_script("data_inspector.py", "data_science_geoai.data_inspector", job_dir, client.client_id, job_id,
                        [str(data_path), "--output-dir", str(job_dir)], scripts_dir=DS_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="data_science_geoai.data_inspector", statut=meta["statut"],
                               message="Audit termine, voir /jobs/{job_id}.")


@router.post("/statistical-test", response_model=JobCreatedResponse)
async def statistical_test(
    file: UploadFile, test: str = Form(...), field_x: str = Form(...),
    field_y: Optional[str] = Form(default=None), group_field: Optional[str] = Form(default=None),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    data_path = job_dir / file.filename
    data_path.write_bytes(await file.read())
    cli_args = [str(data_path), "--test", test, "--field-x", field_x, "--output-dir", str(job_dir)]
    if field_y:
        cli_args += ["--field-y", field_y]
    if group_field:
        cli_args += ["--group-field", group_field]
    meta = _run_script("statistical_tests.py", "data_science_geoai.statistical_tests", job_dir, client.client_id, job_id, cli_args, scripts_dir=DS_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="data_science_geoai.statistical_tests", statut=meta["statut"],
                               message="Test statistique termine, voir /jobs/{job_id}.")


@router.post("/train-model", response_model=JobCreatedResponse)
async def train_model(
    file: UploadFile, target: str = Form(...), features: str = Form(...),
    model_type: str = Form(...), client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    data_path = job_dir / file.filename
    data_path.write_bytes(await file.read())
    cli_args = [str(data_path), "--target", target, "--features", features, "--model-type", model_type, "--output-dir", str(job_dir)]
    meta = _run_script("model_trainer.py", "data_science_geoai.model_trainer", job_dir, client.client_id, job_id, cli_args, scripts_dir=DS_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="data_science_geoai.model_trainer", statut=meta["statut"],
                               message="Modele entraine et evalue (prototype) -- validation humaine requise avant usage operationnel.")
