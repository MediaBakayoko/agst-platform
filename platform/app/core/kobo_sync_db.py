"""
Persistance de la tracabilite des synchronisations KoboToolbox dans
Supabase (table synchronisations_kobo, migration 0004). Best-effort :
echoue toujours proprement, jamais d'exception remontee a l'appelant,
coherent avec jobs_db.py et storage_backend.py.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("agst_platform.kobo_sync_db")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")


def _get_connection():
    if not SUPABASE_DB_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(SUPABASE_DB_URL, connect_timeout=10)
    except Exception as exc:
        logger.warning("Connexion Supabase (synchronisations_kobo) indisponible : %s", exc)
        return None


def record_sync_attempt(
    client_id: str,
    kobo_project_uid: str,
    statut: str,
    job_id: str | None = None,
    n_recuperees: int | None = None,
    n_nouvelles: int | None = None,
    n_modifiees: int | None = None,
    n_inchangees: int | None = None,
    erreur: str | None = None,
) -> bool:
    """Enregistre une tentative de synchronisation (succes ou echec).
    Ne leve jamais d'exception -- renvoie False si l'ecriture echoue.
    """
    from app.core.jobs_db import is_valid_uuid
    if not is_valid_uuid(client_id):
        return False  # mode developpement -- pas de FK auth.users valide

    conn = _get_connection()
    if conn is None:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into synchronisations_kobo
                        (client_id, kobo_project_uid, job_id, statut,
                         n_soumissions_recuperees, n_soumissions_nouvelles,
                         n_soumissions_modifiees, n_soumissions_inchangees,
                         erreur, terminee_le)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now());
                    """,
                    (client_id, kobo_project_uid, job_id, statut,
                     n_recuperees, n_nouvelles, n_modifiees, n_inchangees, erreur),
                )
        return True
    except Exception as exc:
        logger.info("Persistance synchronisation Kobo ignoree : %s", exc)
        return False
    finally:
        conn.close()
