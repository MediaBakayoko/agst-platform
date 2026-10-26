"""Routes Survey Intelligence : conception/validation d'enquete,
contrôle qualite de soumissions. Aucun deploiement Kobo reel dans
cette phase (voir kobo_connector.py et README -- connecteur HTTP
implemente mais jamais teste contre un vrai serveur Kobo, faute de
credentials).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import AGENTS_ROOT
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse
from app.routers.consulting_business import _run_script

router = APIRouter(prefix="/agents/survey-intelligence", tags=["survey_intelligence"])

SI_SCRIPTS = AGENTS_ROOT / "survey_intelligence" / "scripts"


@router.post("/project-intake", response_model=JobCreatedResponse)
async def project_intake(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    desc_path = job_dir / file.filename
    desc_path.write_bytes(await file.read())
    meta = _run_script("project_intake.py", "survey_intelligence.project_intake", job_dir, client.client_id, job_id,
                        [str(desc_path), "--output-dir", str(job_dir)], scripts_dir=SI_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="survey_intelligence.project_intake", statut=meta["statut"],
                               message="Projet structure, voir /jobs/{job_id}. Elements manquants a demander explicitement.")


@router.post("/indicator-matrix", response_model=JobCreatedResponse)
async def indicator_matrix(
    project_json: UploadFile, indicators_csv: UploadFile,
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    project_path = job_dir / "project_structured.json"
    project_path.write_bytes(await project_json.read())
    indicators_path = job_dir / "indicators.csv"
    indicators_path.write_bytes(await indicators_csv.read())
    meta = _run_script(
        "indicator_matrix_builder.py", "survey_intelligence.indicator_matrix_builder", job_dir, client.client_id, job_id,
        ["--project", str(project_path), "--indicators", str(indicators_path), "--output-dir", str(job_dir)],
        scripts_dir=SI_SCRIPTS,
    )
    return JobCreatedResponse(job_id=job_id, agent="survey_intelligence.indicator_matrix_builder", statut=meta["statut"],
                               message="Matrice d'indicateurs generee (brouillon) -- cibles manquantes a arbitrer avant approbation.")


@router.post("/xlsform-build", response_model=JobCreatedResponse)
async def xlsform_build(
    matrix_file: UploadFile, form_title: Optional[str] = Form(default=None),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    matrix_path = job_dir / matrix_file.filename
    matrix_path.write_bytes(await matrix_file.read())
    cli_args = ["--matrix", str(matrix_path), "--output-dir", str(job_dir)]
    if form_title:
        cli_args += ["--form-title", form_title]
    meta = _run_script("xlsform_builder.py", "survey_intelligence.xlsform_builder", job_dir, client.client_id, job_id, cli_args, scripts_dir=SI_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="survey_intelligence.xlsform_builder", statut=meta["statut"],
                               message="XLSForm genere -- NON DEPLOYE. Valider puis approuver avant tout deploiement.")


@router.post("/xlsform-validate", response_model=JobCreatedResponse)
async def xlsform_validate(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    form_path = job_dir / file.filename
    form_path.write_bytes(await file.read())
    meta = _run_script("xlsform_validator.py", "survey_intelligence.xlsform_validator", job_dir, client.client_id, job_id,
                        [str(form_path), "--output-dir", str(job_dir)], scripts_dir=SI_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="survey_intelligence.xlsform_validator", statut=meta["statut"],
                               message="Validation terminee, voir /jobs/{job_id} pour le resultat (VALIDE ou INVALIDE).")


@router.post("/quality-check", response_model=JobCreatedResponse)
async def quality_check(
    file: UploadFile, project_id: str = Form(default="projet_non_specifie"),
    required_fields: str = Form(default=""), numeric_fields: str = Form(default=""),
    gps_fields: str = Form(default=""), dedup_key_fields: str = Form(default=""),
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    data_path = job_dir / file.filename
    data_path.write_bytes(await file.read())
    cli_args = [
        str(data_path), "--project-id", project_id,
        "--required-fields", required_fields, "--numeric-fields", numeric_fields,
        "--gps-fields", gps_fields, "--dedup-key-fields", dedup_key_fields,
        "--output-dir", str(job_dir),
    ]
    meta = _run_script("survey_quality_checks.py", "survey_intelligence.survey_quality_checks", job_dir, client.client_id, job_id, cli_args, scripts_dir=SI_SCRIPTS)
    return JobCreatedResponse(job_id=job_id, agent="survey_intelligence.survey_quality_checks", statut=meta["statut"],
                               message="Registre d'alertes genere, voir /jobs/{job_id}.")
