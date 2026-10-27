"""
Teste reellement la protection contre les ecritures concurrentes sur
le registre d'alertes (filelock). Lance de vrais threads qui appellent
la route PATCH en parallele sur le MEME id_soumission -- sans verrou,
une ecriture pourrait silencieusement perdre l'historique d'une autre.
"""
import io
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PLATFORM_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM_ROOT))

from app.main import app  # noqa: E402

SAMPLE_CSV = """nom_repondant,commune,age
Koffi Jean,San-Pedro,45
Aka Marie,,38
"""


def test_concurrent_alert_updates_do_not_corrupt_or_lose_history():
    """20 threads mettent a jour la MEME alerte en parallele avec des
    commentaires distincts et numerotes. Verifie ensuite que :
    1. le fichier reste un CSV valide et lisible (pas de corruption) ;
    2. le nombre d'entrees d'historique correspond bien au nombre
       d'ecritures reussies (aucune perte silencieuse par ecrasement).
    """
    client = TestClient(app)
    headers = {"X-Client-Id": "client_concurrency_test"}

    files = {"file": ("soumissions.csv", io.BytesIO(SAMPLE_CSV.encode()), "text/csv")}
    resp = client.post(
        "/agents/survey-intelligence/quality-check",
        files=files, headers=headers,
        data={"project_id": "concurrency_test", "required_fields": "nom_repondant,commune",
              "numeric_fields": "", "gps_fields": "", "dedup_key_fields": ""},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    n_threads = 20
    results = [None] * n_threads

    def worker(i):
        r = client.patch(
            f"/agents/survey-intelligence/alertes/{job_id}/1",
            headers=headers,
            json={"nouveau_statut": "a_verifier", "commentaire": f"ecriture_{i}"},
        )
        results[i] = r.status_code

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Chaque requete doit avoir reussi (200) ou avoir ete rejetee
    # proprement (409 = verrou occupe, jamais une corruption silencieuse).
    assert all(code in (200, 409) for code in results), f"codes inattendus : {results}"
    n_success = sum(1 for c in results if c == 200)
    assert n_success >= 1, "au moins une ecriture doit reussir"

    # Le fichier final doit rester un CSV valide et lisible, avec une
    # seule ligne (une seule anomalie generee : champ 'commune'
    # manquant pour Aka Marie).
    import pandas as pd
    download = client.get(f"/jobs/{job_id}/files/registre_alertes.csv", headers=headers)
    assert download.status_code == 200
    df = pd.read_csv(io.BytesIO(download.content))
    assert len(df) == 1  # pas de corruption de structure (lignes dupliquees/perdues)

    # L'historique de la ligne traitee doit contenir EXACTEMENT autant
    # d'entrees que d'ecritures reussies -- aucune perte par ecrasement.
    import json
    row = df[df["id_soumission"].astype(str) == "1"].iloc[0]
    historique = json.loads(row["historique_corrections"])
    assert len(historique) == n_success, (
        f"{len(historique)} entrees d'historique pour {n_success} ecritures reussies "
        "-- perte silencieuse detectee si ces nombres different"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
