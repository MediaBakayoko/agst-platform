"""
Tests du systeme de notifications. Verifie reellement :
- le canal in-app fonctionne sans dependance externe
- le canal email echoue PROPREMENT (jamais de succes simule) sans
  fournisseur configure
- le dispatcher journalise chaque canal independamment (un echec sur
  un canal ne bloque pas les autres)
- aucune donnee personnelle de beneficiaire n'est incluse dans la
  representation securisee
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from notifications import (  # noqa: E402
    EmailNotificationChannel,
    InAppNotificationChannel,
    Notification,
    NotificationDispatcher,
    NotificationProviderNotConfigured,
)


def _sample_notification():
    return Notification(
        projet_id="projet_test",
        id_soumission="42",
        type_probleme="reponse_manquante",
        gravite="erreur_bloquante",
        lien_interface="https://app.example/alertes/job123/42",
    )


def test_in_app_channel_writes_registry_without_external_dependency(tmp_path):
    channel = InAppNotificationChannel(registry_path=tmp_path / "notifications.json")
    result = channel.send(_sample_notification())
    assert result.statut == "envoye"
    assert result.canal == "in_app"

    entries = json.loads((tmp_path / "notifications.json").read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["projet_id"] == "projet_test"


def test_in_app_channel_accumulates_multiple_notifications(tmp_path):
    channel = InAppNotificationChannel(registry_path=tmp_path / "notifications.json")
    channel.send(_sample_notification())
    channel.send(_sample_notification())
    entries = json.loads((tmp_path / "notifications.json").read_text(encoding="utf-8"))
    assert len(entries) == 2


def test_email_channel_fails_explicitly_without_provider():
    """Jamais de succes simule -- le canal email doit renvoyer un
    statut 'non_disponible' explicite tant qu'aucun fournisseur n'est
    configure.
    """
    channel = EmailNotificationChannel(provider_config=None)
    result = channel.send(_sample_notification())
    assert result.statut == "non_disponible"
    assert result.erreur is not None


def test_email_channel_with_unfinished_provider_raises_not_simulated():
    """Meme si un provider_config est fourni, l'implementation reelle
    d'envoi n'existe pas encore -- doit lever une exception explicite,
    jamais un succes.
    """
    channel = EmailNotificationChannel(provider_config={"nom": "provider_hypothetique"})
    with pytest.raises(NotificationProviderNotConfigured):
        channel.send(_sample_notification())


def test_dispatcher_reports_each_channel_independently(tmp_path):
    """Un canal qui echoue ne doit pas empecher le dispatcher de
    tenter et de rapporter les autres canaux.
    """
    in_app = InAppNotificationChannel(registry_path=tmp_path / "notif.json")
    email = EmailNotificationChannel(provider_config=None)
    dispatcher = NotificationDispatcher(channels={"in_app": in_app, "email": email})

    results = dispatcher.dispatch(_sample_notification())
    statuts = {r.canal: r.statut for r in results}
    assert statuts["in_app"] == "envoye"
    assert statuts["email"] == "non_disponible"


def test_notification_safe_dict_never_contains_beneficiary_name():
    """La representation 'safe' ne doit jamais contenir de champ
    permettant d'identifier un beneficiaire -- seulement des
    identifiants techniques.
    """
    notif = _sample_notification()
    safe = notif.to_safe_dict()
    assert "nom_repondant" not in safe
    assert "destinataire" not in safe  # exclu volontairement de la representation securisee
    assert set(safe.keys()) == {"projet_id", "id_soumission", "type_probleme", "gravite", "lien_interface"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
