"""
Point d'extension KoboToolbox -- interface pensee pour etre branchee
SANS reecrire le moteur (project_intake, matrix_builder, xlsform_builder/
validator, quality_checks), une fois un compte Kobo + token API
disponibles.

STATUT ACTUEL : NON TESTE, NON FONCTIONNEL. Aucune des methodes
ci-dessous n'a ete executee contre une vraie instance KoboToolbox --
elles documentent l'interface prevue (signature, endpoints cibles,
comportement attendu) pour que l'implementation reelle n'ait qu'a
remplir le corps des fonctions, pas a redefinir l'architecture.

Prerequis reels avant de rendre ce module fonctionnel (voir aussi le
README racine du depot, section "Prerequis KoboToolbox") :
1. Un compte sur kf.kobotoolbox.org (ou un serveur Kobo prive) --
   https://www.kobotoolbox.org/
2. Un token API v2 : Account Settings > API Token, dans le compte Kobo.
3. L'URL de base de l'API (ex: https://kf.kobotoolbox.org/api/v2/)
   -- differente si serveur prive/auto-heberge.
4. Decision de stockage du token cote serveur (jamais dans un prompt
   ni un log) -- voir platform/app/core/auth.py pour le pattern
   d'injection de secret deja utilise (SUPABASE_JWT_SECRET).

Endpoints Kobo API v2 vises (a VERIFIER contre la documentation
officielle au moment de l'implementation reelle -- https://support.kobotoolbox.org/api.html) :
- POST /api/v2/assets/                         -> creer un projet/asset
- PATCH /api/v2/assets/<uid>/                  -> mettre a jour un asset (import XLSForm)
- POST /api/v2/assets/<uid>/deployment/        -> deployer la version active
- GET  /api/v2/assets/<uid>/data/              -> recuperer les soumissions
- GET  /api/v2/assets/<uid>/data/?query=...    -> filtrer (pour synchro incrementale)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class KoboNotConfiguredError(RuntimeError):
    """Levee par toute methode de ce module tant qu'aucun token/URL Kobo
    n'est configure -- ne jamais pretendre a un succes silencieux.
    """


@dataclass
class KoboCredentials:
    base_url: str  # ex: "https://kf.kobotoolbox.org/api/v2/"
    api_token: str  # jamais logge, jamais renvoye dans une reponse API


class KoboConnector:
    """Interface prevue pour le connecteur Kobo reel. Chaque methode
    leve KoboNotConfiguredError tant qu'elle n'est pas implementee
    contre de vrais credentials -- aucune simulation de succes.
    """

    def __init__(self, credentials: Optional[KoboCredentials] = None):
        self.credentials = credentials

    def _require_credentials(self):
        if self.credentials is None:
            raise KoboNotConfiguredError(
                "Aucun credential KoboToolbox configure. Fournir base_url + api_token "
                "(voir README section Prerequis) avant d'appeler cette methode."
            )

    def create_or_update_project(self, xlsform_path: str, project_uid: Optional[str] = None) -> dict:
        """Cree un nouveau projet Kobo (si project_uid est None) ou met
        a jour un projet existant avec le XLSForm fourni. NE DEPLOIE PAS
        automatiquement -- le deploiement est une methode separee
        (deploy_project) necessitant une approbation humaine explicite.
        """
        self._require_credentials()
        raise NotImplementedError("Implementation reelle a faire une fois les credentials Kobo disponibles.")

    def deploy_project(self, project_uid: str, confirmed_by_human: bool = False) -> dict:
        """Deploie la version active du projet. Refuse explicitement si
        confirmed_by_human n'est pas True -- jamais de deploiement
        silencieux d'un formulaire non approuve.
        """
        self._require_credentials()
        if not confirmed_by_human:
            raise PermissionError("Deploiement refuse : approbation humaine explicite requise (confirmed_by_human=True).")
        raise NotImplementedError("Implementation reelle a faire une fois les credentials Kobo disponibles.")

    def fetch_submissions(self, project_uid: str, since_submission_id: Optional[int] = None) -> list[dict]:
        """Recupere les soumissions, avec synchronisation incrementale
        via since_submission_id pour eviter de re-traiter les
        soumissions deja vues (dedoublonnage).
        """
        self._require_credentials()
        raise NotImplementedError("Implementation reelle a faire une fois les credentials Kobo disponibles.")

    def check_connection(self) -> dict:
        """Verifie que les credentials permettent reellement un appel
        API (ex: GET /api/v2/assets/) -- a utiliser avant toute
        operation pour un retour d'erreur clair plutot qu'un echec
        silencieux plus loin dans le pipeline.
        """
        self._require_credentials()
        raise NotImplementedError("Implementation reelle a faire une fois les credentials Kobo disponibles.")
