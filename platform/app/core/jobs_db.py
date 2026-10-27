"""
Persistance des metadonnees de job dans Supabase (table `jobs`,
migration 0002). Complement AU stockage fichier existant -- le
fichier job_meta.json reste la SOURCE DE VERITE pour les resultats
reels des agents (fichiers generes, stdout/stderr) ; cette table
n'ajoute qu'une vue consolidee/interrogeable, cote base, en cas de
perte disque ou pour un futur tableau de bord.

Echoue PROPREMENT et SILENCIEUSEMENT (log warning, jamais d'exception
qui casserait l'execution d'un agent) si SUPABASE_DB_URL est absent --
le mode fichier-seul reste pleinement fonctionnel sans Supabase.
"""
from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger("agst_platform.jobs_db")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

_pool = None


def _get_connection():
    """Connexion directe psycopg2 -- un pool simple suffit pour ce
    volume (ecriture a la fin de chaque job, pas de haute frequence).
    Retourne None si SUPABASE_DB_URL absent ou la connexion echoue --
    appelant doit toujours tolerer un retour None.
    """
    if not SUPABASE_DB_URL:
        return None
    try:
        import psycopg2
        return psycopg2.connect(SUPABASE_DB_URL, connect_timeout=5)
    except Exception as exc:
        logger.warning("Connexion Supabase (table jobs) indisponible -- mode fichier seul maintenu : %s", exc)
        return None


def record_job_in_db(
    job_id: str,
    client_id: str,
    agent: str,
    statut: str,
    cli_args: list[str],
    code_retour: int | None,
    duree_secondes: float,
    erreur: str | None,
) -> bool:
    """Ecrit (upsert) la ligne de job dans Supabase. Ne leve JAMAIS
    d'exception vers l'appelant -- un echec Supabase ne doit jamais
    faire echouer l'execution reelle d'un agent. Renvoie True si
    l'ecriture a reussi, False sinon (deja journalise en interne).

    client_id doit etre un uuid Supabase Auth valide pour s'inserer
    (contrainte FK vers auth.users) -- en mode developpement
    (X-Client-Id arbitraire, pas un vrai uuid Supabase), l'insertion
    echoue proprement et est journalisee en debug, sans impact sur
    le job lui-meme.
    """
    conn = _get_connection()
    if conn is None:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                import json
                cur.execute(
                    """
                    insert into jobs (job_id, client_id, agent, statut, cli_args, code_retour, duree_secondes, erreur, termine_le)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (job_id) do update set
                        statut = excluded.statut,
                        code_retour = excluded.code_retour,
                        duree_secondes = excluded.duree_secondes,
                        erreur = excluded.erreur,
                        termine_le = now();
                    """,
                    (job_id, client_id, agent, statut, json.dumps(cli_args), code_retour, duree_secondes, erreur),
                )
        return True
    except Exception as exc:
        logger.info("Ecriture Supabase (table jobs) non effectuee pour job %s : %s", job_id, exc)
        return False
    finally:
        conn.close()


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
