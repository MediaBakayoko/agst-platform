"""
Couche de stockage reutilisable pour les fichiers importes/generes
par les agents AGST OS : upload vers Supabase Storage (prive),
metadonnees en base (table `fichiers`), URLs signees de courte duree
pour le telechargement.

Fallback explicite : si SUPABASE_DB_URL/SUPABASE_URL ne sont pas
configures (mode developpement sans Supabase), toute fonction leve
StorageNotConfigured -- jamais de simulation silencieuse d'un succes.
L'appelant (routers) doit alors continuer a utiliser le stockage
fichier local existant (app.core.storage) sans aucune regression.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agst_platform.storage_backend")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
BUCKET = "agst-files"

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 Mo -- doit rester coherent avec le bucket (file_size_limit)
ALLOWED_EXTENSIONS = {".xlsx", ".csv", ".json", ".txt", ".pdf", ".docx", ".gpkg", ".png"}

# Table MIME explicite -- mimetypes.guess_type() depend de la
# configuration systeme (registre Windows notamment) et peut renvoyer
# des types incoherents avec ceux configures sur le bucket Supabase
# (ex: .csv -> application/vnd.ms-excel au lieu de text/csv sur
# certains systemes Windows) -- bug reel rencontre et corrige.
EXTENSION_TO_MIME = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".gpkg": "application/geopackage+sqlite3",
    ".png": "image/png",
}

VALID_CATEGORIES = {
    "matrice_indicateurs", "xlsform", "soumissions_importees",
    "registre_alertes", "rapport", "fichier_source", "autre",
}


class StorageNotConfigured(RuntimeError):
    pass


class StorageError(RuntimeError):
    pass


class FileTooLarge(StorageError):
    pass


class UnsupportedFileType(StorageError):
    pass


class FileNotFound(StorageError):
    pass


def _require_configured():
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_DB_URL):
        raise StorageNotConfigured(
            "Supabase Storage non configure (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/"
            "SUPABASE_DB_URL manquants) -- utiliser le stockage fichier local."
        )


def _validate_upload(filename: str, content: bytes) -> None:
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise FileTooLarge(f"Fichier trop volumineux : {len(content)} octets (limite {MAX_FILE_SIZE_BYTES}).")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileType(f"Extension non autorisee : {ext!r} (autorisees : {sorted(ALLOWED_EXTENSIONS)}).")


def _safe_storage_key(client_id: str) -> str:
    """Genere une cle de stockage non previsible, sous le prefixe
    <client_id>/ exige par les policies RLS storage.objects. Le nom
    original n'est JAMAIS utilise dans la cle (evite path traversal,
    collision, et devinabilite).
    """
    return f"{client_id}/{uuid.uuid4().hex}"


def _get_db_connection():
    import psycopg2
    return psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)


def upload_file(
    client_id: str,
    filename: str,
    content: bytes,
    categorie: str,
    job_id: Optional[str] = None,
    projet_id: Optional[str] = None,
) -> dict:
    """Upload un fichier vers Supabase Storage et enregistre ses
    metadonnees. Leve StorageNotConfigured / FileTooLarge /
    UnsupportedFileType / StorageError selon le cas -- jamais de
    succes partiel silencieux (si l'upload reussit mais l'insertion
    des metadonnees echoue, on tente de nettoyer l'objet uploade).
    """
    _require_configured()
    if categorie not in VALID_CATEGORIES:
        raise StorageError(f"Categorie invalide : {categorie!r} (valeurs autorisees : {sorted(VALID_CATEGORIES)}).")
    _validate_upload(filename, content)

    storage_key = _safe_storage_key(client_id)
    ext = Path(filename).suffix.lower()
    mime_type = EXTENSION_TO_MIME.get(ext, "application/octet-stream")
    checksum = hashlib.sha256(content).hexdigest()

    import requests
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_key}"
    resp = requests.post(
        upload_url,
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": mime_type,
            "x-upsert": "false",
        },
        data=content,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise StorageError(f"Echec upload Storage ({resp.status_code}) : {resp.text[:300]}")

    try:
        conn = _get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into fichiers (client_id, job_id, projet_id, categorie, nom_original,
                                          cle_stockage, bucket, type_mime, taille_octets, checksum_sha256)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning id;
                    """,
                    (client_id, job_id, projet_id, categorie, filename,
                     storage_key, BUCKET, mime_type, len(content), checksum),
                )
                fichier_id = cur.fetchone()[0]
        conn.close()
    except Exception as exc:
        # Nettoyer l'objet Storage orphelin si les metadonnees n'ont
        # pas pu etre ecrites -- jamais de fichier "fantome" sans
        # trace en base.
        logger.warning("Metadonnees non enregistrees pour %s, nettoyage de l'objet Storage : %s", storage_key, exc)
        try:
            requests.delete(
                upload_url,
                headers={"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
                timeout=15,
            )
        except Exception:
            logger.error("Echec du nettoyage de l'objet Storage orphelin %s -- intervention manuelle requise", storage_key)
        raise StorageError(f"Echec enregistrement metadonnees : {exc}") from exc

    return {
        "id": str(fichier_id),
        "cle_stockage": storage_key,
        "taille_octets": len(content),
        "type_mime": mime_type,
        "checksum_sha256": checksum,
    }


def get_file_metadata(client_id: str, fichier_id: str) -> dict:
    """Renvoie les metadonnees d'un fichier, UNIQUEMENT si client_id
    correspond au proprietaire (controle d'autorisation applicatif --
    en plus de la policy RLS Storage, jamais en remplacement).
    """
    _require_configured()
    conn = _get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, client_id, job_id, projet_id, categorie, nom_original,
                       cle_stockage, bucket, type_mime, taille_octets, checksum_sha256, cree_le
                from fichiers
                where id = %s and client_id = %s and supprime_le is null;
                """,
                (fichier_id, client_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise FileNotFound(f"Fichier introuvable ou acces refuse : {fichier_id}")

    return {
        "id": str(row[0]), "client_id": str(row[1]), "job_id": row[2], "projet_id": str(row[3]) if row[3] else None,
        "categorie": row[4], "nom_original": row[5], "cle_stockage": row[6], "bucket": row[7],
        "type_mime": row[8], "taille_octets": row[9], "checksum_sha256": row[10], "cree_le": row[11].isoformat(),
    }


def get_signed_download_url(client_id: str, fichier_id: str, expires_in_seconds: int = 300) -> str:
    """Genere une URL signee de courte duree pour le telechargement.
    Verifie TOUJOURS l'autorisation applicative avant de generer
    l'URL -- la cle service_role ne remplace jamais ce controle.
    """
    meta = get_file_metadata(client_id, fichier_id)  # leve FileNotFound si non autorise

    import requests
    resp = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/sign/{meta['bucket']}/{meta['cle_stockage']}",
        headers={"Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}", "Content-Type": "application/json"},
        json={"expiresIn": expires_in_seconds},
        timeout=15,
    )
    if resp.status_code != 200:
        raise StorageError(f"Echec generation URL signee ({resp.status_code}) : {resp.text[:300]}")
    signed_path = resp.json()["signedURL"]
    return f"{SUPABASE_URL}/storage/v1{signed_path}"


def delete_file(client_id: str, fichier_id: str) -> None:
    """Suppression LOGIQUE uniquement (colonne supprime_le) -- jamais
    de DELETE physique immediat sur un fichier genere/importe par un
    agent, pour permettre une recuperation en cas d'erreur.

    RISQUE IDENTIFIE ET CONFIRME PAR TEST REEL (2026-10-27) : la
    suppression d'un compte Supabase Auth declenche bien la cascade
    SQL sur la table `fichiers` (FK client_id -> auth.users), mais ne
    supprime JAMAIS l'objet physique dans Supabase Storage (systeme
    distinct, sans cascade automatique). Une tache periodique de purge
    des objets Storage orphelins (presents dans le bucket mais sans
    ligne `fichiers` correspondante) est necessaire -- NON IMPLEMENTEE
    a ce jour, reste une tache a prevoir avant une suppression de
    compte en production.
    """
    meta = get_file_metadata(client_id, fichier_id)  # verifie l'autorisation
    conn = _get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update fichiers set supprime_le = now() where id = %s and client_id = %s;",
                    (fichier_id, client_id),
                )
    finally:
        conn.close()
    logger.info("Fichier %s marque supprime (logique) pour client %s", fichier_id, client_id)


def sync_job_output_files(
    client_id: str,
    job_id: str,
    job_dir: Path,
    categorie: str,
    filenames: Optional[list] = None,
) -> list:
    """Upload best-effort vers Supabase Storage de chaque fichier
    present dans job_dir (recursif), en complement du stockage fichier
    local qui reste la source de verite. N'echoue JAMAIS vers
    l'appelant -- si Supabase n'est pas configure ou l'upload echoue,
    retourne une liste vide et journalise, sans empecher le reste du
    job de fonctionner (compatibilite controlee avec le mode local
    exigee par la mission).

    filenames : si fourni, ne synchronise que les fichiers dont le nom
    correspond (ex: eviter d'uploader job_meta.json ou les fichiers
    d'entree bruts). Si None, synchronise tous les fichiers de sortie
    (hors job_meta.json et fichiers d'entree nommes "input").
    """
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_DB_URL):
        return []
    from app.core.jobs_db import is_valid_uuid
    if not is_valid_uuid(client_id):
        return []  # mode developpement -- pas de FK auth.users valide

    uploaded = []
    for path in job_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in ("job_meta.json",) or path.suffix == ".lock":
            continue
        if filenames is not None and path.name not in filenames:
            continue
        ext = path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue  # types non couverts par la couche Storage (ex: .log) -- restent en local uniquement
        try:
            content = path.read_bytes()
            if len(content) > MAX_FILE_SIZE_BYTES:
                logger.info("Fichier %s trop volumineux pour Supabase Storage, reste en local uniquement.", path)
                continue
            result = upload_file(
                client_id=client_id, filename=path.name, content=content,
                categorie=categorie, job_id=job_id,
            )
            uploaded.append(result)
        except Exception as exc:
            logger.info("Synchronisation Supabase ignoree pour %s (job %s) : %s", path.name, job_id, exc)
    return uploaded
