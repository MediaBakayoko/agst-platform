"""
Tests du connecteur KoboToolbox contre un serveur HTTP mock (bibliotheque
`responses`) qui imite l'API Kobo v2. Exerce reellement la logique HTTP
(pagination, retry, parsing, idempotence) -- AUCUN appel n'est fait
contre une vraie instance Kobo (pas de compte disponible). C'est le
maximum testable sans credentials reels.
"""
import sys
from pathlib import Path

import pytest
import responses

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from kobo_connector import (  # noqa: E402
    KoboAPIError,
    KoboConnector,
    KoboCredentials,
    KoboNotConfiguredError,
    SyncState,
)

BASE_URL = "https://kf.kobotoolbox.test/api/v2/"


def _creds():
    return KoboCredentials(base_url=BASE_URL, api_token="FAKE_TOKEN_FOR_TEST")


def test_methods_raise_without_credentials():
    connector = KoboConnector(credentials=None)
    with pytest.raises(KoboNotConfiguredError):
        connector.check_connection()


@responses.activate
def test_check_connection_success():
    responses.add(responses.GET, BASE_URL + "assets/", json={"results": [], "next": None}, status=200)
    connector = KoboConnector(credentials=_creds())
    result = connector.check_connection()
    assert result["connecte"] is True


@responses.activate
def test_check_connection_never_logs_token(caplog):
    """Un echec de connexion ne doit jamais exposer le token dans le
    message d'erreur leve.
    """
    responses.add(responses.GET, BASE_URL + "assets/", status=401, json={"detail": "Invalid token"})
    connector = KoboConnector(credentials=_creds())
    with pytest.raises(KoboAPIError) as exc_info:
        connector.check_connection()
    assert "FAKE_TOKEN_FOR_TEST" not in str(exc_info.value)


@responses.activate
def test_list_accessible_projects_follows_pagination():
    responses.add(responses.GET, BASE_URL + "assets/",
                   json={"results": [{"uid": "a1"}], "next": BASE_URL + "assets/?offset=1"}, status=200)
    responses.add(responses.GET, BASE_URL + "assets/?offset=1",
                   json={"results": [{"uid": "a2"}], "next": None}, status=200)
    connector = KoboConnector(credentials=_creds())
    projects = connector.list_accessible_projects()
    assert [p["uid"] for p in projects] == ["a1", "a2"]


@responses.activate
def test_deploy_project_refuses_without_human_confirmation():
    connector = KoboConnector(credentials=_creds())
    with pytest.raises(PermissionError):
        connector.deploy_project("asset123", confirmed_by_human=False)
    # Aucune requete HTTP ne doit avoir ete emise.
    assert len(responses.calls) == 0


@responses.activate
def test_deploy_project_succeeds_with_confirmation():
    responses.add(responses.POST, BASE_URL + "assets/asset123/deployment/", json={"active": True}, status=200)
    connector = KoboConnector(credentials=_creds())
    result = connector.deploy_project("asset123", confirmed_by_human=True)
    assert result["active"] is True


@responses.activate
def test_retry_on_server_error_then_success():
    """Une erreur 503 doit declencher un retry ; la 2e tentative qui
    reussit doit renvoyer le resultat normalement.
    """
    responses.add(responses.GET, BASE_URL + "assets/", status=503)
    responses.add(responses.GET, BASE_URL + "assets/", json={"results": [], "next": None}, status=200)
    connector = KoboConnector(credentials=_creds())
    result = connector.check_connection()
    assert result["connecte"] is True
    assert len(responses.calls) == 2


@responses.activate
def test_no_retry_on_client_error():
    """Une erreur 404 (client) ne doit PAS declencher de retry --
    inutile de retenter une ressource inexistante.
    """
    responses.add(responses.GET, BASE_URL + "assets/", status=404, json={"detail": "Not found"})
    connector = KoboConnector(credentials=_creds())
    with pytest.raises(KoboAPIError):
        connector.check_connection()
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_submissions_pagination():
    responses.add(responses.GET, BASE_URL + "assets/proj1/data/",
                   json={"results": [{"_id": i} for i in range(100)]}, status=200)
    responses.add(responses.GET, BASE_URL + "assets/proj1/data/",
                   json={"results": [{"_id": 100}]}, status=200)
    connector = KoboConnector(credentials=_creds())
    subs = connector.fetch_submissions("proj1")
    assert len(subs) == 101


@responses.activate
def test_sync_submissions_is_idempotent_no_duplicates():
    """Synchroniser deux fois la meme liste de soumissions ne doit
    produire aucune 'nouvelle' soumission a la 2e passe -- coeur de
    l'exigence d'idempotence de la mission.
    """
    submissions = [{"_id": 1, "val": "a"}, {"_id": 2, "val": "b"}]
    responses.add(responses.GET, BASE_URL + "assets/proj1/data/", json={"results": submissions}, status=200)
    connector = KoboConnector(credentials=_creds())
    state = SyncState()

    result1 = connector.sync_submissions("proj1", state)
    assert len(result1["nouvelles"]) == 2
    assert len(result1["modifiees"]) == 0

    responses.add(responses.GET, BASE_URL + "assets/proj1/data/", json={"results": submissions}, status=200)
    result2 = connector.sync_submissions("proj1", state)
    assert len(result2["nouvelles"]) == 0
    assert result2["inchangees"] == 2


@responses.activate
def test_sync_submissions_detects_modification_not_duplication():
    submissions_v1 = [{"_id": 1, "val": "a"}]
    responses.add(responses.GET, BASE_URL + "assets/proj1/data/", json={"results": submissions_v1}, status=200)
    connector = KoboConnector(credentials=_creds())
    state = SyncState()
    connector.sync_submissions("proj1", state)

    submissions_v2 = [{"_id": 1, "val": "a_modifie"}]
    responses.add(responses.GET, BASE_URL + "assets/proj1/data/", json={"results": submissions_v2}, status=200)
    result2 = connector.sync_submissions("proj1", state)
    assert len(result2["modifiees"]) == 1
    assert len(result2["nouvelles"]) == 0


def test_sync_state_persists_and_reloads(tmp_path):
    state_path = tmp_path / "sync_state.json"
    state = SyncState(hashes_soumissions={"1": "abc"})
    state.save(state_path)

    reloaded = SyncState.load(state_path)
    assert reloaded.hashes_soumissions == {"1": "abc"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
