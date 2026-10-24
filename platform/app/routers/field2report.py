"""Route Field2Report : upload CSV/Excel d'enquete -> job isole -> pipeline complet."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import run_agent_job
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse

router = APIRouter(prefix="/agents/field2report", tags=["field2report"])


@router.post("/run", response_model=JobCreatedResponse)
async def run_pipeline(
    file: UploadFile,
    lat_field: Optional[str] = Form(default=None),
    lon_field: Optional[str] = Form(default=None),
    group_field: Optional[str] = Form(default=None),
    numeric_fields: str = Form(default=""),
    text_fields: str = Form(default=""),
    required_fields: str = Form(default=""),
    dedup_key_fields: str = Form(default=""),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    cli_args = [
        str(input_path), "--output-dir", str(job_dir),
        "--numeric-fields", numeric_fields,
        "--text-fields", text_fields,
        "--required-fields", required_fields,
        "--dedup-key-fields", dedup_key_fields,
    ]
    if lat_field:
        cli_args += ["--lat-field", lat_field]
    if lon_field:
        cli_args += ["--lon-field", lon_field]
    if group_field:
        cli_args += ["--group-field", group_field]

    meta = run_agent_job("field2report", job_dir, client.client_id, job_id, cli_args)
    return JobCreatedResponse(
        job_id=job_id, agent="field2report", statut=meta["statut"],
        message="Job termine, voir GET /jobs/{job_id} pour le detail et les fichiers.",
    )
