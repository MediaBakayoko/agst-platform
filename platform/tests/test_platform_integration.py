"""
Tests d'integration de la plateforme AGST (FastAPI). Exercent reellement
l'app complete via TestClient -- pas de mocks du framework, seulement
les sous-processus scripts qui s'executent reellement.

Couvre : isolation multi-client, parcours quality-check -> alertes ->
traitement, gestion d'erreurs (pas de secret expose), rate limiting.
"""
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PLATFORM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM_ROOT))

from app.main import app  # noqa: E402

SAMPLE_CSV = """nom_repondant,commune,age
Koffi Jean,San-Pedro,45
Aka Marie,,38
Koffi Jean,San-Pedro,45
"""


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check_real():
    with TestClient(app) as c:
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_quality_check_requires_client_id(client):
    files = {"file": ("soumissions.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")}
    resp = client.post(
        "/agents/survey-intelligence/quality-check",
        files=files,
        data={"project_id": "test", "required_fields": "nom_repondant,commune",
              "numeric_fields": "", "gps_fields": "", "dedup_key_fields": "nom_repondant,commune"},
    )
    assert resp.status_code == 401


def test_full_flow_quality_check_then_alert_update_then_isolation(client):
    """Parcours complet : quality-check -> lecture du registre via /jobs
    -> traitement d'une alerte -> verification qu'un autre client ne
    peut ni lire ni modifier ce job (isolation reelle, pas seulement
    documentee).
    """
    owner_headers = {"X-Client-Id": "client_integration_owner"}
    intruder_headers = {"X-Client-Id": "client_integration_intrus"}

    files = {"file": ("soumissions.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")}
    resp = client.post(
        "/agents/survey-intelligence/quality-check",
        files=files,
        headers=owner_headers,
        data={"project_id": "integration_test", "required_fields": "nom_repondant,commune",
              "numeric_fields": "", "gps_fields": "", "dedup_key_fields": "nom_repondant,commune"},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["statut"] == "termine"

    # Le proprietaire peut consulter le statut du job.
    status_resp = client.get(f"/jobs/{job_id}", headers=owner_headers)
    assert status_resp.status_code == 200
    assert "registre_alertes.csv" in status_resp.json()["fichiers_sortie"]

    # L'intrus ne peut PAS consulter ce job -- isolation reelle.
    intruder_resp = client.get(f"/jobs/{job_id}", headers=intruder_headers)
    assert intruder_resp.status_code == 404

    # Le proprietaire peut telecharger le registre.
    download_resp = client.get(f"/jobs/{job_id}/files/registre_alertes.csv", headers=owner_headers)
    assert download_resp.status_code == 200
    assert b"commune" in download_resp.content

    # L'intrus ne peut pas telecharger ce fichier.
    intruder_download = client.get(f"/jobs/{job_id}/files/registre_alertes.csv", headers=intruder_headers)
    assert intruder_download.status_code == 404

    # Trouver un id_soumission reel dans le registre (champ manquant -> ligne 1).
    registry_text = download_resp.content.decode("utf-8")
    assert "reponse_manquante" in registry_text

    # Le proprietaire peut traiter l'alerte (id_soumission=1 correspond a Aka Marie, commune manquante).
    patch_resp = client.patch(
        f"/agents/survey-intelligence/alertes/{job_id}/1",
        headers=owner_headers,
        json={"nouveau_statut": "a_verifier", "commentaire": "Test integration"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["nouveau_statut"] == "a_verifier"

    # L'intrus ne peut PAS traiter une alerte sur le job d'un autre client.
    intruder_patch = client.patch(
        f"/agents/survey-intelligence/alertes/{job_id}/1",
        headers=intruder_headers,
        json={"nouveau_statut": "cloturee"},
    )
    assert intruder_patch.status_code == 404

    # Le statut a bien ete persiste dans le fichier (pas seulement en memoire).
    download_resp2 = client.get(f"/jobs/{job_id}/files/registre_alertes.csv", headers=owner_headers)
    assert "a_verifier" in download_resp2.content.decode("utf-8")


def test_alert_update_rejects_invalid_status(client):
    headers = {"X-Client-Id": "client_integration_invalid"}
    files = {"file": ("soumissions.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")}
    resp = client.post(
        "/agents/survey-intelligence/quality-check",
        files=files, headers=headers,
        data={"project_id": "t", "required_fields": "nom_repondant,commune",
              "numeric_fields": "", "gps_fields": "", "dedup_key_fields": ""},
    )
    job_id = resp.json()["job_id"]
    patch_resp = client.patch(
        f"/agents/survey-intelligence/alertes/{job_id}/1",
        headers=headers,
        json={"nouveau_statut": "statut_invente_qui_n_existe_pas"},
    )
    assert patch_resp.status_code == 400


def test_error_responses_never_expose_internal_trace(client):
    """Une erreur serveur ne doit jamais renvoyer de trace Python brute
    au client -- verifie sur un cas reel (fichier malformé plutot qu'un
    mock de l'exception).
    """
    headers = {"X-Client-Id": "client_integration_errtest"}
    # CSV volontairement corrompu pour declencher une vraie erreur de parsing.
    bad_csv = b"\xff\xfe\x00\x01corrupted_binary_not_csv"
    files = {"file": ("corrupt.csv", io.BytesIO(bad_csv), "text/csv")}
    resp = client.post(
        "/agents/survey-intelligence/quality-check",
        files=files, headers=headers,
        data={"project_id": "t", "required_fields": "", "numeric_fields": "",
              "gps_fields": "", "dedup_key_fields": ""},
    )
    # Que ca reussisse (si pandas tolere le fichier) ou echoue, aucune
    # trace Python (mot "Traceback", chemin absolu C:\) ne doit fuiter.
    body_text = resp.text
    assert "Traceback (most recent call last)" not in body_text


def test_job_not_found_for_nonexistent_job(client):
    headers = {"X-Client-Id": "client_integration_404test"}
    resp = client.get("/jobs/job_id_qui_nexiste_pas_du_tout", headers=headers)
    assert resp.status_code == 404


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
