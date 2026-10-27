"""
Abstraction des canaux de notification. Un seul canal est reellement
implemente (dans l'application -- le registre d'alertes consultable,
sans dependance externe). Le canal email est un POINT D'EXTENSION
explicite qui echoue proprement (NotificationProviderNotConfigured)
tant qu'aucun fournisseur n'est choisi -- jamais de simulation d'envoi
reussi.

Contrat commun : chaque notification porte projet, reference technique
de soumission (jamais le nom du repondant), type de probleme, gravite,
lien securise -- jamais de donnee personnelle de beneficiaire en clair.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("survey_intelligence.notifications")


class NotificationProviderNotConfigured(RuntimeError):
    """Levee par tout canal necessitant un fournisseur externe non
    configure -- jamais de succes simule.
    """


@dataclass
class Notification:
    projet_id: str
    id_soumission: str
    type_probleme: str
    gravite: str
    lien_interface: str
    destinataire: Optional[str] = None

    def to_safe_dict(self) -> dict:
        """Representation sans donnee personnelle de beneficiaire --
        c'est la seule forme autorisee a etre journalisee ou envoyee.
        """
        return {
            "projet_id": self.projet_id,
            "id_soumission": self.id_soumission,
            "type_probleme": self.type_probleme,
            "gravite": self.gravite,
            "lien_interface": self.lien_interface,
        }


@dataclass
class NotificationResult:
    canal: str
    statut: str  # "envoye" | "echec" | "non_disponible"
    erreur: Optional[str] = None
    horodatage: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InAppNotificationChannel:
    """Canal reellement fonctionnel, sans dependance externe : ecrit
    la notification dans un registre fichier consultable (meme
    principe que registre_alertes -- en attendant Supabase, qui
    remplacera ce fichier par une table 'notifications').
    """

    def __init__(self, registry_path: Path):
        self.registry_path = registry_path

    def send(self, notification: Notification) -> NotificationResult:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        if self.registry_path.exists():
            try:
                entries = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Registre de notifications illisible (%s) -- redemarre a zero", exc)
        entries.append(notification.to_safe_dict() | {"horodatage": datetime.now(timezone.utc).isoformat()})
        self.registry_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        return NotificationResult(canal="in_app", statut="envoye")


class EmailNotificationChannel:
    """POINT D'EXTENSION -- aucun fournisseur SMTP/API configure.
    Toute tentative d'envoi echoue explicitement tant qu'un
    fournisseur reel n'est pas branche (variable d'environnement
    EMAIL_PROVIDER + credentials associes, jamais en dur).
    """

    def __init__(self, provider_config: Optional[dict] = None):
        self.provider_config = provider_config

    def send(self, notification: Notification) -> NotificationResult:
        if not self.provider_config:
            logger.warning(
                "Notification email NON envoyee (projet=%s, soumission=%s) -- "
                "aucun fournisseur email configure (EMAIL_PROVIDER absent)",
                notification.projet_id, notification.id_soumission,
            )
            return NotificationResult(
                canal="email", statut="non_disponible",
                erreur="Aucun fournisseur email configure -- voir docs/notifications_prerequis.md",
            )
        # Implementation reelle a faire une fois le fournisseur choisi
        # (ex: Resend, SendGrid) -- ne jamais simuler un envoi reussi
        # ici en attendant.
        raise NotificationProviderNotConfigured(
            "provider_config fourni mais aucune implementation reelle n'existe encore -- "
            "a completer lors du choix effectif du fournisseur."
        )


class NotificationDispatcher:
    """Envoie une notification sur tous les canaux configures,
    journalise le resultat de CHACUN (succes/echec) -- n'echoue jamais
    silencieusement sur un canal indisponible, et ne bloque pas les
    autres canaux si l'un echoue.
    """

    def __init__(self, channels: dict):
        self.channels = channels

    def dispatch(self, notification: Notification, retry_failed: bool = False) -> list[NotificationResult]:
        results = []
        for name, channel in self.channels.items():
            try:
                result = channel.send(notification)
            except NotificationProviderNotConfigured as exc:
                result = NotificationResult(canal=name, statut="non_disponible", erreur=str(exc))
            except Exception as exc:
                result = NotificationResult(canal=name, statut="echec", erreur=str(exc))
            results.append(result)
            logger.info("Notification canal=%s statut=%s", name, result.statut)
        return results
