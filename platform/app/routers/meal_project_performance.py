"""Route MEAL & Project Performance : cadre de resultats, calcul d'indicateurs, dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import AGENTS_ROOT
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse
from app.routers.consulting_business import _run_script

router = APIRouter(prefix="/agents/meal-project-performance", tags=["meal_project_performance"])

MEAL_SCRIPTS = AGENTS_ROOT / "meal_project_performance" / "scripts"


@router.post("/results-framework", response_model=JobCreatedResponse)
async def results_framework(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    csv_path = job_dir / file.filename
    csv_path.write_bytes(await file.read())
    meta = _run_script("results_framework.py", "meal.results_framework", job_dir, client.client_id, job_id,
                        [str(csv_path), "--output-dir", str(job_dir)], scripts_dir=MEAL_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="meal.results_framework", statut=meta["statut"],
                               message="Cadre de resultats valide, voir /jobs/{job_id}.")


@router.post("/indicator-calculate", response_model=JobCreatedResponse)
async def indicator_calculate(
    indicators_file: UploadFile, values_file: UploadFile,
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    indicators_path = job_dir / "indicators.csv"
    indicators_path.write_bytes(await indicators_file.read())
    values_path = job_dir / "values.csv"
    values_path.write_bytes(await values_file.read())
    meta = _run_script(
        "indicator_calculator.py", "meal.indicator_calculator", job_dir, client.client_id, job_id,
        ["--indicators", str(indicators_path), "--values", str(values_path), "--output-dir", str(job_dir)],
        scripts_dir=MEAL_SCRIPTS,
    )
    return JobCreatedResponse(job_id=job_id, agent="meal.indicator_calculator", statut=meta["statut"],
                               message="Indicateurs calcules, voir /jobs/{job_id}.")
