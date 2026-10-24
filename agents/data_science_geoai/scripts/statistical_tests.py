#!/usr/bin/env python3
"""
Tests statistiques usuels avec verification explicite des hypotheses
prealables. N'applique jamais un test sans signaler si ses conditions
d'usage ne sont pas remplies.

Usage:
    python statistical_tests.py data.csv --test correlation --field-x A --field-y B --output-dir output/
    python statistical_tests.py data.csv --test ttest --field-x A --group-field G --output-dir output/
    python statistical_tests.py data.csv --test anova --field-x A --group-field G --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from scipy import stats

logger = logging.getLogger("data_science_geoai.statistical_tests")


def check_normality(series: pd.Series) -> dict:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 3:
        return {"applicable": False, "raison": "n < 3, test de normalite non applicable"}
    if len(numeric) > 5000:
        numeric = numeric.sample(5000, random_state=42)
    stat, pval = stats.shapiro(numeric)
    return {
        "applicable": True, "test": "shapiro-wilk", "statistique": round(float(stat), 4),
        "p_value": round(float(pval), 4), "normal_au_seuil_5pct": bool(pval > 0.05),
    }


def run_correlation(df: pd.DataFrame, field_x: str, field_y: str) -> dict:
    x = pd.to_numeric(df[field_x], errors="coerce")
    y = pd.to_numeric(df[field_y], errors="coerce")
    valid = x.notna() & y.notna()
    n = int(valid.sum())
    result = {"test": "correlation", "field_x": field_x, "field_y": field_y, "n": n}
    if n < 3:
        result["erreur"] = "n < 3, correlation non calculable"
        return result

    norm_x, norm_y = check_normality(x[valid]), check_normality(y[valid])
    result["normalite_x"] = norm_x
    result["normalite_y"] = norm_y
    both_normal = norm_x.get("normal_au_seuil_5pct", False) and norm_y.get("normal_au_seuil_5pct", False)

    if both_normal:
        r, pval = stats.pearsonr(x[valid], y[valid])
        result["methode"] = "pearson (hypothese de normalite verifiee)"
    else:
        r, pval = stats.spearmanr(x[valid], y[valid])
        result["methode"] = "spearman (normalite non verifiee pour au moins une variable -- methode non parametrique utilisee)"
    result["coefficient"] = round(float(r), 4)
    result["p_value"] = round(float(pval), 4)
    result["significatif_au_seuil_5pct"] = bool(pval < 0.05)
    result["avertissement"] = "Une correlation, meme significative, n'est jamais une preuve de causalite."
    return result


def run_ttest(df: pd.DataFrame, field_x: str, group_field: str) -> dict:
    groups = df[group_field].dropna().unique()
    result = {"test": "t-test independant", "field_x": field_x, "group_field": group_field}
    if len(groups) != 2:
        result["erreur"] = f"Le t-test a 2 echantillons requiert exactement 2 groupes, {len(groups)} trouve(s) : {list(groups)}"
        return result

    g1 = pd.to_numeric(df[df[group_field] == groups[0]][field_x], errors="coerce").dropna()
    g2 = pd.to_numeric(df[df[group_field] == groups[1]][field_x], errors="coerce").dropna()
    result["groupes"] = {str(groups[0]): len(g1), str(groups[1]): len(g2)}
    if len(g1) < 3 or len(g2) < 3:
        result["erreur"] = "Au moins un groupe a n < 3, t-test non fiable"
        return result

    norm1, norm2 = check_normality(g1), check_normality(g2)
    result["normalite_groupe1"] = norm1
    result["normalite_groupe2"] = norm2
    if not (norm1.get("normal_au_seuil_5pct") and norm2.get("normal_au_seuil_5pct")):
        result["avertissement_normalite"] = "Hypothese de normalite non verifiee pour au moins un groupe -- interpreter le resultat avec prudence (test de Mann-Whitney non parametrique serait plus approprie)."

    stat, pval = stats.ttest_ind(g1, g2, equal_var=False)
    result["statistique"] = round(float(stat), 4)
    result["p_value"] = round(float(pval), 4)
    result["significatif_au_seuil_5pct"] = bool(pval < 0.05)
    return result


def run_anova(df: pd.DataFrame, field_x: str, group_field: str) -> dict:
    groups_data = [pd.to_numeric(g[field_x], errors="coerce").dropna() for _, g in df.groupby(group_field)]
    group_names = list(df[group_field].dropna().unique())
    result = {"test": "ANOVA a 1 facteur", "field_x": field_x, "group_field": group_field, "n_groupes": len(groups_data)}
    too_small = [g for g in groups_data if len(g) < 3]
    if too_small:
        result["erreur"] = f"{len(too_small)} groupe(s) avec n < 3 -- ANOVA non fiable"
        return result

    stat, pval = stats.f_oneway(*groups_data)
    result["statistique_F"] = round(float(stat), 4)
    result["p_value"] = round(float(pval), 4)
    result["significatif_au_seuil_5pct"] = bool(pval < 0.05)
    result["avertissement"] = "Un resultat significatif indique une difference entre groupes, pas quels groupes different (test post-hoc necessaire pour cela)."
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file")
    ap.add_argument("--test", required=True, choices=["correlation", "ttest", "anova"])
    ap.add_argument("--field-x", required=True)
    ap.add_argument("--field-y", default=None)
    ap.add_argument("--group-field", default=None)
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{args.test}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    df = pd.read_csv(input_path) if input_path.suffix.lower() == ".csv" else pd.read_excel(input_path)

    if args.test == "correlation":
        if not args.field_y:
            print("--field-y requis pour le test de correlation", file=sys.stderr)
            return 1
        result = run_correlation(df, args.field_x, args.field_y)
    elif args.test == "ttest":
        if not args.group_field:
            print("--group-field requis pour le t-test", file=sys.stderr)
            return 1
        result = run_ttest(df, args.field_x, args.group_field)
    else:
        if not args.group_field:
            print("--group-field requis pour l'ANOVA", file=sys.stderr)
            return 1
        result = run_anova(df, args.field_x, args.group_field)

    if "erreur" in result:
        logger.warning("Test non realise : %s", result["erreur"])
    else:
        logger.info("Test %s realise : %s", args.test, {k: v for k, v in result.items() if k not in ("normalite_x", "normalite_y", "normalite_groupe1", "normalite_groupe2")})

    out_path = run_dir / "resultat_test.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK - resultat: {out_path}")
    if "erreur" in result:
        print(f"ATTENTION : {result['erreur']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
