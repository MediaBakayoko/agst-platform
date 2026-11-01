"""
Connecteur Claude (Anthropic) pour les propositions IA des agents
AGST -- utilise UNIQUEMENT pour generer des SUGGESTIONS explicitement
marquees comme telles (jamais substituees a une donnee reelle sans
etiquette), jamais pour inventer silencieusement un fait factuel
(cible chiffree, valeur de reference mesuree, etc.).

Variables d'environnement attendues (platform/.env, jamais commite) :
- ANTHROPIC_API_KEY : cle API personnelle (console.anthropic.com).
  Jamais loggee, jamais transmise au frontend.

Principe de securite applique partout ou ce module est utilise :
chaque element produit par le LLM porte un champ "origine" avec la
valeur "proposition_ia" (jamais confondu avec "detecte_dans_texte"
ou une donnee fournie par l'utilisateur) -- l'appelant doit toujours
distinguer visuellement les deux dans le document final.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

logger = logging.getLogger("survey_intelligence.llm_connector")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 4096


class LLMNotConfiguredError(RuntimeError):
    """Levee tant qu'aucune cle API n'est configuree -- jamais de
    simulation de reponse."""


class LLMAPIError(RuntimeError):
    """Erreur reelle de l'API Anthropic -- message tronque, jamais
    la cle API."""


def is_llm_configured() -> bool:
    return bool(ANTHROPIC_API_KEY) and anthropic is not None


def _redact_error(exc: Exception, api_key: Optional[str] = None) -> str:
    """Masque la cle API dans un message d'erreur. Verifie a la fois
    la cle explicitement passee (celle reellement utilisee par
    l'appel) ET la variable d'environnement globale -- une
    instanciation avec une cle differente de l'environnement ne doit
    jamais fuiter non masquee.
    """
    msg = str(exc)
    for key in (api_key, ANTHROPIC_API_KEY):
        if key and key in msg:
            msg = msg.replace(key, "***")
    return msg[:500]


@dataclass
class LLMSuggestion:
    """Une proposition IA generique -- toujours accompagnee de son
    origine explicite et jamais ecrite directement comme une donnee
    validee."""
    contenu: dict
    origine: str = "proposition_ia"
    modele: str = DEFAULT_MODEL


class ClaudeConnector:
    """Client minimal pour generer des propositions structurees
    (JSON) a partir d'un texte source. Chaque methode leve une
    exception explicite si la cle API est absente -- jamais de
    proposition simulee sans appel reel."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.model = model
        self._client = None

    def _require_ready(self):
        if anthropic is None:
            raise RuntimeError("Le package 'anthropic' n'est pas installe -- pip install anthropic")
        if not self.api_key:
            raise LLMNotConfiguredError(
                "ANTHROPIC_API_KEY non configuree -- aucune proposition IA ne peut etre generee. "
                "Definir la variable dans platform/.env avant d'utiliser cette fonctionnalite."
            )
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)

    def generate_json(self, system_prompt: str, user_content: str, max_tokens: int = MAX_TOKENS) -> dict:
        """Envoie un prompt et exige une reponse JSON structuree.
        Leve LLMAPIError si l'appel echoue ou si la reponse n'est pas
        un JSON valide -- jamais de JSON invente en cas d'echec
        de parsing.
        """
        self._require_ready()
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as exc:
            logger.error("Appel Claude echoue : %s", _redact_error(exc, self.api_key))
            raise LLMAPIError(_redact_error(exc, self.api_key)) from None

        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        text = text.strip()
        # Tolere un bloc de code markdown autour du JSON (frequent
        # meme avec consigne explicite de n'en pas mettre).
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Reponse Claude non-JSON (tronquee) : %s", text[:300])
            raise LLMAPIError(f"Reponse Claude non exploitable (JSON invalide) : {exc}") from None


def get_claude_connector() -> ClaudeConnector:
    """Renvoie un connecteur pret a l'emploi, ou leve une exception
    explicite si non configure -- jamais de connecteur silencieux."""
    if not is_llm_configured():
        raise LLMNotConfiguredError(
            "ANTHROPIC_API_KEY non configuree -- les propositions IA sont desactivees. "
            "Les agents continuent de fonctionner en mode extraction deterministe seule."
        )
    return ClaudeConnector()
