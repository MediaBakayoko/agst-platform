#!/usr/bin/env python3
"""
Audit d'un jeu de donnees : structure, completude, types, valeurs
aberrantes (regle IQR), correlations entre variables numeriques.
Produit un dictionnaire de donnees -- ne modifie jamais le fichier
source.

Usage:
    python data_inspector.py sample_data/dataset_test.csv --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))

logger = logging.getLogger("data_science_geoai.data_inspector")


def detect_outliers_iqr(series: pd.Series) -> dict:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < 4:
        return {"n_outliers": 0, "methode": "IQR (n insuffisant pour une estimation fiable)"}
    q1, q3 = numeric.quantile([0.25, 0.75])
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = numeric[(numeric < low) | (numeric > high)]
    return {
        "n_outliers": int(len(outliers)),
        "bornes_iqr": [round(float(low), 3), round(float(high), 3)],
        "valeurs_aberrantes": outliers.tolist()[:20],
    }


def build_data_dictionary(df: pd.DataFrame) -> list[dict]:
    entries = []
    for col in df.columns:
        series = df[col]
        n_total = len(series)
        n_missing = int(series.isna().sum())
        dtype_detected = str(series.dtype)
        entry = {
            "variable": col,
            "type_detecte": dtype_detected,
            "n_valeurs": n_total,
            "n_manquantes": n_missing,
            "pct_manquant": round(n_missing / n_total * 100, 1) if n_total else 0,
            "n_valeurs_uniques": int(series.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(series) or series.apply(lambda v: isinstance(v, (int, float))).all():
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().any():
                entry.update({
                    "moyenne": round(float(numeric.mean()), 3),
                    "mediane": round(float(numeric.median()), 3),
                    "min": round(float(numeric.min()), 3),
                    "max": round(float(numeric.max()), 3),
                    "ecart_type": round(float(numeric.std()), 3) if numeric.notna().sum() > 1 else None,
                })
                entry["valeurs_aberrantes"] = detect_outliers_iqr(numeric)
        entries.append(entry)
    return entries


def compute_correlations(df: pd.DataFrame) -> dict:
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] < 2:
        return {"note": "Moins de 2 variables numeriques -- pas de matrice de correlation calculee"}
    corr = numeric_df.corr(method="pearson").round(3)
    return corr.to_dict()


def interpret_dictionary_with_ia(dictionary: list[dict], correlations: dict, n_lignes: int) -> str | None:
    """Demande a Claude une synthese en langage clair du dictionnaire
    de donnees REELLEMENT calcule (completude, outliers IQR,
    correlations) -- jamais un chiffre invente hors de ce
    dictionnaire. Retourne None si aucune cle API configuree ou si
    l'appel echoue.
    """
    from llm_connector import get_claude_connector, LLMNotConfiguredError, LLMAPIError

    try:
        connector = get_claude_connector()
        system_prompt = (
            "Tu es un data scientist specialise en donnees geospatiales/agricoles. On te donne "
            "un dictionnaire de donnees REELLEMENT calcule (completude, statistiques, valeurs "
            "aberrantes detectees par regle IQR, correlations de Pearson) -- tu ne dois JAMAIS "
            "inventer un chiffre absent de ces donnees. Redige une synthese en langage clair "
            "(4-6 phrases) pour un non-statisticien : qualite globale des donnees, variables a "
            "surveiller (valeurs manquantes, aberrantes), correlations notables et leur sens "
            "possible -- sans affirmer de causalite a partir d'une simple correlation.\n\n"
            "Reponds UNIQUEMENT en JSON valide : {\"synthese\": \"...\"}"
        )
        user_content = (
            f"Nombre de lignes : {n_lignes}\n\n"
            f"Dictionnaire de donnees :\n{json.dumps(dictionary, ensure_ascii=False, indent=2, default=str)}\n\n"
            f"Correlations Pearson :\n{json.dumps(correlations, ensure_ascii=False, indent=2, default=str)}"
        )
        result = connector.generate_json(system_prompt, user_content)
        return result.get("synthese")
    except LLMNotConfiguredError as exc:
        logger.info("Synthese IA desactivee : %s", exc)
        return None
    except LLMAPIError as exc:
        logger.warning("Synthese IA indisponible (echec appel) : %s", str(exc)[:500])
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--no-ia", action="store_true")
    args = ap.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{input_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    df = pd.read_csv(input_path) if input_path.suffix.lower() == ".csv" else pd.read_excel(input_path)
    logger.info("Jeu de donnees charge : %d lignes, %d colonnes", len(df), len(df.columns))

    dictionary = build_data_dictionary(df)
    for entry in dictionary:
        if entry["pct_manquant"] > 20:
            logger.warning("Variable '%s' : %.1f%% de valeurs manquantes -- a considerer avant toute analyse", entry["variable"], entry["pct_manquant"])
        outliers = entry.get("valeurs_aberrantes", {})
        if isinstance(outliers, dict) and outliers.get("n_outliers", 0) > 0:
            logger.warning("Variable '%s' : %d valeur(s) aberrante(s) detectee(s) (regle IQR)", entry["variable"], outliers["n_outliers"])

    correlations = compute_correlations(df)
    synthese_ia = None if args.no_ia else interpret_dictionary_with_ia(dictionary, correlations, len(df))

    out = {
        "fichier_source": str(input_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "n_lignes": len(df),
        "n_colonnes": len(df.columns),
        "dictionnaire_donnees": dictionary,
        "correlations_pearson": correlations,
        "synthese_ia": synthese_ia,
        "avertissement_synthese_ia": (
            "La synthese_ia est une interpretation generee par IA, basee uniquement sur les "
            "chiffres ci-dessus -- a valider, jamais une source de verite independante."
            if synthese_ia else None
        ),
    }
    out_path = run_dir / "data_dictionary.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    n_vars_incompletes = sum(1 for e in dictionary if e["pct_manquant"] > 20)
    logger.info("Termine : %d variable(s) avec >20%% manquant, voir data_dictionary.json", n_vars_incompletes)
    print(f"OK - dictionnaire de donnees: {out_path}")
    if synthese_ia:
        print("INFO : synthese IA generee -- voir champ 'synthese_ia' du fichier JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
