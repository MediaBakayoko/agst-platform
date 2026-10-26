"""Routes Survey Intelligence : conception/validation d'enquete,
contrôle qualite de soumissions. Aucun deploiement Kobo reel dans
cette phase (voir kobo_connector.py et README -- connecteur HTTP
implemente mais jamais teste contre un vrai serveur Kobo, faute de
credentials).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel

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


class AlertUpdateRequest(BaseModel):
    nouveau_statut: str
    commentaire: Optional[str] = None


ALLOWED_ALERT_STATUSES = {"nouvelle", "a_verifier", "correction_demandee", "corrigee", "cloturee", "faux_positif"}


@router.patch("/alertes/{job_id}/{id_soumission}")
async def update_alert_status(
    job_id: str, id_soumission: str, body: AlertUpdateRequest,
    client: ClientIdentity = Depends(get_current_client),
):
    """Permet a un superviseur de faire evoluer le statut d'une alerte
    du registre genere par un quality-check, avec historique conserve
    (jamais de perte de l'etat precedent). Ne modifie JAMAIS la
    soumission source -- uniquement le registre d'alertes derive.
    """
    import pandas as pd
    from app.core.storage import job_dir_for

    if body.nouveau_statut not in ALLOWED_ALERT_STATUSES:
        raise HTTPException(400, f"Statut invalide : {body.nouveau_statut}. Valeurs autorisees : {sorted(ALLOWED_ALERT_STATUSES)}")

    try:
        job_dir = job_dir_for(client.client_id, job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Job introuvable pour ce client")

    # survey_quality_checks.py ecrit dans un sous-dossier horodate
    # (quality_<nom>_<timestamp>/) plutot qu'a la racine du job --
    # on cherche le registre_alertes.csv quel que soit ce sous-dossier.
    matches = list(job_dir.glob("**/registre_alertes.csv"))
    if not matches:
        raise HTTPException(404, "Registre d'alertes introuvable pour ce job")
    csv_path = matches[0]

    df = pd.read_csv(csv_path)
    # object dtype explicite pour historique_corrections : c'est une
    # colonne texte JSON, jamais numerique -- evite le FutureWarning
    # pandas et le downcast errone si la colonne est entierement vide
    # au depart (NaN -> float64 par defaut).
    df["historique_corrections"] = df["historique_corrections"].astype(object)
    mask = df["id_soumission"].astype(str) == str(id_soumission)
    if not mask.any():
        raise HTTPException(404, f"Aucune alerte trouvee pour id_soumission={id_soumission} dans ce job")

    import json as _json
    from datetime import datetime, timezone

    for idx in df[mask].index:
        historique_brut = df.at[idx, "historique_corrections"]
        historique = []
        if isinstance(historique_brut, str) and historique_brut.strip():
            try:
                historique = _json.loads(historique_brut)
            except Exception:
                historique = [{"ancien_contenu_non_structure": historique_brut}]
        historique.append({
            "horodatage": datetime.now(timezone.utc).isoformat(),
            "ancien_statut": df.at[idx, "statut_resolution"],
            "nouveau_statut": body.nouveau_statut,
            "commentaire": body.commentaire,
            "modifie_par": client.client_id,
        })
        df.at[idx, "statut_resolution"] = body.nouveau_statut
        df.at[idx, "historique_corrections"] = _json.dumps(historique, ensure_ascii=False)

    df.to_csv(csv_path, index=False)
    return {"statut": "mis_a_jour", "job_id": job_id, "id_soumission": id_soumission, "nouveau_statut": body.nouveau_statut}
