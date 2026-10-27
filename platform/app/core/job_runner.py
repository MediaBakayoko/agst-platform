"""
Execution des scripts agents en sous-processus isole. Chaque agent
garde son code et son CLI inchanges -- l'orchestrateur ne fait
qu'appeler le script avec un dossier de travail dedie au job.

Journalisation complete : chaque job (agent, client, parametres,
statut, duree) est enregistre pour audit.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agst_platform.job_runner")

AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "agents"

AGENT_SCRIPTS = {
    "geodata_quality": AGENTS_ROOT / "geodata_quality" / "scripts" / "run_quality_check.py",
    "field2report": AGENTS_ROOT / "field2report" / "scripts" / "run_pipeline.py",
    "eudr_forest_monitoring": AGENTS_ROOT / "eudr_forest_monitoring" / "scripts" / "run_eudr_check.py",
}

# Categorie Supabase Storage par agent -- determine quelle categorie
# (parmi celles autorisees par la contrainte CHECK de la table
# `fichiers`) est utilisee pour la synchronisation best-effort des
# fichiers de sortie. 'rapport' pour les 3 agents geres par
# run_agent_job (rapports XLSX/DOCX/GPKG/PNG).
AGENT_STORAGE_CATEGORY = {
    "geodata_quality": "rapport",
    "field2report": "rapport",
    "eudr_forest_monitoring": "rapport",
}


def run_agent_job(
    agent_name: str,
    job_dir: Path,
    client_id: str,
    job_id: str,
    cli_args: list[str],
) -> dict:
    """Execute le script CLI d'un agent en sous-processus, dans
    job_dir. Ecrit un fichier job_meta.json avec statut/duree/erreurs
    pour audit et consultation ulterieure.
    """
    script_path = AGENT_SCRIPTS.get(agent_name)
    if script_path is None or not script_path.exists():
        raise ValueError(f"Agent inconnu ou script introuvable : {agent_name}")

    meta = {
        "agent": agent_name,
        "client_id": client_id,
        "job_id": job_id,
        "cli_args": cli_args,
        "statut": "en_cours",
        "demarre_le": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta_path = job_dir / "job_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *cli_args],
            cwd=str(job_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )
        meta["statut"] = "termine" if result.returncode == 0 else "erreur"
        meta["code_retour"] = result.returncode
        meta["stdout"] = result.stdout[-5000:]
        meta["stderr"] = result.stderr[-5000:]
    except subprocess.TimeoutExpired:
        meta["statut"] = "timeout"
        meta["erreur"] = "Depassement du delai maximal (600s)"
    except Exception as exc:
        meta["statut"] = "erreur"
        meta["erreur"] = str(exc)

    meta["duree_secondes"] = round(time.time() - start, 2)
    meta["termine_le"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ecriture complementaire dans Supabase (table jobs) -- best-effort,
    # ne doit jamais faire echouer le job lui-meme. Le fichier
    # job_meta.json ci-dessus reste la source de verite.
    try:
        from app.core.jobs_db import record_job_in_db, is_valid_uuid
        if is_valid_uuid(client_id):
            record_job_in_db(
                job_id=job_id, client_id=client_id, agent=agent_name,
                statut=meta["statut"], cli_args=cli_args,
                code_retour=meta.get("code_retour"), duree_secondes=meta["duree_secondes"],
                erreur=meta.get("erreur"),
            )
    except Exception as exc:
        logger.info("Persistance Supabase ignoree pour job %s : %s", job_id, exc)

    # Synchronisation best-effort des fichiers de sortie vers Supabase
    # Storage -- jamais bloquant, le stockage fichier local reste la
    # source de verite dans tous les cas (voir storage_backend.py).
    try:
        from app.core.storage_backend import sync_job_output_files
        sync_job_output_files(
            client_id, job_id, job_dir,
            categorie=AGENT_STORAGE_CATEGORY.get(agent_name, "autre"),
        )
    except Exception as exc:
        logger.info("Synchronisation Storage ignoree pour job %s : %s", job_id, exc)

    logger.info(
        "Job %s (agent=%s, client=%s) termine : statut=%s duree=%.2fs",
        job_id, agent_name, client_id, meta["statut"], meta["duree_secondes"],
    )
    return meta
