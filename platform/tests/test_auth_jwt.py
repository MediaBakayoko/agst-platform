"""
Teste reellement la logique de verification JWT de auth.py, SANS
creer de vrai compte Supabase : genere une paire de cles ES256 de
test, simule un JWKS local via unittest.mock, et verifie que
get_current_client() accepte un token valide signe avec la cle privee
correspondante, et rejette un token expire ou mal signe.
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import auth as auth_module  # noqa: E402


def _generate_test_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key


def _make_token(private_key, sub="user-test-123", email="test@example.com", expired=False):
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "aud": "authenticated",
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test-kid"})


class FakeSigningKey:
    def __init__(self, key):
        self.key = key


def test_valid_token_is_accepted(monkeypatch):
    private_key = _generate_test_keypair()
    public_key = private_key.public_key()
    token = _make_token(private_key)

    monkeypatch.setattr(auth_module, "SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setattr(auth_module, "DEV_MODE", False)

    with patch.object(auth_module, "_get_jwks_client") as mock_jwks:
        mock_client = mock_jwks.return_value
        mock_client.get_signing_key_from_jwt.return_value = FakeSigningKey(public_key)

        identity = auth_module.get_current_client(
            x_client_id=None, authorization=f"Bearer {token}"
        )
    assert identity.client_id == "user-test-123"
    assert identity.email == "test@example.com"


def test_expired_token_is_rejected(monkeypatch):
    private_key = _generate_test_keypair()
    public_key = private_key.public_key()
    token = _make_token(private_key, expired=True)

    monkeypatch.setattr(auth_module, "SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setattr(auth_module, "DEV_MODE", False)

    with patch.object(auth_module, "_get_jwks_client") as mock_jwks:
        mock_client = mock_jwks.return_value
        mock_client.get_signing_key_from_jwt.return_value = FakeSigningKey(public_key)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_module.get_current_client(x_client_id=None, authorization=f"Bearer {token}")
        assert exc_info.value.status_code == 401


def test_token_signed_with_wrong_key_is_rejected(monkeypatch):
    """Simule un attaquant signant avec une AUTRE cle privee -- doit
    etre rejete car la cle publique ne correspond pas.
    """
    attacker_key = _generate_test_keypair()
    real_private_key = _generate_test_keypair()
    real_public_key = real_private_key.public_key()

    forged_token = _make_token(attacker_key)

    monkeypatch.setattr(auth_module, "SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setattr(auth_module, "DEV_MODE", False)

    with patch.object(auth_module, "_get_jwks_client") as mock_jwks:
        mock_client = mock_jwks.return_value
        mock_client.get_signing_key_from_jwt.return_value = FakeSigningKey(real_public_key)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_module.get_current_client(x_client_id=None, authorization=f"Bearer {forged_token}")
        assert exc_info.value.status_code == 401


def test_dev_mode_still_works_without_supabase_url(monkeypatch):
    monkeypatch.setattr(auth_module, "SUPABASE_URL", None)
    monkeypatch.setattr(auth_module, "DEV_MODE", True)

    identity = auth_module.get_current_client(x_client_id="client_dev_test", authorization=None)
    assert identity.client_id == "client_dev_test"


def test_missing_authorization_header_rejected_in_prod_mode(monkeypatch):
    monkeypatch.setattr(auth_module, "SUPABASE_URL", "https://fake-project.supabase.co")
    monkeypatch.setattr(auth_module, "DEV_MODE", False)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        auth_module.get_current_client(x_client_id=None, authorization=None)
    assert exc_info.value.status_code == 401


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
