"""Genere parcelles + rasters foret (reference/recent) de test pour EUDR."""
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

# Emprise raster : 0.02 x 0.02 deg, resolution 0.0002 deg (~100x100 px)
west, north = -4.10, 5.40
res = 0.0002
size = 100
transform = from_origin(west, north, res, res)

rng = np.random.default_rng(42)

# Reference 2020 : foret dense (80% foret) sur toute l'emprise
baseline = (rng.random((size, size)) < 0.8).astype(np.uint8)

# Recent : perte totale dans le coin sud-est (parcelle P_HIGH), perte partielle
# au centre (P_MOD), stable ailleurs (P_NONE)
recent = baseline.copy()
recent[70:100, 70:100] = 0       # perte totale -> alerte elevee pour une parcelle ici
recent[30:45, 30:45] = (rng.random((15, 15)) < 0.4).astype(np.uint8)  # perte partielle -> moderee

profile = {
    "driver": "GTiff", "height": size, "width": size, "count": 1,
    "dtype": "uint8", "crs": "EPSG:4326", "transform": transform, "nodata": 255,
}
with rasterio.open("sample_data/foret_ref_2020.tif", "w", **profile) as dst:
    dst.write(baseline, 1)
with rasterio.open("sample_data/foret_recent.tif", "w", **profile) as dst:
    dst.write(recent, 1)

# Parcelles : une sans perte, une avec perte moderee, une avec perte elevee
def square(cx, cy, half_side):
    return Polygon([(cx-half_side, cy-half_side), (cx+half_side, cy-half_side),
                     (cx+half_side, cy+half_side), (cx-half_side, cy+half_side)])

parcels = gpd.GeoDataFrame(
    [
        {"id_parcelle": "P_NONE", "producteur": "Koffi Jean"},
        {"id_parcelle": "P_MOD", "producteur": "Aka Marie"},
        {"id_parcelle": "P_HIGH", "producteur": "Ouattara Ali"},
    ],
    geometry=[
        square(west + 0.010, north - 0.006, 0.003),   # zone stable (haut, hors zones modifiees)
        square(west + 0.0075, north - 0.0075, 0.0015),  # zone perte moderee (centre, lignes 30-45)
        square(west + 0.017, north - 0.017, 0.0020),   # zone perte totale (coin SE, lignes 70-100)
    ],
    crs="EPSG:4326",
)
parcels.to_file("sample_data/parcelles_eudr_test.gpkg", driver="GPKG")
print("OK - rasters et parcelles EUDR de test generes")
