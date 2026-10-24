#!/usr/bin/env python3
"""
Genere les fiches indicateur structurees a partir d'un CSV
d'indicateurs fourni par l'utilisateur. Signale tout champ obligatoire
manquant -- ne complete jamais une fiche incomplete par une valeur
devinee.

CSV attendu (colonnes) :
    code_indicateur, intitule, type (activite|extrant|resultat|impact),
    formule, source_donnees, frequence_collecte, responsable, cible, unite

Usage:
    python results_framework.py sample_data/indicateurs_test.csv --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("meal.results_framework")

REQUIRED_FIELDS = ["code_indicateur", "intitule", "type", "formule", "source_donnees", "frequence_collecte", "responsable"]
VALID_TYPES = {"activite", "extrant", "resultat", "impact"}


def validate_indicators(df: pd.DataFrame) -> list[dict]:
    """Verifie chaque ligne et signale les champs manquants ou le type
    invalide. Ne corrige jamais silencieusement.
    """
    issues = []
    missing_cols = [c for c in REQUIRED_FIELDS if c not in df.columns]
    if missing_cols:
        issues.append({"indicateur": "(fichier entier)", "probleme": f"Colonnes obligatoires absentes : {missing_cols}"})
        return issues

    for idx, row in df.iterrows():
        code = row.get("code_indicateur", f"ligne_{idx}")
        for field in REQUIRED_FIELDS:
            val = row.get(field)
            if pd.isna(val) or str(val).strip() == "":
                issues.append({"indicateur": code, "probleme": f"Champ obligatoire vide : {field}"})
        type_val = str(row.get("type", "")).strip().lower()
        if type_val and type_val not in VALID_TYPES:
            issues.append({"indicateur": code, "probleme": f"Type invalide '{type_val}' (attendu : {sorted(VALID_TYPES)})"})
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("indicators_csv")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    csv_path = Path(args.indicators_csv)
    if not csv_path.exists():
        print(f"Fichier introuvable : {csv_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{csv_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    df = pd.read_csv(csv_path)
    logger.info("Cadre de resultats charge : %d indicateur(s)", len(df))

    issues = validate_indicators(df)
    for issue in issues:
        logger.warning("Indicateur %s : %s", issue["indicateur"], issue["probleme"])

    counts_by_type = df["type"].value_counts().to_dict() if "type" in df.columns else {}
    logger.info("Repartition par type : %s", counts_by_type)

    out = {
        "fichier_source": str(csv_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "n_indicateurs": len(df),
        "repartition_par_type": counts_by_type,
        "problemes_detectes": issues,
    }
    out_path = run_dir / "cadre_resultats_valide.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    fiches_path = run_dir / "fiches_indicateurs.csv"
    df.to_csv(fiches_path, index=False)

    logger.info("Termine : %d indicateur(s), %d probleme(s) detecte(s)", len(df), len(issues))
    print(f"OK - cadre valide: {out_path}")
    print(f"OK - fiches indicateurs: {fiches_path}")
    if issues:
        print(f"ATTENTION : {len(issues)} probleme(s) a corriger dans le fichier source avant usage officiel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
