"""Routes generiques de stockage Supabase Storage (upload/download/
suppression), reutilisables par tous les agents. N'existe que si
Supabase est configure -- sinon chaque agent continue d'utiliser le
stockage fichier local existant (app.core.storage), sans regression.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse

from app.core.auth import ClientIdentity, get_current_client
from app.core.storage_backend import (
    FileNotFound,
    FileTooLarge,
    StorageError,
    StorageNotConfigured,
    UnsupportedFileType,
    delete_file,
    get_file_metadata,
    get_signed_download_url,
    upload_file,
)

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload")
async def upload(
    file: UploadFile,
    categorie: str = Form(...),
    job_id: Optional[str] = Form(default=None),
    projet_id: Optional[str] = Form(default=None),
    client: ClientIdentity = Depends(get_current_client),
):
    content = await file.read()
    try:
        result = upload_file(
            client_id=client.client_id, filename=file.filename, content=content,
            categorie=categorie, job_id=job_id, projet_id=projet_id,
        )
    except StorageNotConfigured:
        raise HTTPException(503, "Supabase Storage non configure -- utiliser le stockage local existant.")
    except FileTooLarge as exc:
        raise HTTPException(413, str(exc))
    except UnsupportedFileType as exc:
        raise HTTPException(415, str(exc))
    except StorageError as exc:
        raise HTTPException(502, f"Echec du stockage : {exc}")
    return result


@router.get("/{fichier_id}/metadata")
def metadata(fichier_id: str, client: ClientIdentity = Depends(get_current_client)):
    try:
        return get_file_metadata(client.client_id, fichier_id)
    except StorageNotConfigured:
        raise HTTPException(503, "Supabase Storage non configure.")
    except FileNotFound:
        raise HTTPException(404, "Fichier introuvable ou acces refuse.")


@router.get("/{fichier_id}/download")
def download(fichier_id: str, client: ClientIdentity = Depends(get_current_client)):
    """Redirige vers une URL signee de courte duree (5 minutes) --
    jamais d'URL publique permanente. L'autorisation est verifiee
    AVANT la generation de l'URL (get_signed_download_url appelle
    get_file_metadata en interne).
    """
    try:
        url = get_signed_download_url(client.client_id, fichier_id, expires_in_seconds=300)
    except StorageNotConfigured:
        raise HTTPException(503, "Supabase Storage non configure.")
    except FileNotFound:
        raise HTTPException(404, "Fichier introuvable ou acces refuse.")
    except StorageError as exc:
        raise HTTPException(502, f"Echec de generation de l'URL : {exc}")
    return RedirectResponse(url, status_code=307)


@router.delete("/{fichier_id}")
def remove(fichier_id: str, client: ClientIdentity = Depends(get_current_client)):
    """Suppression LOGIQUE uniquement -- voir storage_backend.delete_file."""
    try:
        delete_file(client.client_id, fichier_id)
    except StorageNotConfigured:
        raise HTTPException(503, "Supabase Storage non configure.")
    except FileNotFound:
        raise HTTPException(404, "Fichier introuvable ou acces refuse.")
    return {"statut": "supprime", "fichier_id": fichier_id}
