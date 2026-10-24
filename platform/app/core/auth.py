"""
Authentification -- squelette pret pour Supabase Auth (JWT).

IMPORTANT : dans cette version de developpement, en l'absence de
credentials Supabase, l'auth utilise un en-tete de dev
(X-Client-Id) explicitement marque INSECURE. Ne jamais deployer cette
version en production sans remplacer get_current_client par une
verification JWT reelle.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
DEV_MODE = SUPABASE_JWT_SECRET is None


class ClientIdentity:
    def __init__(self, client_id: str, email: str | None = None):
        self.client_id = client_id
        self.email = email


def get_current_client(
    x_client_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> ClientIdentity:
    """Renvoie l'identite du client courant, isolee par client_id.

    - Si SUPABASE_JWT_SECRET est configure : decode et verifie le JWT
      Supabase passe dans Authorization: Bearer <token>, en extrait
      `sub` comme client_id. (A implementer completement lors de la
      connexion reelle a Supabase -- squelette ci-dessous.)
    - Sinon (DEV_MODE) : utilise X-Client-Id directement, avec un
      avertissement explicite -- usage developpement uniquement.
    """
    if not DEV_MODE:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token Supabase manquant")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            import jwt  # PyJWT, a ajouter aux dependances lors de la connexion Supabase
            payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        except Exception as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token invalide : {exc}")
        client_id = payload.get("sub")
        email = payload.get("email")
        if not client_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sans identifiant client (sub)")
        return ClientIdentity(client_id=client_id, email=email)

    if not x_client_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Mode developpement : en-tete X-Client-Id requis (SUPABASE_JWT_SECRET non configure)",
        )
    return ClientIdentity(client_id=x_client_id)
