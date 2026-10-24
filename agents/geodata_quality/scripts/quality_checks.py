"""
GeoData Quality — moteur de controle qualite geospatial.

Regles non negociables :
  - ne jamais modifier le fichier source
  - ne jamais corriger/supprimer automatiquement une entite
  - toujours distinguer "erreur" (certaine) de "a_verifier" (anomalie a examiner)
  - toujours verifier le CRS avant un calcul de surface/distance

Usage programmatique :
    from quality_checks import run_quality_checks
    result = run_quality_checks(
        input_path="data.gpkg",
        required_fields=["nom", "surface_ha"],
        area_field="surface_ha",
        area_tolerance_pct=20,
        dup_tolerance_m=0,
    )
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger("geodata_quality")


# --------------------------------------------------------------------------
# CRS helpers
# --------------------------------------------------------------------------

def pick_projected_crs(gdf: gpd.GeoDataFrame) -> Optional[str]:
    """Renvoie un CRS projete (metres) adapte a l'etendue du GeoDataFrame,
    pour des calculs de surface/distance fiables. Ne modifie jamais le
    GeoDataFrame d'origine — a utiliser uniquement sur une copie
    temporaire pour le calcul.
    """
    if gdf.empty or gdf.crs is None:
        return None
    try:
        # geopandas >= 0.12 : estimate_utm_crs() choisit la zone UTM adaptee
        return gdf.estimate_utm_crs()
    except Exception as exc:  # pragma: no cover - fallback defensif
        logger.warning("estimate_utm_crs a echoue (%s) ; calcul en CRS d'origine", exc)
        return None


# --------------------------------------------------------------------------
# Resultat structure
# --------------------------------------------------------------------------

@dataclass
class Anomaly:
    feature_id: object
    type_anomalie: str
    severite: str  # "erreur" | "a_verifier"
    description: str
    champ_concerne: Optional[str] = None
    valeur: Optional[str] = None


@dataclass
class QualityCheckResult:
    input_path: str
    n_features: int
    crs_origine: Optional[str]
    crs_calcul: Optional[str]
    params: dict
    anomalies: list = field(default_factory=list)
    anomaly_feature_ids: set = field(default_factory=set)
    started_at: str = ""
    finished_at: str = ""

    def to_dataframe(self) -> pd.DataFrame:
        if not self.anomalies:
            return pd.DataFrame(columns=[
                "feature_id", "type_anomalie", "severite", "description",
                "champ_concerne", "valeur",
            ])
        return pd.DataFrame([a.__dict__ for a in self.anomalies])

    def summary_by_type(self) -> pd.DataFrame:
        df = self.to_dataframe()
        if df.empty:
            return pd.DataFrame(columns=["type_anomalie", "severite", "nombre"])
        return (
            df.groupby(["type_anomalie", "severite"])
            .size()
            .reset_index(name="nombre")
            .sort_values(["severite", "nombre"], ascending=[True, False])
        )


# --------------------------------------------------------------------------
# Controles individuels
# --------------------------------------------------------------------------

def check_geometry_validity(gdf: gpd.GeoDataFrame) -> list[Anomaly]:
    anomalies = []
    for idx, geom in gdf.geometry.items():
        fid = gdf.loc[idx].get("_feature_id", idx)
        if geom is None or geom.is_empty:
            anomalies.append(Anomaly(
                feature_id=fid, type_anomalie="geometrie_vide", severite="erreur",
                description="Geometrie manquante ou vide",
            ))
            continue
        if not geom.is_valid:
            anomalies.append(Anomaly(
                feature_id=fid, type_anomalie="geometrie_invalide", severite="erreur",
                description="Geometrie topologiquement invalide (auto-intersection, etc.)",
            ))
    return anomalies


def check_missing_crs(gdf: gpd.GeoDataFrame) -> list[Anomaly]:
    if gdf.crs is None:
        return [Anomaly(
            feature_id="(couche entiere)", type_anomalie="crs_manquant", severite="erreur",
            description="Aucun systeme de coordonnees (CRS) defini pour cette couche",
        )]
    return []


def check_duplicate_geometries(gdf: gpd.GeoDataFrame, tolerance_m: float = 0) -> list[Anomaly]:
    """Detecte les geometries identiques ou quasi-identiques (dans une
    tolerance en metres, calculee en CRS projete si possible).
    """
    anomalies = []
    if gdf.empty:
        return anomalies

    work = gdf.copy()
    crs_calc = pick_projected_crs(gdf) if tolerance_m > 0 else None
    if crs_calc is not None:
        work = work.to_crs(crs_calc)

    # Cle de comparaison : WKB normalise si tolerance 0, sinon buffer+hash
    seen: dict = {}
    for idx, geom in work.geometry.items():
        fid = gdf.loc[idx].get("_feature_id", idx)
        if geom is None or geom.is_empty:
            continue
        if tolerance_m > 0:
            key = geom.buffer(tolerance_m / 2).wkb_hex
        else:
            key = geom.normalize().wkb_hex
        if key in seen:
            anomalies.append(Anomaly(
                feature_id=fid, type_anomalie="doublon_geometrique", severite="a_verifier",
                description=f"Geometrie identique (tolerance {tolerance_m} m) a l'entite {seen[key]!r}",
            ))
        else:
            seen[key] = fid
    return anomalies


def check_duplicate_attributes(gdf: gpd.GeoDataFrame, key_fields: list[str]) -> list[Anomaly]:
    anomalies = []
    missing = [f for f in key_fields if f not in gdf.columns]
    if missing:
        anomalies.append(Anomaly(
            feature_id="(couche entiere)", type_anomalie="champ_cle_absent", severite="erreur",
            description=f"Champs cles demandes absents de la couche : {missing}",
        ))
        key_fields = [f for f in key_fields if f not in missing]
    if not key_fields:
        return anomalies

    dup_mask = gdf.duplicated(subset=key_fields, keep=False)
    for idx in gdf[dup_mask].index:
        fid = gdf.loc[idx].get("_feature_id", idx)
        anomalies.append(Anomaly(
            feature_id=fid, type_anomalie="doublon_attributaire", severite="a_verifier",
            description=f"Valeurs dupliquees sur les champs {key_fields}",
            champ_concerne=",".join(key_fields),
        ))
    return anomalies


def check_overlaps(gdf: gpd.GeoDataFrame) -> list[Anomaly]:
    """Detecte les paires de polygones qui se chevauchent (intersection
    d'aire non nulle). Signale, ne juge jamais si c'est normal ou pas.
    """
    anomalies = []
    polys = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    if len(polys) < 2:
        return anomalies

    sindex = polys.sindex
    reported_pairs = set()
    for idx, geom in polys.geometry.items():
        if geom is None or geom.is_empty or not geom.is_valid:
            continue
        candidates = list(sindex.intersection(geom.bounds))
        for cand_pos in candidates:
            cand_idx = polys.index[cand_pos]
            if cand_idx == idx:
                continue
            pair = tuple(sorted((idx, cand_idx)))
            if pair in reported_pairs:
                continue
            other = polys.geometry.loc[cand_idx]
            if other is None or other.is_empty or not other.is_valid:
                continue
            inter = geom.intersection(other)
            if not inter.is_empty and inter.area > 0:
                reported_pairs.add(pair)
                fid_a = gdf.loc[idx].get("_feature_id", idx)
                fid_b = gdf.loc[cand_idx].get("_feature_id", cand_idx)
                anomalies.append(Anomaly(
                    feature_id=fid_a, type_anomalie="chevauchement", severite="a_verifier",
                    description=f"Chevauche l'entite {fid_b!r} (aire d'intersection: {inter.area:.2f} unites CRS^2)",
                ))
    return anomalies


def check_required_fields(gdf: gpd.GeoDataFrame, required_fields: list[str]) -> list[Anomaly]:
    anomalies = []
    for fld in required_fields:
        if fld not in gdf.columns:
            anomalies.append(Anomaly(
                feature_id="(couche entiere)", type_anomalie="champ_obligatoire_absent",
                severite="erreur", description=f"Champ obligatoire absent de la couche: {fld}",
                champ_concerne=fld,
            ))
            continue
        null_mask = gdf[fld].isna() | (gdf[fld].astype(str).str.strip() == "")
        for idx in gdf[null_mask].index:
            fid = gdf.loc[idx].get("_feature_id", idx)
            anomalies.append(Anomaly(
                feature_id=fid, type_anomalie="champ_obligatoire_vide", severite="erreur",
                description=f"Champ obligatoire vide: {fld}", champ_concerne=fld,
            ))
    return anomalies


def check_area_anomalies(
    gdf: gpd.GeoDataFrame,
    area_field: Optional[str] = None,
    area_tolerance_pct: float = 20.0,
    min_area_m2: float = 1.0,
) -> tuple[list[Anomaly], Optional[str]]:
    """Calcule la surface SIG reelle (en CRS projete) et la compare au
    champ de surface declaree s'il est fourni. Renvoie aussi le CRS
    utilise pour le calcul (pour le journal/rapport).
    """
    anomalies: list[Anomaly] = []
    polys = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    if polys.empty:
        return anomalies, None

    crs_calc = pick_projected_crs(gdf)
    if crs_calc is None:
        anomalies.append(Anomaly(
            feature_id="(couche entiere)", type_anomalie="calcul_surface_impossible",
            severite="erreur",
            description="CRS absent ou non reprojetable : calcul de surface non fiable, ignore",
        ))
        return anomalies, None

    work = polys.to_crs(crs_calc)
    areas_m2 = work.geometry.area

    for idx, area_m2 in areas_m2.items():
        fid = gdf.loc[idx].get("_feature_id", idx)
        if area_m2 < min_area_m2:
            anomalies.append(Anomaly(
                feature_id=fid, type_anomalie="surface_anormalement_petite",
                severite="a_verifier",
                description=f"Surface SIG calculee = {area_m2:.2f} m2 (< seuil {min_area_m2} m2)",
            ))
        if area_field and area_field in gdf.columns:
            declared = gdf.loc[idx, area_field]
            if pd.isna(declared):
                continue
            try:
                declared_m2 = float(declared) * 10000.0  # hypothese : champ en hectares
            except (TypeError, ValueError):
                continue
            if declared_m2 <= 0:
                continue
            diff_pct = abs(area_m2 - declared_m2) / declared_m2 * 100.0
            if diff_pct > area_tolerance_pct:
                anomalies.append(Anomaly(
                    feature_id=fid, type_anomalie="ecart_surface_declaree_vs_sig",
                    severite="a_verifier",
                    description=(
                        f"Surface declaree ({area_field})={declared} ha "
                        f"({declared_m2:.0f} m2) vs surface SIG={area_m2:.0f} m2 "
                        f"-> ecart {diff_pct:.1f}% (seuil {area_tolerance_pct}%)"
                    ),
                    champ_concerne=area_field,
                    valeur=str(declared),
                ))
    return anomalies, str(crs_calc)


def check_field_type_consistency(gdf: gpd.GeoDataFrame, numeric_fields: list[str]) -> list[Anomaly]:
    anomalies = []
    for fld in numeric_fields:
        if fld not in gdf.columns:
            continue
        for idx, val in gdf[fld].items():
            if pd.isna(val):
                continue
            try:
                float(val)
            except (TypeError, ValueError):
                fid = gdf.loc[idx].get("_feature_id", idx)
                anomalies.append(Anomaly(
                    feature_id=fid, type_anomalie="type_incoherent", severite="erreur",
                    description=f"Valeur non numerique dans un champ attendu numerique: {val!r}",
                    champ_concerne=fld, valeur=str(val),
                ))
    return anomalies


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run_quality_checks(
    input_path: str,
    required_fields: Optional[list[str]] = None,
    numeric_fields: Optional[list[str]] = None,
    key_fields_for_dedup: Optional[list[str]] = None,
    area_field: Optional[str] = None,
    area_tolerance_pct: float = 20.0,
    dup_tolerance_m: float = 0.0,
    layer: Optional[str] = None,
    id_field: Optional[str] = None,
) -> QualityCheckResult:
    """Execute l'ensemble des controles qualite sur un fichier geospatial.

    Ne modifie jamais `input_path`. Renvoie un QualityCheckResult complet
    pret a etre exporte (Excel, GeoPackage d'anomalies, journal).
    """
    started_at = datetime.utcnow().isoformat() + "Z"
    required_fields = required_fields or []
    numeric_fields = numeric_fields or []
    key_fields_for_dedup = key_fields_for_dedup or []

    logger.info("Lecture de %s (layer=%s)", input_path, layer)
    gdf = gpd.read_file(input_path, layer=layer) if layer else gpd.read_file(input_path)
    n_features = len(gdf)
    crs_origine = str(gdf.crs) if gdf.crs else None

    # Identifiant stable pour le rapport : champ fourni, sinon index positionnel
    if id_field and id_field in gdf.columns:
        gdf["_feature_id"] = gdf[id_field]
    else:
        gdf["_feature_id"] = gdf.index

    anomalies: list[Anomaly] = []
    anomalies += check_missing_crs(gdf)
    anomalies += check_geometry_validity(gdf)
    anomalies += check_required_fields(gdf, required_fields)
    anomalies += check_field_type_consistency(gdf, numeric_fields)
    if key_fields_for_dedup:
        anomalies += check_duplicate_attributes(gdf, key_fields_for_dedup)
    anomalies += check_duplicate_geometries(gdf, tolerance_m=dup_tolerance_m)
    anomalies += check_overlaps(gdf)

    area_anomalies, crs_calcul = check_area_anomalies(
        gdf, area_field=area_field, area_tolerance_pct=area_tolerance_pct,
    )
    anomalies += area_anomalies

    anomaly_ids = {a.feature_id for a in anomalies if a.feature_id != "(couche entiere)"}

    result = QualityCheckResult(
        input_path=str(input_path),
        n_features=n_features,
        crs_origine=crs_origine,
        crs_calcul=crs_calcul,
        params={
            "required_fields": required_fields,
            "numeric_fields": numeric_fields,
            "key_fields_for_dedup": key_fields_for_dedup,
            "area_field": area_field,
            "area_tolerance_pct": area_tolerance_pct,
            "dup_tolerance_m": dup_tolerance_m,
            "layer": layer,
            "id_field": id_field,
        },
        anomalies=anomalies,
        anomaly_feature_ids=anomaly_ids,
        started_at=started_at,
        finished_at=datetime.utcnow().isoformat() + "Z",
    )
    result._gdf = gdf  # attache pour l'export GeoPackage (prive, non serialise)
    return result
