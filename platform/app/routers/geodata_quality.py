"""Route GeoData Quality : upload fichier geospatial -> job isole -> appel
du script agent -> resultats telechargeables via /jobs/{job_id}/files/.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import run_agent_job
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse

router = APIRouter(prefix="/agents/geodata-quality", tags=["geodata_quality"])


@router.post("/check", response_model=JobCreatedResponse)
async def run_quality_check(
    file: UploadFile,
    required_fields: str = Form(default=""),
    numeric_fields: str = Form(default=""),
    dedup_key_fields: str = Form(default=""),
    area_field: Optional[str] = Form(default=None),
    area_tolerance_pct: float = Form(default=20.0),
    dup_tolerance_m: float = Form(default=0.0),
    id_field: Optional[str] = Form(default=None),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    input_path = job_dir / file.filename
    input_path.write_bytes(await file.read())

    cli_args = [
        str(input_path), "--output-dir", str(job_dir),
        "--required-fields", required_fields,
        "--numeric-fields", numeric_fields,
        "--dedup-key-fields", dedup_key_fields,
        "--area-tolerance-pct", str(area_tolerance_pct),
        "--dup-tolerance-m", str(dup_tolerance_m),
    ]
    if area_field:
        cli_args += ["--area-field", area_field]
    if id_field:
        cli_args += ["--id-field", id_field]

    meta = run_agent_job("geodata_quality", job_dir, client.client_id, job_id, cli_args)
    return JobCreatedResponse(
        job_id=job_id, agent="geodata_quality", statut=meta["statut"],
        message="Job termine, voir GET /jobs/{job_id} pour le detail et les fichiers.",
    )
