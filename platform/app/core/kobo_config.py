"""
Configuration KoboToolbox lue depuis les variables d'environnement
cote backend uniquement -- jamais depuis le frontend, jamais dans un
log, jamais demande dans la conversation.

Variables attendues (platform/.env, jamais committe) :
- KOBO_BASE_URL : URL de base de l'API v2 (ex:
  "https://kf.kobotoolbox.org/api/v2/" pour le serveur Global, ou
  "https://eu.kobotoolbox.org/api/v2/" pour le serveur Europe --
  choisir celui correspondant au compte reel de l'organisation. Les
  anciennes routes KPI v1 ont ete supprimees en 2026
  (https://support.kobotoolbox.org/migrating_api.html) -- ce module
  et kobo_connector.py n'utilisent QUE l'API v2.
- KOBO_API_TOKEN : jeton API personnel (Account Settings > Security >
  API Token sur l'instance Kobo concernee). Jamais logge.

Si l'une des deux variables est absente, is_kobo_configured() renvoie
False -- toute route appelante doit alors repondre explicitement
"non configure", jamais simuler un succes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

AGENTS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "agents"
KOBO_SCRIPTS_DIR = AGENTS_ROOT / "survey_intelligence" / "scripts"
if str(KOBO_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(KOBO_SCRIPTS_DIR))

from kobo_connector import KoboConnector, KoboCredentials  # noqa: E402

KOBO_BASE_URL = os.getenv("KOBO_BASE_URL")
KOBO_API_TOKEN = os.getenv("KOBO_API_TOKEN")


def is_kobo_configured() -> bool:
    return bool(KOBO_BASE_URL and KOBO_API_TOKEN)


def get_kobo_connector() -> KoboConnector:
    """Renvoie un connecteur pret a l'emploi, ou leve RuntimeError
    explicitement si KOBO_BASE_URL/KOBO_API_TOKEN sont absents --
    jamais de connecteur silencieusement non fonctionnel.
    """
    if not is_kobo_configured():
        raise RuntimeError(
            "KoboToolbox non configure -- KOBO_BASE_URL et KOBO_API_TOKEN "
            "doivent etre definis dans platform/.env (jamais dans le "
            "frontend ni dans un log)."
        )
    return KoboConnector(credentials=KoboCredentials(base_url=KOBO_BASE_URL, api_token=KOBO_API_TOKEN))
