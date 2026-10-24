"""
Field2Report — analyse statistique et cartographie.

Regles :
  - toute statistique affichee provient d'un calcul reel sur les donnees
    nettoyees, jamais d'une valeur par defaut ou inventee
  - les variables avec trop peu d'observations pour etre fiables sont
    signalees (n < seuil), jamais masquees silencieusement
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

logger = logging.getLogger("field2report.analysis")

MIN_N_FOR_STATS = 3


def descriptive_stats(df: pd.DataFrame, numeric_fields: list[str], group_field: Optional[str] = None) -> pd.DataFrame:
    """Statistiques descriptives globales, et par groupe si group_field
    est fourni. Signale les groupes avec n < MIN_N_FOR_STATS.
    """
    rows = []
    for fld in numeric_fields:
        if fld not in df.columns:
            continue
        series = pd.to_numeric(df[fld], errors="coerce").dropna()
        rows.append({
            "variable": fld, "groupe": "(ensemble)", "n": len(series),
            "moyenne": series.mean() if len(series) else None,
            "mediane": series.median() if len(series) else None,
            "min": series.min() if len(series) else None,
            "max": series.max() if len(series) else None,
            "ecart_type": series.std() if len(series) else None,
            "fiabilite": "ok" if len(series) >= MIN_N_FOR_STATS else "n_insuffisant",
        })
        if group_field and group_field in df.columns:
            for grp_val, grp_df in df.groupby(group_field):
                grp_series = pd.to_numeric(grp_df[fld], errors="coerce").dropna()
                rows.append({
                    "variable": fld, "groupe": str(grp_val), "n": len(grp_series),
                    "moyenne": grp_series.mean() if len(grp_series) else None,
                    "mediane": grp_series.median() if len(grp_series) else None,
                    "min": grp_series.min() if len(grp_series) else None,
                    "max": grp_series.max() if len(grp_series) else None,
                    "ecart_type": grp_series.std() if len(grp_series) else None,
                    "fiabilite": "ok" if len(grp_series) >= MIN_N_FOR_STATS else "n_insuffisant",
                })
    return pd.DataFrame(rows)


def detect_sample_bias(df: pd.DataFrame, group_field: Optional[str] = None) -> list[str]:
    """Signale des desequilibres manifestes dans l'echantillon. Ne
    corrige jamais, informe seulement.
    """
    notes = []
    if group_field and group_field in df.columns:
        counts = df[group_field].value_counts()
        if len(counts) > 1:
            ratio = counts.max() / max(counts.min(), 1)
            if ratio >= 3:
                notes.append(
                    f"Deséquilibre marque entre groupes de '{group_field}' : "
                    f"{counts.idxmax()!r} ({counts.max()} obs.) represente {ratio:.1f}x "
                    f"{counts.idxmin()!r} ({counts.min()} obs.). A considerer dans l'interpretation."
                )
    n_total = len(df)
    if n_total < 30:
        notes.append(
            f"Echantillon de petite taille (n={n_total}) : les statistiques descriptives "
            "doivent etre interpretees avec prudence, en particulier par sous-groupe."
        )
    return notes


def plot_survey_map(
    df: pd.DataFrame,
    lat_field: str,
    lon_field: str,
    output_path: Path,
    group_field: Optional[str] = None,
    title: str = "Carte des points de collecte",
) -> Optional[Path]:
    if lat_field not in df.columns or lon_field not in df.columns:
        logger.warning("Champs GPS absents (%s/%s), carte non generee", lat_field, lon_field)
        return None

    lat = pd.to_numeric(df[lat_field], errors="coerce")
    lon = pd.to_numeric(df[lon_field], errors="coerce")
    valid = lat.notna() & lon.notna() & ~((lat == 0) & (lon == 0))
    if valid.sum() == 0:
        logger.warning("Aucune coordonnee GPS valide, carte non generee")
        return None

    fig, ax = plt.subplots(figsize=(8, 8))
    if group_field and group_field in df.columns:
        for grp_val, grp_df in df[valid].groupby(df.loc[valid, group_field]):
            ax.scatter(
                pd.to_numeric(grp_df[lon_field], errors="coerce"),
                pd.to_numeric(grp_df[lat_field], errors="coerce"),
                label=str(grp_val), s=40, alpha=0.8,
            )
        ax.legend(title=group_field, fontsize=8)
    else:
        ax.scatter(lon[valid], lat[valid], s=40, alpha=0.8, color="#1F3864")

    n_excluded = (~valid).sum()
    subtitle = f"{valid.sum()} points"
    if n_excluded:
        subtitle += f" ({n_excluded} exclus : coordonnees manquantes ou (0,0))"
    ax.set_title(f"{title}\n{subtitle}", fontsize=11)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
