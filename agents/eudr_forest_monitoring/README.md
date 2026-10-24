# EUDR & Forest Monitoring Agent

Contrôle des parcelles agricoles (géolocalisation, cohérence) et analyse
de changement de couverture forestière, pour appuyer la traçabilité et
la diligence raisonnée liée à l'**EUDR** (Règlement européen sur la
déforestation). Priorité filières cacao et hévéa, Côte d'Ivoire / Afrique
de l'Ouest.

## Principe fondamental (non négociable)

**Cet agent ne conclut jamais seul à une infraction ou à une conformité
EUDR.** Il produit des *alertes* et des *observations documentées* ;
la décision de conformité reste un acte humain d'expert, après examen.
Toute sortie distingue explicitement :
- **alerte** (changement détecté, à examiner) — jamais "infraction confirmée"
- **observation** (donnée géographique cohérente ou non) — jamais "conforme"/"non conforme"

## Ce que l'agent fait

1. **Contrôle de géolocalisation des parcelles** — réutilise les
   contrôles `geodata_quality` (géométrie valide, CRS, doublons,
   superficie plausible) appliqués aux polygones/points de parcelles
   fournis par les producteurs/coopératives.
2. **Analyse de changement de couverture forestière** — compare une
   couverture forestière de référence (date de référence réglementaire :
   **31/12/2020**) à une couverture plus récente, sur l'emprise de
   chaque parcelle. Calcule la surface de perte de couverture par
   parcelle.
3. **Hiérarchisation des alertes** — classe chaque parcelle par niveau
   d'alerte (aucune / faible / modérée / élevée) selon le % de perte de
   couverture sur son emprise, **jamais** par un seuil binaire
   conforme/non-conforme.
4. **Rapport et cartes** — Excel (inventaire parcelles + alertes) et
   carte des alertes (PNG, + GeoPackage si besoin SIG), avec sources et
   dates des observations toujours citées.

## Entrées attendues

- Couche des parcelles (GeoPackage/Shapefile/GeoJSON), avec identifiant
  producteur/parcelle.
- Deux rasters de couverture forestière binaire (0=non-forêt, 1=forêt),
  même emprise/résolution/CRS : un à la date de référence, un plus
  récent. (Dans un contexte réel : dérivés de Sentinel-2/Landsat/Hansen
  Global Forest Change via Google Earth Engine — non inclus ici, voir
  `docs/extension_gee.md` pour le point d'intégration.)

## Usage

```bash
python scripts/run_eudr_check.py \
    --parcels sample_data/parcelles_eudr_test.gpkg \
    --forest-baseline sample_data/foret_ref_2020.tif \
    --forest-recent sample_data/foret_recent.tif \
    --output-dir output/ \
    --id-field id_parcelle \
    --alert-threshold-moderate-pct 5 \
    --alert-threshold-high-pct 20
```

## Limites assumées

- Les rasters de couverture forestière doivent être fournis par
  l'utilisateur ou un pipeline GEE séparé — ce module ne télécharge pas
  lui-même d'imagerie satellite dans cette version.
- Une perte de couverture détectée peut avoir des causes multiples
  (déforestation, erreur de classification, nuage résiduel, agroforesterie
  avec couvert variable) — **c'est pourquoi l'agent qualifie toujours
  "alerte à examiner", jamais "déforestation confirmée".**
