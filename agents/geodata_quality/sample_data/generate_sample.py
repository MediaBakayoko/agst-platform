"""
Genere un jeu de donnees de test avec anomalies volontaires, pour
valider le moteur geodata_quality. Usage ponctuel, pas partie du moteur
lui-meme.
"""
import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

# Zone fictive pres d'Abidjan (EPSG:4326)
polys = []
rows = []

def square(cx, cy, half_side_deg):
    return Polygon([
        (cx - half_side_deg, cy - half_side_deg),
        (cx + half_side_deg, cy - half_side_deg),
        (cx + half_side_deg, cy + half_side_deg),
        (cx - half_side_deg, cy + half_side_deg),
    ])

# 1. Parcelle normale, surface coherente (~1 ha)
polys.append(square(-4.000, 5.300, 0.00045))
rows.append({"id_parcelle": "P001", "producteur": "Koffi Jean", "surface_ha": 1.0})

# 2. Parcelle normale
polys.append(square(-4.010, 5.310, 0.00064))
rows.append({"id_parcelle": "P002", "producteur": "Aka Marie", "surface_ha": 2.0})

# 3. Doublon geometrique exact de P001
polys.append(square(-4.000, 5.300, 0.00045))
rows.append({"id_parcelle": "P003", "producteur": "Koffi Jean", "surface_ha": 1.0})

# 4. Champ obligatoire (producteur) vide
polys.append(square(-4.020, 5.320, 0.00050))
rows.append({"id_parcelle": "P004", "producteur": None, "surface_ha": 1.2})

# 5. Ecart fort entre surface declaree et surface SIG reelle (declare 5ha, reel ~1.2ha)
polys.append(square(-4.030, 5.330, 0.00050))
rows.append({"id_parcelle": "P005", "producteur": "Ouattara Ali", "surface_ha": 5.0})

# 6. Geometrie invalide (polygone auto-intersectant, "papillon")
bowtie = Polygon([(-4.050, 5.340), (-4.048, 5.342), (-4.050, 5.342), (-4.048, 5.340)])
polys.append(bowtie)
rows.append({"id_parcelle": "P006", "producteur": "Bamba Fatou", "surface_ha": 0.8})

# 7. Chevauchement partiel avec P002
polys.append(square(-4.0085, 5.3085, 0.00064))
rows.append({"id_parcelle": "P007", "producteur": "Diallo Seydou", "surface_ha": 2.1})

# 8. Type incoherent dans surface_ha (texte au lieu de nombre)
polys.append(square(-4.060, 5.350, 0.00045))
rows.append({"id_parcelle": "P008", "producteur": "Traore Awa", "surface_ha": "non renseigne"})

gdf = gpd.GeoDataFrame(rows, geometry=polys, crs="EPSG:4326")
gdf.to_file("sample_data/parcelles_test.gpkg", driver="GPKG")
print(f"OK - {len(gdf)} parcelles ecrites dans sample_data/parcelles_test.gpkg")
print("Anomalies attendues : P001/P003 doublon, P004 champ vide, P005 ecart surface,")
print("P006 geometrie invalide, P002/P007 chevauchement, P008 type incoherent")
