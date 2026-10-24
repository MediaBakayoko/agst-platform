#!/usr/bin/env python3
"""
Calcule le taux d'atteinte de chaque indicateur a partir des valeurs
observees reelles et des cibles declarees. Chaque calcul est
journalise avec sa formule explicite -- aucune valeur manquante n'est
imputee.

CSV indicateurs attendu : code_indicateur, cible, unite
CSV valeurs attendu : code_indicateur, periode, valeur_observee

Usage:
    python indicator_calculator.py \
        --indicators sample_data/indicateurs_test.csv \
        --values sample_data/valeurs_observees_test.csv \
        --output-dir output/
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("meal.indicator_calculator")


def classify_status(pct_atteinte: float) -> str:
    if pct_atteinte >= 100:
        return "atteint"
    if pct_atteinte >= 70:
        return "en_bonne_voie"
    if pct_atteinte >= 40:
        return "en_retard"
    return "tres_en_retard"


def calculate_performance(indicators_df: pd.DataFrame, values_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings = []
    if "cible" not in indicators_df.columns or "code_indicateur" not in indicators_df.columns:
        raise ValueError("Le fichier indicateurs doit contenir 'code_indicateur' et 'cible'")

    rows = []
    for _, val_row in values_df.iterrows():
        code = val_row.get("code_indicateur")
        periode = val_row.get("periode")
        observe = val_row.get("valeur_observee")

        matches = indicators_df[indicators_df["code_indicateur"] == code]
        if matches.empty:
            warnings.append(f"Indicateur {code!r} present dans les valeurs mais absent du cadre de resultats -- ignore")
            continue
        cible = matches.iloc[0].get("cible")

        if pd.isna(observe):
            warnings.append(f"Valeur observee manquante pour {code} / {periode} -- non calcule (pas d'imputation)")
            pct = None
        elif pd.isna(cible) or cible == 0:
            warnings.append(f"Cible manquante ou nulle pour {code} -- taux d'atteinte non calculable")
            pct = None
        else:
            pct = round(float(observe) / float(cible) * 100.0, 1)

        rows.append({
            "code_indicateur": code,
            "periode": periode,
            "valeur_observee": observe,
            "cible": cible,
            "pct_atteinte": pct,
            "statut": classify_status(pct) if pct is not None else "non_calculable",
            "formule_appliquee": "valeur_observee / cible * 100" if pct is not None else "N/A (donnee manquante)",
        })

    return pd.DataFrame(rows), warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indicators", required=True)
    ap.add_argument("--values", required=True)
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    indicators_path = Path(args.indicators)
    values_path = Path(args.values)
    if not indicators_path.exists() or not values_path.exists():
        print("Fichier indicateurs ou valeurs introuvable", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{values_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    indicators_df = pd.read_csv(indicators_path)
    values_df = pd.read_csv(values_path)
    logger.info("Chargement : %d indicateur(s), %d observation(s)", len(indicators_df), len(values_df))

    result_df, warnings = calculate_performance(indicators_df, values_df)
    for w in warnings:
        logger.warning(w)

    out_path = run_dir / "indicateurs_calcules.csv"
    result_df.to_csv(out_path, index=False)

    n_non_calculable = (result_df["statut"] == "non_calculable").sum()
    logger.info(
        "Termine : %d calcul(s), %d non calculable(s) (donnee manquante)",
        len(result_df), n_non_calculable,
    )
    print(f"OK - indicateurs calcules: {out_path}")
    if warnings:
        print(f"ATTENTION : {len(warnings)} avertissement(s) -- voir journal.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
