"""Genere un jeu de donnees d'enquete synthetique avec anomalies connues."""
import pandas as pd

rows = [
    {"nom_repondant": "Koffi Jean", "commune": "Yopougon", "age": 45, "surface_ha": 1.5, "rendement_kg_ha": 850, "latitude": 5.345, "longitude": -4.095},
    {"nom_repondant": "Aka Marie", "commune": "Yopougon", "age": 38, "surface_ha": 2.0, "rendement_kg_ha": 900, "latitude": 5.347, "longitude": -4.097},
    {"nom_repondant": "Ouattara Ali", "commune": "Abobo", "age": 52, "surface_ha": 1.2, "rendement_kg_ha": 780, "latitude": 5.420, "longitude": -4.020},
    {"nom_repondant": "Bamba Fatou", "commune": "Abobo", "age": 29, "surface_ha": 0.8, "rendement_kg_ha": 700, "latitude": 5.422, "longitude": -4.022},
    {"nom_repondant": "Diallo Seydou", "commune": "Abobo", "age": 61, "surface_ha": 1.9, "rendement_kg_ha": 950, "latitude": 5.425, "longitude": -4.025},
    # Anomalie : champ obligatoire (commune) vide
    {"nom_repondant": "Traore Awa", "commune": None, "age": 34, "surface_ha": 1.1, "rendement_kg_ha": 820, "latitude": 5.400, "longitude": -4.010},
    # Anomalie : age hors plage plausible (ici testee comme rendement hors plage realiste)
    {"nom_repondant": "Kone Issa", "commune": "Yopougon", "age": 150, "surface_ha": 1.4, "rendement_kg_ha": 880, "latitude": 5.346, "longitude": -4.096},
    # Anomalie : coordonnees GPS (0,0) suspectes
    {"nom_repondant": "Yao Paul", "commune": "Cocody", "age": 40, "surface_ha": 1.0, "rendement_kg_ha": 800, "latitude": 0, "longitude": 0},
    # Anomalie : doublon exact de Koffi Jean
    {"nom_repondant": "Koffi Jean", "commune": "Yopougon", "age": 45, "surface_ha": 1.5, "rendement_kg_ha": 850, "latitude": 5.345, "longitude": -4.095},
    # Cocody : un seul repondant -> desequilibre vs Yopougon/Abobo
    {"nom_repondant": "Bakayoko Marc", "commune": "Cocody", "age": 48, "surface_ha": 1.6, "rendement_kg_ha": "non mesure", "latitude": 5.355, "longitude": -3.985},
]

df = pd.DataFrame(rows)
df.to_csv("sample_data/enquete_test.csv", index=False)
print(f"OK - {len(df)} lignes ecrites dans sample_data/enquete_test.csv")
