"""
Tests du connecteur Claude (llm_connector.py) et de la logique
d'extraction/proposition de project_intake.py. Les appels reels a
l'API Anthropic sont mockes (unittest.mock) -- ces tests n'exigent
aucune cle API reelle. Un test reel avec appel API effectif a ete
execute manuellement le 2026-11-01 (voir journal de mission) et a
confirme le fonctionnement complet (propositions pertinentes,
justifiees par citation du texte source).
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from llm_connector import (  # noqa: E402
    ClaudeConnector,
    LLMAPIError,
    LLMNotConfiguredError,
    is_llm_configured,
)
from project_intake import extract_elements, propose_missing_elements_with_ia  # noqa: E402


def _fake_anthropic_response(text: str):
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def test_connector_requires_api_key(monkeypatch):
    monkeypatch.setattr("llm_connector.ANTHROPIC_API_KEY", None)
    connector = ClaudeConnector(api_key=None)
    with pytest.raises(LLMNotConfiguredError):
        connector.generate_json("system", "user")


def test_connector_parses_valid_json_response():
    connector = ClaudeConnector(api_key="fake-key-for-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response('{"ok": true}')
    connector._client = fake_client
    result = connector.generate_json("system", "user")
    assert result == {"ok": True}


def test_connector_tolerates_markdown_code_block():
    """Certaines reponses incluent ```json ... ``` malgre la consigne
    explicite -- doit etre tolere, pas rejete."""
    connector = ClaudeConnector(api_key="fake-key-for-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response('```json\n{"ok": true}\n```')
    connector._client = fake_client
    result = connector.generate_json("system", "user")
    assert result == {"ok": True}


def test_connector_raises_explicit_error_on_invalid_json():
    """Une reponse non-JSON ne doit jamais etre silencieusement
    acceptee ou transformee en JSON invente."""
    connector = ClaudeConnector(api_key="fake-key-for-test")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_anthropic_response("ceci n'est pas du JSON")
    connector._client = fake_client
    with pytest.raises(LLMAPIError):
        connector.generate_json("system", "user")


def test_connector_never_logs_api_key_on_error(caplog):
    connector = ClaudeConnector(api_key="SECRET_KEY_12345")
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("erreur contenant SECRET_KEY_12345 dans le message")
    connector._client = fake_client
    with pytest.raises(LLMAPIError) as exc_info:
        connector.generate_json("system", "user")
    assert "SECRET_KEY_12345" not in str(exc_info.value)


def test_propose_missing_elements_only_returns_requested_keys():
    """Le modele ne doit jamais pouvoir injecter une cle hors de la
    liste des elements reellement manquants demandes."""
    fake_connector = MagicMock()
    fake_connector.generate_json.return_value = {
        "propositions": {
            "zone_geographique": {"texte_propose": "...", "confiance": "haute", "justification": "..."},
            "cle_non_demandee_inventee": {"texte_propose": "injection", "confiance": "haute", "justification": "..."},
        }
    }
    with patch("llm_connector.get_claude_connector", return_value=fake_connector):
        result = propose_missing_elements_with_ia("texte source", ["zone_geographique"])
    assert "zone_geographique" in result
    assert "cle_non_demandee_inventee" not in result


def test_propose_missing_elements_propagates_not_configured_error():
    """Si aucune cle API n'est configuree, l'appelant (project_intake.py)
    doit pouvoir distinguer ce cas (mode deterministe seul) d'une
    vraie erreur d'appel."""
    with patch("llm_connector.get_claude_connector", side_effect=LLMNotConfiguredError("non configure")):
        with pytest.raises(LLMNotConfiguredError):
            propose_missing_elements_with_ia("texte", ["zone_geographique"])


def test_extract_elements_never_invents_missing_section():
    """Verifie que la passe 1 (deterministe, inchangee) continue de
    ne jamais inventer un element absent du texte."""
    text = "Contexte: un texte de test sans les autres sections."
    elements = extract_elements(text)
    assert elements["contexte_problematique"] is not None
    assert elements["objectifs_resultats"] is None  # absent du texte, doit rester None
