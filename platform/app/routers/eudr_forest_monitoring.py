"""Route EUDR & Forest Monitoring : upload parcelles + 2 rasters -> job isole.

Rappel : cette route ne retourne jamais de conclusion de conformite ou
d'infraction EUDR -- uniquement des alertes a examiner (voir sortie de
l'agent sous-jacent).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import run_agent_job
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse

router = APIRouter(prefix="/agents/eudr-forest-monitoring", tags=["eudr_forest_monitoring"])


@router.post("/check", response_model=JobCreatedResponse)
async def run_eudr_check(
    parcels: UploadFile,
    forest_baseline: UploadFile,
    forest_recent: UploadFile,
    id_field: str = Form(default=""),
    alert_threshold_moderate_pct: float = Form(default=5.0),
    alert_threshold_high_pct: float = Form(default=20.0),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)

    parcels_path = job_dir / parcels.filename
    parcels_path.write_bytes(await parcels.read())
    baseline_path = job_dir / forest_baseline.filename
    baseline_path.write_bytes(await forest_baseline.read())
    recent_path = job_dir / forest_recent.filename
    recent_path.write_bytes(await forest_recent.read())

    cli_args = [
        "--parcels", str(parcels_path),
        "--forest-baseline", str(baseline_path),
        "--forest-recent", str(recent_path),
        "--output-dir", str(job_dir),
        "--alert-threshold-moderate-pct", str(alert_threshold_moderate_pct),
        "--alert-threshold-high-pct", str(alert_threshold_high_pct),
    ]
    if id_field:
        cli_args += ["--id-field", id_field]

    meta = run_agent_job("eudr_forest_monitoring", job_dir, client.client_id, job_id, cli_args)
    return JobCreatedResponse(
        job_id=job_id, agent="eudr_forest_monitoring", statut=meta["statut"],
        message=(
            "Job termine -- RAPPEL : les resultats sont des ALERTES a examiner par un "
            "expert, jamais une conclusion de conformite/infraction EUDR. "
            "Voir GET /jobs/{job_id} pour le detail."
        ),
    )
