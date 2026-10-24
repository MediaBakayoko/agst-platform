"""
Isolation du stockage par client. Aucune fonction de ce module
n'accepte un chemin fourni librement par le client -- tout chemin est
construit a partir du client_id authentifie et d'un job_id genere
serveur.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_id(value: str, label: str) -> str:
    if not _SAFE_ID.match(value):
        raise ValueError(f"{label} invalide (caracteres non autorises) : {value!r}")
    return value


def new_job_dir(client_id: str) -> tuple[str, Path]:
    """Cree et renvoie (job_id, chemin) pour un nouveau job, isole sous
    storage/<client_id>/<job_id>/.
    """
    client_id = _validate_id(client_id, "client_id")
    job_id = uuid.uuid4().hex[:16]
    job_dir = STORAGE_ROOT / client_id / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_id, job_dir


def job_dir_for(client_id: str, job_id: str) -> Path:
    """Renvoie le chemin d'un job existant, en verifiant qu'il
    appartient bien au client_id fourni -- jamais d'acces a un job
    d'un autre client.
    """
    client_id = _validate_id(client_id, "client_id")
    job_id = _validate_id(job_id, "job_id")
    path = STORAGE_ROOT / client_id / job_id
    if not path.exists():
        raise FileNotFoundError(f"Job introuvable pour ce client : {job_id}")
    return path


def list_jobs_for(client_id: str) -> list[str]:
    client_id = _validate_id(client_id, "client_id")
    client_dir = STORAGE_ROOT / client_id
    if not client_dir.exists():
        return []
    return sorted(p.name for p in client_dir.iterdir() if p.is_dir())
