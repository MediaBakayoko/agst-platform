"""
Authentification -- Supabase Auth (JWT) reel.

Mode : verification JWT via JWKS (cles publiques ES256 recuperees
depuis <SUPABASE_URL>/auth/v1/.well-known/jwks.json) -- approche
moderne recommandee par Supabase, ne necessite aucun secret partage
cote serveur pour la verification (contrairement a l'ancien
HS256+SUPABASE_JWT_SECRET, desormais obsolete et non expose par la
CLI de toute facon).

IMPORTANT : en l'absence de SUPABASE_URL configure, l'auth retombe en
mode developpement explicite (en-tete X-Client-Id, marque INSECURE).
Ne jamais deployer cette version en production sans SUPABASE_URL
configure.
"""
from __future__ import annotations

import os
import time

from fastapi import Header, HTTPException, status

SUPABASE_URL = os.getenv("SUPABASE_URL")
DEV_MODE = not SUPABASE_URL

_JWKS_CLIENT = None
_JWKS_CLIENT_URL = None


def _get_jwks_client():
    """Cree (une seule fois, mis en cache par PyJWKClient lui-meme
    avec son propre TTL) le client JWKS pointant vers le projet
    Supabase configure. Recree si SUPABASE_URL a change (utile en
    tests).
    """
    global _JWKS_CLIENT, _JWKS_CLIENT_URL
    jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    if _JWKS_CLIENT is None or _JWKS_CLIENT_URL != jwks_url:
        import jwt  # PyJWT
        _JWKS_CLIENT = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
        _JWKS_CLIENT_URL = jwks_url
    return _JWKS_CLIENT


class ClientIdentity:
    def __init__(self, client_id: str, email: str | None = None):
        self.client_id = client_id
        self.email = email


def get_current_client(
    x_client_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ClientIdentity:
    """Renvoie l'identite du client courant, isolee par client_id.

    - Si SUPABASE_URL est configure : verifie le JWT Supabase passe
      dans Authorization: Bearer <token> via les cles publiques JWKS
      du projet (ES256), en extrait `sub` (uuid utilisateur Supabase
      Auth) comme client_id. Signature ET expiration verifiees --
      jamais un token expire ou mal signe n'est accepte.
    - Sinon (DEV_MODE) : utilise X-Client-Id directement, avec un
      avertissement explicite -- usage developpement uniquement.
    """
    if not DEV_MODE:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Supabase manquant")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            import jwt  # PyJWT
            jwks_client = _get_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        except Exception as exc:
            # Jamais de detail de l'erreur de signature expose au
            # client -- juste "invalide", le detail reste dans les
            # logs serveur pour audit.
            import logging
            logging.getLogger("agst_platform.auth").warning("Token Supabase rejete : %s", exc)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalide ou expire")
        client_id = payload.get("sub")
        email = payload.get("email")
        if not client_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sans identifiant client (sub)")
        return ClientIdentity(client_id=client_id, email=email)

    if not x_client_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Mode developpement : en-tete X-Client-Id requis (SUPABASE_URL non configure)",
        )
    return ClientIdentity(client_id=x_client_id)
