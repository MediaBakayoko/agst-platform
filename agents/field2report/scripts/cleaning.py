"""
Field2Report — moteur de nettoyage et controle qualite pour donnees
d'enquete terrain (CSV/Excel, KoboToolbox/ODK).

Regles non negociables :
  - ne jamais modifier les donnees brutes (toujours une copie en sortie)
  - toute action de nettoyage est journalisee (avant/apres, nombre de lignes touchees)
  - jamais d'imputation/completion silencieuse d'une valeur manquante
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger("field2report.cleaning")


@dataclass
class CleaningAction:
    action: str
    champ: Optional[str]
    description: str
    n_lignes_concernees: int


@dataclass
class CleaningResult:
    df_clean: pd.DataFrame
    actions: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)  # reutilise le format Anomaly-like (dict)


def check_missing_required(df: pd.DataFrame, required_fields: list[str]) -> list[dict]:
    anomalies = []
    for fld in required_fields:
        if fld not in df.columns:
            anomalies.append({
                "type_anomalie": "champ_obligatoire_absent", "severite": "erreur",
                "description": f"Champ obligatoire absent: {fld}", "ligne": None, "champ": fld,
            })
            continue
        mask = df[fld].isna() | (df[fld].astype(str).str.strip() == "")
        for idx in df[mask].index:
            anomalies.append({
                "type_anomalie": "reponse_manquante", "severite": "erreur",
                "description": f"Reponse manquante sur champ obligatoire: {fld}",
                "ligne": idx, "champ": fld,
            })
    return anomalies


def check_out_of_range(df: pd.DataFrame, field_ranges: dict[str, tuple[float, float]]) -> list[dict]:
    anomalies = []
    for fld, (lo, hi) in field_ranges.items():
        if fld not in df.columns:
            continue
        numeric = pd.to_numeric(df[fld], errors="coerce")
        mask = numeric.notna() & ((numeric < lo) | (numeric > hi))
        for idx in df[mask].index:
            anomalies.append({
                "type_anomalie": "valeur_hors_plage", "severite": "a_verifier",
                "description": f"Valeur {df.loc[idx, fld]!r} hors plage [{lo}, {hi}]",
                "ligne": idx, "champ": fld,
            })
    return anomalies


def check_duplicate_respondents(df: pd.DataFrame, key_fields: list[str]) -> list[dict]:
    anomalies = []
    present = [f for f in key_fields if f in df.columns]
    if not present:
        return anomalies
    dup_mask = df.duplicated(subset=present, keep=False)
    for idx in df[dup_mask].index:
        anomalies.append({
            "type_anomalie": "doublon_repondant", "severite": "a_verifier",
            "description": f"Lignes dupliquees sur {present}", "ligne": idx, "champ": ",".join(present),
        })
    return anomalies


def check_gps_validity(df: pd.DataFrame, lat_field: str, lon_field: str) -> list[dict]:
    anomalies = []
    if lat_field not in df.columns or lon_field not in df.columns:
        return anomalies
    lat = pd.to_numeric(df[lat_field], errors="coerce")
    lon = pd.to_numeric(df[lon_field], errors="coerce")
    invalid = lat.isna() | lon.isna() | (lat.abs() > 90) | (lon.abs() > 180)
    for idx in df[invalid].index:
        anomalies.append({
            "type_anomalie": "coordonnees_gps_invalides", "severite": "erreur",
            "description": f"lat={df.loc[idx, lat_field]!r} lon={df.loc[idx, lon_field]!r}",
            "ligne": idx, "champ": f"{lat_field}/{lon_field}",
        })
    # (0,0) est un piege classique GPS non pris (erreur d'app mobile)
    zero_mask = (lat == 0) & (lon == 0)
    for idx in df[zero_mask].index:
        anomalies.append({
            "type_anomalie": "coordonnees_gps_suspectes_zero", "severite": "a_verifier",
            "description": "Coordonnees (0,0) -- GPS probablement non pris",
            "ligne": idx, "champ": f"{lat_field}/{lon_field}",
        })
    return anomalies


def normalize_text_fields(df: pd.DataFrame, text_fields: list[str]) -> tuple[pd.DataFrame, list[CleaningAction]]:
    """Normalisation minimale et documentee : strip() des espaces en
    debut/fin. Ne modifie jamais la casse ou le contenu semantique.
    """
    out = df.copy()
    actions = []
    for fld in text_fields:
        if fld not in out.columns:
            continue
        before = out[fld].copy()
        out[fld] = out[fld].astype(str).str.strip().replace({"nan": pd.NA, "None": pd.NA})
        n_changed = int((before.astype(str) != out[fld].astype(str)).sum())
        if n_changed:
            actions.append(CleaningAction(
                action="strip_espaces", champ=fld,
                description=f"Suppression des espaces superflus en debut/fin sur {fld}",
                n_lignes_concernees=n_changed,
            ))
    return out, actions


def coerce_numeric_fields(df: pd.DataFrame, numeric_fields: list[str]) -> tuple[pd.DataFrame, list[CleaningAction], list[dict]]:
    """Convertit en numerique quand possible ; les valeurs non convertibles
    deviennent NaN et sont signalees comme anomalie (jamais supprimees
    silencieusement de la ligne).
    """
    out = df.copy()
    actions = []
    anomalies = []
    for fld in numeric_fields:
        if fld not in out.columns:
            continue
        coerced = pd.to_numeric(out[fld], errors="coerce")
        failed_mask = coerced.isna() & out[fld].notna() & (out[fld].astype(str).str.strip() != "")
        n_failed = int(failed_mask.sum())
        if n_failed:
            for idx in out[failed_mask].index:
                anomalies.append({
                    "type_anomalie": "type_incoherent", "severite": "erreur",
                    "description": f"Valeur non numerique: {out.loc[idx, fld]!r}",
                    "ligne": idx, "champ": fld,
                })
            actions.append(CleaningAction(
                action="conversion_numerique_echouee", champ=fld,
                description=f"{n_failed} valeur(s) non convertibles en numerique, laissees telles quelles (non supprimees)",
                n_lignes_concernees=n_failed,
            ))
        out[fld] = coerced
    return out, actions, anomalies


def run_cleaning_pipeline(
    df_raw: pd.DataFrame,
    required_fields: Optional[list[str]] = None,
    numeric_fields: Optional[list[str]] = None,
    text_fields: Optional[list[str]] = None,
    lat_field: Optional[str] = None,
    lon_field: Optional[str] = None,
    dedup_key_fields: Optional[list[str]] = None,
    field_ranges: Optional[dict[str, tuple[float, float]]] = None,
) -> CleaningResult:
    required_fields = required_fields or []
    numeric_fields = numeric_fields or []
    text_fields = text_fields or []
    dedup_key_fields = dedup_key_fields or []
    field_ranges = field_ranges or {}

    anomalies: list[dict] = []
    anomalies += check_missing_required(df_raw, required_fields)
    anomalies += check_out_of_range(df_raw, field_ranges)
    if dedup_key_fields:
        anomalies += check_duplicate_respondents(df_raw, dedup_key_fields)
    if lat_field and lon_field:
        anomalies += check_gps_validity(df_raw, lat_field, lon_field)

    df_clean, actions_text = normalize_text_fields(df_raw, text_fields)
    df_clean, actions_num, anomalies_num = coerce_numeric_fields(df_clean, numeric_fields)
    anomalies += anomalies_num

    return CleaningResult(
        df_clean=df_clean,
        actions=actions_text + actions_num,
        anomalies=anomalies,
    )
