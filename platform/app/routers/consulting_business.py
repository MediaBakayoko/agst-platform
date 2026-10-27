"""Routes Consulting & Business : analyse ToR, construction budget,
brouillon de proposition. Aucune route n'envoie/signe/paie quoi que ce
soit automatiquement -- tout reste brouillon pour validation humaine.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile

from app.core.auth import ClientIdentity, get_current_client
from app.core.job_runner import AGENTS_ROOT, run_agent_job
from app.core.storage import new_job_dir
from app.models.schemas import JobCreatedResponse

router = APIRouter(prefix="/agents/consulting-business", tags=["consulting_business"])

CONSULTING_SCRIPTS = AGENTS_ROOT / "consulting_business" / "scripts"

# Categorie Supabase Storage par agent (prefixe de agent_label avant
# le premier point) -- determine la categorie utilisee pour la
# synchronisation best-effort des fichiers de sortie. Toutes les
# categories autorisees par la contrainte CHECK de la table
# `fichiers` (voir migration 0003) sauf celles deja gerees par les
# routes survey_intelligence dediees (matrice_indicateurs/xlsform/
# registre_alertes, branchees directement dans ce router-la).
AGENT_PREFIX_STORAGE_CATEGORY = {
    "consulting_business": "rapport",
    "academy_knowledge": "rapport",
    "data_science_geoai": "rapport",
    "meal": "rapport",  # meal_project_performance utilise le prefixe court "meal."
    # survey_intelligence.* n'est PAS liste ici : ses 3 routes
    # concernees (indicator-matrix, xlsform-build, quality-check)
    # appellent deja sync_job_output_files explicitement avec une
    # categorie precise (matrice_indicateurs/xlsform/registre_alertes)
    # -- eviter un double-upload avec la categorie generique "rapport".
}


def _run_script(script_name: str, agent_label: str, job_dir: Path, client_id: str, job_id: str, cli_args: list[str], scripts_dir: Path = None):
    import subprocess
    import sys
    import time
    script_path = (scripts_dir or CONSULTING_SCRIPTS) / script_name
    start = time.time()
    result = subprocess.run([sys.executable, str(script_path), *cli_args], cwd=str(job_dir),
                             capture_output=True, text=True, timeout=600)
    duree_secondes = round(time.time() - start, 2)
    import json
    meta = {
        "agent": agent_label, "client_id": client_id, "job_id": job_id, "cli_args": cli_args,
        "statut": "termine" if result.returncode == 0 else "erreur",
        "code_retour": result.returncode, "stdout": result.stdout[-5000:], "stderr": result.stderr[-5000:],
        "duree_secondes": duree_secondes,
        "termine_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (job_dir / "job_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ecriture complementaire dans Supabase (table jobs) -- best-effort,
    # ne doit jamais faire echouer le job lui-meme (voir
    # app.core.jobs_db -- memes garanties que job_runner.run_agent_job,
    # cette fonction etant le second point d'entree reellement utilise
    # par 5 des 8 routers d'agents).
    try:
        from app.core.jobs_db import record_job_in_db, is_valid_uuid
        if is_valid_uuid(client_id):
            record_job_in_db(
                job_id=job_id, client_id=client_id, agent=agent_label,
                statut=meta["statut"], cli_args=cli_args,
                code_retour=meta.get("code_retour"), duree_secondes=duree_secondes,
                erreur=meta.get("stderr") if meta["statut"] == "erreur" else None,
            )
    except Exception:
        pass  # jamais bloquant -- deja gere en interne par jobs_db (logs)

    # Synchronisation best-effort vers Supabase Storage -- UNIQUEMENT
    # pour les agents dont le prefixe est dans AGENT_PREFIX_STORAGE_CATEGORY
    # (survey_intelligence.* est delibrement exclu : ses routes font
    # deja leur propre synchronisation ciblee par categorie precise,
    # voir commentaire sur AGENT_PREFIX_STORAGE_CATEGORY).
    prefix = agent_label.split(".", 1)[0]
    categorie = AGENT_PREFIX_STORAGE_CATEGORY.get(prefix)
    if categorie:
        try:
            from app.core.storage_backend import sync_job_output_files
            sync_job_output_files(client_id, job_id, job_dir, categorie=categorie)
        except Exception:
            pass

    return meta


@router.post("/tor-analyze", response_model=JobCreatedResponse)
async def tor_analyze(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    tor_path = job_dir / file.filename
    tor_path.write_bytes(await file.read())
    meta = _run_script(
        "tor_analyzer.py", "consulting_business.tor_analyzer", job_dir, client.client_id, job_id,
        [str(tor_path), "--output-dir", str(job_dir)],
    )
    return JobCreatedResponse(job_id=job_id, agent="consulting_business.tor_analyzer",
                               statut=meta["statut"], message="Analyse ToR terminee, voir /jobs/{job_id}.")


@router.post("/budget-build", response_model=JobCreatedResponse)
async def budget_build(file: UploadFile, client: ClientIdentity = Depends(get_current_client)):
    job_id, job_dir = new_job_dir(client.client_id)
    csv_path = job_dir / file.filename
    csv_path.write_bytes(await file.read())
    meta = _run_script(
        "budget_builder.py", "consulting_business.budget_builder", job_dir, client.client_id, job_id,
        [str(csv_path), "--output-dir", str(job_dir)],
    )
    return JobCreatedResponse(job_id=job_id, agent="consulting_business.budget_builder",
                               statut=meta["statut"],
                               message="Budget construit (brouillon). Tout montant [HYPOTHESE] reste a valider.")


@router.post("/proposal-build", response_model=JobCreatedResponse)
async def proposal_build(
    tor_analysis_json: UploadFile, profile_json: UploadFile,
    client: ClientIdentity = Depends(get_current_client),
):
    job_id, job_dir = new_job_dir(client.client_id)
    tor_path = job_dir / "tor_analysis.json"
    tor_path.write_bytes(await tor_analysis_json.read())
    profile_path = job_dir / "profile.json"
    profile_path.write_bytes(await profile_json.read())
    meta = _run_script(
        "proposal_builder.py", "consulting_business.proposal_builder", job_dir, client.client_id, job_id,
        ["--tor-analysis", str(tor_path), "--profile", str(profile_path), "--output-dir", str(job_dir)],
    )
    return JobCreatedResponse(job_id=job_id, agent="consulting_business.proposal_builder",
                               statut=meta["statut"],
                               message="Brouillon de proposition genere -- validation humaine requise avant envoi.")
