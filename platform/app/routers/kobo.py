"""Routes KoboToolbox -- EXCLUSIVEMENT en lecture pour cette phase
(connexion, liste des projets accessibles, metadonnees d'un
formulaire, soumissions). Aucune route de deploiement/modification/
suppression n'est exposee ici -- voir kobo_connector.py pour le code
(deploy_project exige deja confirmed_by_human=True), non branche sur
une route HTTP par prudence tant qu'aucun test reel n'a ete effectue.

Le token KOBO_API_TOKEN est lu uniquement cote serveur
(app.core.kobo_config) -- jamais transmis au frontend, jamais logge.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import ClientIdentity, get_current_client
from app.core.kobo_config import get_kobo_connector, is_kobo_configured

router = APIRouter(prefix="/agents/kobo", tags=["kobo"])


def _require_kobo(client: ClientIdentity) -> None:
    if not is_kobo_configured():
        raise HTTPException(
            503,
            "KoboToolbox non configure (KOBO_BASE_URL/KOBO_API_TOKEN absents cote serveur). "
            "Aucun appel reel n'a ete effectue -- voir supabase/README.md section KoboToolbox "
            "pour la procedure de configuration.",
        )


@router.get("/connection-check")
def connection_check(client: ClientIdentity = Depends(get_current_client)):
    """Verifie que les credentials Kobo configures cote serveur
    permettent un appel API reel. N'expose jamais le token."""
    _require_kobo(client)
    try:
        connector = get_kobo_connector()
        result = connector.check_connection()
        return {"configure": True, "connecte": result["connecte"]}
    except Exception as exc:
        # Le message d'erreur est deja tronque/redige par
        # kobo_connector.py (_redact_error) -- jamais le token.
        raise HTTPException(502, f"Connexion Kobo echouee : {exc}")


@router.get("/projects")
def list_projects(client: ClientIdentity = Depends(get_current_client)):
    """Liste les projets (assets) Kobo accessibles avec le token
    configure -- ne filtre PAS par client_id cote Kobo (le token
    determine deja quels projets sont visibles cote Kobo lui-meme)."""
    _require_kobo(client)
    try:
        connector = get_kobo_connector()
        projects = connector.list_accessible_projects()
        return {"n_projets": len(projects), "projets": projects}
    except Exception as exc:
        raise HTTPException(502, f"Liste des projets Kobo echouee : {exc}")


@router.get("/projects/{project_uid}/metadata")
def project_metadata(project_uid: str, client: ClientIdentity = Depends(get_current_client)):
    """Metadonnees d'un formulaire de test -- recherche dans la liste
    des projets accessibles plutot qu'un appel direct, pour ne jamais
    exposer un projet auquel le token n'a normalement pas acces."""
    _require_kobo(client)
    try:
        connector = get_kobo_connector()
        projects = connector.list_accessible_projects()
    except Exception as exc:
        raise HTTPException(502, f"Lecture des projets Kobo echouee : {exc}")
    match = next((p for p in projects if p.get("uid") == project_uid), None)
    if match is None:
        raise HTTPException(404, "Projet Kobo introuvable ou non accessible avec ce token.")
    return match


@router.get("/projects/{project_uid}/submissions")
def project_submissions(project_uid: str, client: ClientIdentity = Depends(get_current_client)):
    """Soumissions d'un projet Kobo -- lecture seule, pagination
    reelle suivie en interne par le connecteur. Journalise la
    tentative dans synchronisations_kobo (best-effort)."""
    _require_kobo(client)
    try:
        connector = get_kobo_connector()
        submissions = connector.fetch_submissions(project_uid)
    except Exception as exc:
        from app.core.kobo_sync_db import record_sync_attempt
        record_sync_attempt(client.client_id, project_uid, statut="echec", erreur=str(exc)[:500])
        raise HTTPException(502, f"Lecture des soumissions Kobo echouee : {exc}")

    from app.core.kobo_sync_db import record_sync_attempt
    record_sync_attempt(client.client_id, project_uid, statut="succes", n_recuperees=len(submissions))
    return {"n_soumissions": len(submissions), "soumissions": submissions}


@router.post("/projects/{project_uid}/quality-check")
def kobo_submissions_quality_check(
    project_uid: str,
    required_fields: str = "",
    numeric_fields: str = "",
    gps_fields: str = "",
    dedup_key_fields: str = "",
    client: ClientIdentity = Depends(get_current_client),
):
    """Enchaine recuperation des soumissions Kobo -> conversion CSV ->
    MEME script de controle qualite que l'upload manuel
    (survey_quality_checks.py, reutilise sans duplication) -> job
    standard, consultable via /jobs/{job_id} comme tout autre job.

    Lecture seule cote Kobo (aucune modification). Les soumissions
    recuperees sont ecrites dans le job_dir local (source de verite)
    puis synchronisees vers Supabase Storage par le mecanisme
    best-effort deja existant (meme route que pour un CSV uploade
    manuellement -- aucune duplication de logique).
    """
    _require_kobo(client)
    try:
        connector = get_kobo_connector()
        submissions = connector.fetch_submissions(project_uid)
    except Exception as exc:
        from app.core.kobo_sync_db import record_sync_attempt
        record_sync_attempt(client.client_id, project_uid, statut="echec", erreur=str(exc)[:500])
        raise HTTPException(502, f"Lecture des soumissions Kobo echouee : {exc}")

    if not submissions:
        raise HTTPException(404, "Aucune soumission recuperee pour ce projet Kobo.")

    import pandas as pd
    from app.core.storage import new_job_dir
    from app.routers.consulting_business import _run_script
    from app.core.job_runner import AGENTS_ROOT

    job_id, job_dir = new_job_dir(client.client_id)
    df = pd.json_normalize(submissions)
    csv_path = job_dir / "soumissions_kobo.csv"
    df.to_csv(csv_path, index=False)

    SI_SCRIPTS = AGENTS_ROOT / "survey_intelligence" / "scripts"
    cli_args = [
        str(csv_path), "--project-id", project_uid,
        "--required-fields", required_fields, "--numeric-fields", numeric_fields,
        "--gps-fields", gps_fields, "--dedup-key-fields", dedup_key_fields,
        "--output-dir", str(job_dir),
    ]
    meta = _run_script(
        "survey_quality_checks.py", "survey_intelligence.survey_quality_checks",
        job_dir, client.client_id, job_id, cli_args, scripts_dir=SI_SCRIPTS,
    )

    # Synchronisation best-effort vers Supabase Storage -- categorie
    # "soumissions_importees" pour la donnee source Kobo, "rapport"
    # pour le registre d'alertes resultant (fichiers nommes
    # explicitement pour eviter tout melange de categorie).
    try:
        from app.core.storage_backend import sync_job_output_files
        sync_job_output_files(client.client_id, job_id, job_dir, categorie="soumissions_importees",
                               filenames=["soumissions_kobo.csv"])
        sync_job_output_files(client.client_id, job_id, job_dir, categorie="registre_alertes",
                               filenames=["registre_alertes.csv", "registre_alertes.xlsx"])
    except Exception:
        pass

    from app.core.kobo_sync_db import record_sync_attempt
    record_sync_attempt(
        client.client_id, project_uid, statut="succes" if meta["statut"] == "termine" else "echec",
        job_id=job_id, n_recuperees=len(submissions),
    )

    return {
        "job_id": job_id, "agent": "survey_intelligence.survey_quality_checks",
        "statut": meta["statut"], "n_soumissions_traitees": len(submissions),
        "message": "Soumissions Kobo recuperees et controle qualite execute, voir /jobs/{job_id}.",
    }
