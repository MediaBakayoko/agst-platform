"""
Connecteur KoboToolbox reel (API v2/KPI v2), avec gestion d'erreurs,
pagination, retry, journalisation sans donnees sensibles, suivi de la
derniere synchronisation reussie, et idempotence (pas de duplication
des soumissions deja traitees).

STATUT ACTUEL : implementation reelle, testee contre un serveur HTTP
mock imitant l'API Kobo v2 (tests/test_kobo_connector.py) -- AUCUN
appel n'a ete effectue contre une vraie instance kf.kobotoolbox.org,
faute de compte/token disponibles. Le code HTTP (requetes, pagination,
retry, parsing) est reel et exerce par les tests ; seule la cible
(serveur Kobo reel) n'a pas pu etre verifiee.

Documentation officielle de reference (reverifiee le 2026-10-27 via le
schema OpenAPI de kf.kobotoolbox.org/api/v2/schema/?format=json) :
https://support.kobotoolbox.org/api.html

Endpoints utilises (API v2, verifies contre le schema reel) :
- GET    /api/v2/assets/                    -> lister les projets accessibles
- POST   /api/v2/assets/                    -> creer un projet (asset) vide
- POST   /api/v2/imports/                   -> importer un XLSForm (endpoint dedie, asynchrone,
                                                champs multipart file + destination=<URI asset>)
- GET    /api/v2/imports/<uid>/             -> suivre le statut d'un import en cours
- POST   /api/v2/assets/<uid>/deployment/   -> deployer la version active
- GET    /api/v2/assets/<uid>/data/         -> recuperer les soumissions (paginee)

Securite :
- Le token API est transmis uniquement via le header Authorization,
  jamais logge, jamais renvoye dans un message d'erreur complet
  (les erreurs HTTP sont tronquees avant journalisation).
- Aucune methode ne deploie un formulaire sans confirmed_by_human=True
  explicite.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

logger = logging.getLogger("survey_intelligence.kobo_connector")

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 30
PAGE_SIZE = 100


class KoboNotConfiguredError(RuntimeError):
    """Levee tant qu'aucun token/URL Kobo n'est configure."""


class KoboAPIError(RuntimeError):
    """Erreur HTTP/API Kobo -- message tronque, jamais le token."""


@dataclass
class KoboCredentials:
    base_url: str  # ex: "https://kf.kobotoolbox.org/api/v2/"
    api_token: str  # jamais logge, jamais renvoye dans une reponse


@dataclass
class SyncState:
    """Etat de synchronisation persistant (dernier succes, hash des
    soumissions deja vues pour l'idempotence). Persiste en JSON ici ;
    en production ce serait la table `synchronisations` + `soumissions`
    Supabase (voir platform/supabase/migrations/).
    """
    derniere_sync_reussie: Optional[str] = None
    hashes_soumissions: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception as exc:
            logger.warning("Etat de synchronisation illisible (%s) -- redemarrage a zero", exc)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


def _redact_error(exc: Exception, credentials: Optional[KoboCredentials]) -> str:
    """Tronque le message d'erreur pour ne jamais exposer le token
    meme si l'URL/erreur HTTP le contenait par accident.
    """
    msg = str(exc)
    if credentials and credentials.api_token and credentials.api_token in msg:
        msg = msg.replace(credentials.api_token, "***")
    return msg[:500]


class KoboConnector:
    """Connecteur Kobo reel avec retry/backoff, pagination et
    idempotence. Chaque methode leve KoboNotConfiguredError si aucun
    credential n'est fourni -- jamais de simulation de succes.
    """

    def __init__(self, credentials: Optional[KoboCredentials] = None, session: "requests.Session" = None):
        self.credentials = credentials
        self._session = session or (requests.Session() if requests else None)

    def _require_ready(self):
        if requests is None:
            raise RuntimeError("Le package 'requests' n'est pas installe -- pip install requests")
        if self.credentials is None:
            raise KoboNotConfiguredError(
                "Aucun credential KoboToolbox configure. Fournir base_url + api_token avant d'appeler cette methode."
            )

    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.credentials.api_token}", "Accept": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Execute une requete HTTP avec retry/backoff sur erreurs
        5xx/timeout (pas sur 4xx -- une erreur client ne se resout
        pas en retentant).

        'path' peut etre un chemin relatif ('/assets/') ou une URL
        complete deja fournie par l'API (champ 'next' de pagination) --
        dans ce 2e cas elle est utilisee telle quelle, sans la
        reprefixer avec base_url.
        """
        self._require_ready()
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = self.credentials.base_url.rstrip("/") + "/" + path.lstrip("/")
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.request(method, url, headers=self._headers(), timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
                if resp.status_code >= 500:
                    raise KoboAPIError(f"Erreur serveur Kobo {resp.status_code} sur {method} {path}")
                if resp.status_code >= 400:
                    raise KoboAPIError(f"Erreur client Kobo {resp.status_code} sur {method} {path} : {resp.text[:300]}")
                return resp.json() if resp.content else {}
            except (KoboAPIError, Exception) as exc:
                is_client_error = isinstance(exc, KoboAPIError) and "Erreur client" in str(exc)
                last_exc = exc
                if is_client_error or attempt == MAX_RETRIES:
                    logger.error("Appel Kobo echoue (tentative %d/%d) : %s", attempt, MAX_RETRIES, _redact_error(exc, self.credentials))
                    raise KoboAPIError(_redact_error(exc, self.credentials)) from None
                logger.warning("Appel Kobo echoue (tentative %d/%d), nouvelle tentative dans %ds : %s",
                                attempt, MAX_RETRIES, RETRY_BACKOFF_SECONDS * attempt, _redact_error(exc, self.credentials))
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise KoboAPIError(_redact_error(last_exc, self.credentials))

    def check_connection(self) -> dict:
        """Verifie que les credentials permettent un appel API reel."""
        self._request("GET", "/assets/", params={"limit": 1})
        return {"connecte": True}

    def list_accessible_projects(self) -> list[dict]:
        """Liste les projets (assets) accessibles avec ce token,
        avec pagination reelle (suit 'next' jusqu'a epuisement).
        """
        results = []
        path = "/assets/"
        params = {"limit": PAGE_SIZE}
        while path:
            data = self._request("GET", path, params=params)
            results.extend(data.get("results", []))
            next_url = data.get("next")
            if not next_url:
                break
            path = next_url
            params = None  # l'URL 'next' contient deja les parametres de pagination
        return results

    def create_project(self, name: str) -> dict:
        """Cree un nouveau projet (asset) vide, de type survey."""
        payload = {"name": name, "asset_type": "survey"}
        return self._request("POST", "/assets/", json=payload)

    def import_xlsform(self, project_uid: str, xlsform_path: Path, poll_timeout_s: int = 30) -> dict:
        """Importe un XLSForm dans un projet existant via l'endpoint
        DEDIE POST /imports/ (verifie contre le schema OpenAPI reel de
        kf.kobotoolbox.org le 2026-10-27 -- PAS un PATCH direct sur
        /assets/{uid}/ comme dans une version precedente de ce
        connecteur, qui etait incorrecte).

        Champs reels attendus par /imports/ (multipart/form-data) :
        file (binaire), destination (URI complete de l'asset, pas
        juste son uid). L'import est ASYNCHRONE cote Kobo -- on
        interroge GET /imports/{uid}/ jusqu'a statut terminal
        (complete/error), avec un timeout explicite.
        """
        self._require_ready()
        destination_uri = self.credentials.base_url.rstrip("/") + f"/assets/{project_uid}/"
        with open(xlsform_path, "rb") as f:
            files = {
                "file": (xlsform_path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            }
            data = {"destination": destination_uri}
            url = self.credentials.base_url.rstrip("/") + "/imports/"
            resp = self._session.post(url, headers=self._headers(), files=files, data=data, timeout=REQUEST_TIMEOUT_SECONDS)
            if resp.status_code >= 400:
                raise KoboAPIError(f"Creation de l'import XLSForm echouee ({resp.status_code}) : {resp.text[:300]}")
            import_result = resp.json()

        import_uid = import_result.get("uid")
        if not import_uid:
            raise KoboAPIError("Reponse d'import Kobo sans 'uid' -- impossible de suivre le statut")

        # L'import est asynchrone -- on interroge son statut jusqu'a
        # une issue terminale (complete/error), avec un timeout explicite
        # plutot qu'une attente indefinie.
        deadline = time.time() + poll_timeout_s
        while time.time() < deadline:
            status_result = self._request("GET", f"/imports/{import_uid}/")
            statut = status_result.get("status", "")
            if statut in ("complete", "error"):
                if statut == "error":
                    raise KoboAPIError(f"Import XLSForm termine en erreur cote Kobo : {status_result}")
                return status_result
            time.sleep(1)
        raise KoboAPIError(f"Import XLSForm toujours en cours apres {poll_timeout_s}s -- statut non confirme")

    def deploy_project(self, project_uid: str, confirmed_by_human: bool = False) -> dict:
        """Deploie la version active du projet. Refuse explicitement
        sans approbation humaine -- jamais de deploiement silencieux.
        """
        if not confirmed_by_human:
            raise PermissionError("Deploiement refuse : approbation humaine explicite requise (confirmed_by_human=True).")
        return self._request("POST", f"/assets/{project_uid}/deployment/", json={"active": True})

    def fetch_submissions(self, project_uid: str, start: int = 0) -> list[dict]:
        """Recupere les soumissions avec pagination reelle (start/limit)."""
        results = []
        current_start = start
        while True:
            data = self._request("GET", f"/assets/{project_uid}/data/", params={"start": current_start, "limit": PAGE_SIZE})
            batch = data.get("results", [])
            results.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            current_start += PAGE_SIZE
        return results

    def sync_submissions(self, project_uid: str, state: SyncState, id_field: str = "_id") -> dict:
        """Synchronisation idempotente : recupere toutes les
        soumissions, compare au hash deja connu pour chaque id, et
        classe en nouvelle/modifiee/inchangee -- jamais de duplication
        en traitement, jamais de perte de modification.
        """
        try:
            submissions = self.fetch_submissions(project_uid)
        except Exception as exc:
            return {"statut": "echec", "erreur": _redact_error(exc, self.credentials),
                     "nouvelles": [], "modifiees": [], "inchangees": 0}

        nouvelles, modifiees = [], []
        inchangees = 0
        for sub in submissions:
            sub_id = str(sub.get(id_field))
            sub_hash = hashlib.sha256(json.dumps(sub, sort_keys=True).encode("utf-8")).hexdigest()
            if sub_id not in state.hashes_soumissions:
                nouvelles.append(sub)
            elif state.hashes_soumissions[sub_id] != sub_hash:
                modifiees.append(sub)
            else:
                inchangees += 1
            state.hashes_soumissions[sub_id] = sub_hash

        from datetime import datetime, timezone
        state.derniere_sync_reussie = datetime.now(timezone.utc).isoformat()

        return {
            "statut": "succes",
            "n_total": len(submissions),
            "nouvelles": nouvelles,
            "modifiees": modifiees,
            "inchangees": inchangees,
        }
