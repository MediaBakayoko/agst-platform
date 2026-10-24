"""
EUDR & Forest Monitoring — moteur de controle parcelles + analyse de
changement de couverture forestiere.

Regle fondamentale : cet agent ne conclut JAMAIS a une infraction ou une
conformite EUDR. Il produit des alertes (a examiner) et des observations
documentees -- la decision reste humaine.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom

logger = logging.getLogger("eudr_forest_monitoring")

EUDR_REFERENCE_DATE = date(2020, 12, 31)


@dataclass
class ParcelAlert:
    feature_id: object
    niveau_alerte: str  # "aucune" | "faible" | "moderee" | "elevee"
    surface_parcelle_ha: float
    surface_foret_reference_ha: float
    surface_foret_recente_ha: float
    surface_perte_ha: float
    pct_perte: float
    note: str


@dataclass
class GeolocationObservation:
    feature_id: object
    type_observation: str
    severite: str  # "erreur" | "a_verifier"
    description: str


def classify_alert_level(pct_perte: float, seuil_moderee: float, seuil_elevee: float) -> str:
    if pct_perte <= 0:
        return "aucune"
    if pct_perte < seuil_moderee:
        return "faible"
    if pct_perte < seuil_elevee:
        return "moderee"
    return "elevee"


def check_parcel_geolocation(gdf: gpd.GeoDataFrame, id_field: Optional[str] = None) -> list[GeolocationObservation]:
    """Controles de geolocalisation reutilisant la logique geodata_quality
    (geometrie valide, CRS defini, superficie plausible), adaptes au
    contexte EUDR (parcelles agricoles).
    """
    observations = []

    if gdf.crs is None:
        observations.append(GeolocationObservation(
            feature_id="(couche entiere)", type_observation="crs_manquant", severite="erreur",
            description="Aucun CRS defini pour la couche de parcelles -- controle de superficie impossible",
        ))

    for idx, geom in gdf.geometry.items():
        fid = gdf.loc[idx, id_field] if id_field and id_field in gdf.columns else idx
        if geom is None or geom.is_empty:
            observations.append(GeolocationObservation(
                feature_id=fid, type_observation="geometrie_vide", severite="erreur",
                description="Geometrie de parcelle manquante ou vide",
            ))
            continue
        if not geom.is_valid:
            observations.append(GeolocationObservation(
                feature_id=fid, type_observation="geometrie_invalide", severite="erreur",
                description="Geometrie de parcelle topologiquement invalide",
            ))

    if gdf.crs is not None:
        try:
            crs_calc = gdf.estimate_utm_crs()
            work = gdf.to_crs(crs_calc)
            areas_ha = work.geometry.area / 10000.0
            for idx, area_ha in areas_ha.items():
                fid = gdf.loc[idx, id_field] if id_field and id_field in gdf.columns else idx
                if area_ha < 0.01:
                    observations.append(GeolocationObservation(
                        feature_id=fid, type_observation="surface_anormalement_petite", severite="a_verifier",
                        description=f"Surface calculee = {area_ha:.4f} ha (< 0.01 ha)",
                    ))
                elif area_ha > 1000:
                    observations.append(GeolocationObservation(
                        feature_id=fid, type_observation="surface_anormalement_grande", severite="a_verifier",
                        description=f"Surface calculee = {area_ha:.1f} ha (inhabituel pour une parcelle individuelle)",
                    ))
        except Exception as exc:
            logger.warning("Calcul de superficie impossible : %s", exc)

    return observations


def _read_forest_fraction(raster_path: str, geom, geom_crs) -> tuple[float, float]:
    """Lit un raster de couverture forestiere binaire et renvoie
    (surface_foret_ha, surface_totale_pixels_couverts_ha) sur l'emprise
    de la geometrie fournie.
    """
    with rasterio.open(raster_path) as src:
        geom_in_raster_crs = transform_geom(geom_crs, src.crs, geom.__geo_interface__) if str(src.crs) != str(geom_crs) else geom.__geo_interface__
        try:
            mask = geometry_mask([geom_in_raster_crs], out_shape=(src.height, src.width), transform=src.transform, invert=True)
        except Exception as exc:
            logger.warning("Impossible de masquer le raster sur la geometrie : %s", exc)
            return 0.0, 0.0
        data = src.read(1)
        px_area_m2 = abs(src.transform.a * src.transform.e)
        valid = mask & (data != src.nodata if src.nodata is not None else mask)
        forest_px = int(np.sum((data == 1) & mask))
        total_px = int(np.sum(valid))
        forest_ha = forest_px * px_area_m2 / 10000.0
        total_ha = total_px * px_area_m2 / 10000.0
        return forest_ha, total_ha


def analyze_forest_change(
    gdf: gpd.GeoDataFrame,
    forest_baseline_path: str,
    forest_recent_path: str,
    id_field: Optional[str] = None,
    seuil_moderee: float = 5.0,
    seuil_elevee: float = 20.0,
) -> list[ParcelAlert]:
    alerts = []
    for idx, geom in gdf.geometry.items():
        fid = gdf.loc[idx, id_field] if id_field and id_field in gdf.columns else idx
        if geom is None or geom.is_empty or not geom.is_valid:
            logger.warning("Parcelle %s ignoree pour l'analyse forestiere (geometrie invalide/vide)", fid)
            continue

        foret_ref_ha, total_ref_ha = _read_forest_fraction(forest_baseline_path, geom, gdf.crs)
        foret_rec_ha, total_rec_ha = _read_forest_fraction(forest_recent_path, geom, gdf.crs)

        perte_ha = max(foret_ref_ha - foret_rec_ha, 0.0)
        pct_perte = (perte_ha / foret_ref_ha * 100.0) if foret_ref_ha > 0 else 0.0
        niveau = classify_alert_level(pct_perte, seuil_moderee, seuil_elevee)

        note = (
            f"Couverture forestiere reference (31/12/{EUDR_REFERENCE_DATE.year}) : {foret_ref_ha:.3f} ha ; "
            f"couverture recente : {foret_rec_ha:.3f} ha. "
        )
        if foret_ref_ha == 0:
            note += "Aucune couverture forestiere de reference sur cette parcelle -- alerte non applicable."
        else:
            note += f"Perte estimee : {perte_ha:.3f} ha ({pct_perte:.1f}%). A EXAMINER, ne constitue pas une conclusion de conformite."

        alerts.append(ParcelAlert(
            feature_id=fid,
            niveau_alerte=niveau,
            surface_parcelle_ha=round((gdf.loc[[idx]].to_crs(gdf.estimate_utm_crs()).geometry.area.iloc[0] / 10000.0), 4) if gdf.crs else 0.0,
            surface_foret_reference_ha=round(foret_ref_ha, 4),
            surface_foret_recente_ha=round(foret_rec_ha, 4),
            surface_perte_ha=round(perte_ha, 4),
            pct_perte=round(pct_perte, 2),
            note=note,
        ))
    return alerts
