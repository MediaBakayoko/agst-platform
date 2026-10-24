"""Genere un jeu de donnees agricole synthetique (30 lignes, assez pour modelisation)."""
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
n = 30
surface_ha = rng.uniform(0.5, 4.0, n).round(2)
age_plantation = rng.integers(1, 20, n)
# Rendement correle a surface et age avec bruit (relation plausible, pas parfaite)
rendement_kg_ha = (600 + 150 * np.log1p(age_plantation) + rng.normal(0, 80, n)).round(1)
commune = rng.choice(["Yopougon", "Abobo", "Cocody"], n, p=[0.5, 0.35, 0.15])
# Un outlier volontaire
surface_ha[5] = 25.0

df = pd.DataFrame({
    "id_parcelle": [f"P{i:03d}" for i in range(n)],
    "commune": commune,
    "surface_ha": surface_ha,
    "age_plantation": age_plantation,
    "rendement_kg_ha": rendement_kg_ha,
})
# Quelques valeurs manquantes volontaires
df.loc[3, "rendement_kg_ha"] = None
df.loc[10, "surface_ha"] = None

df.to_csv("sample_data/dataset_test.csv", index=False)
print(f"OK - {len(df)} lignes ecrites dans sample_data/dataset_test.csv")
