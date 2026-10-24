#!/usr/bin/env python3
"""
Entrainement et validation d'un modele de regression ou classification
(scikit-learn), avec split train/test (jamais de fuite : la metrique
n'est jamais calculee sur les donnees d'entrainement), comparaison
obligatoire a une baseline naive, et rapport des limites.

Usage:
    python model_trainer.py data.csv --target rendement_kg_ha \
        --features surface_ha,age_plantation --model-type regression \
        --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score,
)
from sklearn.model_selection import train_test_split

logger = logging.getLogger("data_science_geoai.model_trainer")

MIN_N_FOR_MODELING = 20


def check_class_balance(y: pd.Series) -> dict:
    counts = y.value_counts()
    ratio = counts.max() / max(counts.min(), 1)
    return {
        "effectifs_par_classe": counts.to_dict(),
        "ratio_desequilibre": round(float(ratio), 2),
        "desequilibre_marque": bool(ratio >= 3),
    }


def train_and_evaluate(
    df: pd.DataFrame, target: str, features: list[str], model_type: str, test_size: float = 0.25,
) -> dict:
    n = len(df)
    result: dict = {"n_total": n, "target": target, "features": features, "model_type": model_type}

    if n < MIN_N_FOR_MODELING:
        result["erreur"] = (
            f"n={n} < {MIN_N_FOR_MODELING} : echantillon trop petit pour entrainer et "
            "valider un modele de maniere fiable. Aucun modele entraine."
        )
        return result

    missing_features = [f for f in features if f not in df.columns]
    if missing_features or target not in df.columns:
        result["erreur"] = f"Colonnes absentes : {missing_features + ([target] if target not in df.columns else [])}"
        return result

    work = df[features + [target]].dropna()
    n_after_dropna = len(work)
    result["n_apres_suppression_na"] = n_after_dropna
    if n_after_dropna < n:
        result["avertissement_na"] = f"{n - n_after_dropna} ligne(s) avec valeur manquante exclues (jamais imputees)"
    if n_after_dropna < MIN_N_FOR_MODELING:
        result["erreur"] = f"Apres suppression des NA, n={n_after_dropna} < {MIN_N_FOR_MODELING} : trop peu de donnees"
        return result

    X = work[features]
    y = work[target]

    if model_type == "classification":
        balance = check_class_balance(y)
        result["balance_classes"] = balance
        if balance["desequilibre_marque"]:
            result["avertissement_balance"] = "Desequilibre marque entre classes -- l'accuracy seule peut etre trompeuse, voir f1_score."

    # Split STRICT avant tout calcul -- jamais de fit+eval sur le meme ensemble
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    result["n_train"] = len(X_train)
    result["n_test"] = len(X_test)

    if model_type == "regression":
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        baseline = DummyRegressor(strategy="mean")
    else:
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        baseline = DummyClassifier(strategy="most_frequent")

    model.fit(X_train, y_train)
    baseline.fit(X_train, y_train)

    pred = model.predict(X_test)
    pred_baseline = baseline.predict(X_test)

    if model_type == "regression":
        result["metriques_modele"] = {
            "r2": round(float(r2_score(y_test, pred)), 4),
            "mae": round(float(mean_absolute_error(y_test, pred)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, pred))), 4),
        }
        result["metriques_baseline_naive"] = {
            "r2": round(float(r2_score(y_test, pred_baseline)), 4),
            "mae": round(float(mean_absolute_error(y_test, pred_baseline)), 4),
            "rmse": round(float(np.sqrt(mean_squared_error(y_test, pred_baseline))), 4),
        }
        result["modele_meilleur_que_baseline"] = bool(result["metriques_modele"]["r2"] > result["metriques_baseline_naive"]["r2"])
    else:
        result["metriques_modele"] = {
            "accuracy": round(float(accuracy_score(y_test, pred)), 4),
            "f1_score_weighted": round(float(f1_score(y_test, pred, average="weighted", zero_division=0)), 4),
        }
        result["metriques_baseline_naive"] = {
            "accuracy": round(float(accuracy_score(y_test, pred_baseline)), 4),
            "f1_score_weighted": round(float(f1_score(y_test, pred_baseline, average="weighted", zero_division=0)), 4),
        }
        result["modele_meilleur_que_baseline"] = bool(result["metriques_modele"]["f1_score_weighted"] > result["metriques_baseline_naive"]["f1_score_weighted"])

    if hasattr(model, "feature_importances_"):
        result["importance_variables"] = dict(zip(features, [round(float(v), 4) for v in model.feature_importances_]))

    result["avertissements"] = [
        "Ce modele est un PROTOTYPE evalue sur un seul split train/test -- une validation croisee et "
        "un jeu de test independant supplementaire sont recommandes avant tout usage operationnel.",
        "Les metriques ci-dessus mesurent la performance sur les donnees de test uniquement -- "
        "aucune metrique n'a ete calculee sur les donnees d'entrainement.",
        "Ne pas deployer ce modele dans un workflow a consequences sans validation humaine explicite.",
    ]
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file")
    ap.add_argument("--target", required=True)
    ap.add_argument("--features", required=True, help="Liste de champs separes par des virgules")
    ap.add_argument("--model-type", required=True, choices=["regression", "classification"])
    ap.add_argument("--test-size", type=float, default=0.25)
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"model_{args.model_type}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    df = pd.read_csv(input_path) if input_path.suffix.lower() == ".csv" else pd.read_excel(input_path)
    features = [f.strip() for f in args.features.split(",") if f.strip()]

    result = train_and_evaluate(df, args.target, features, args.model_type, args.test_size)

    if "erreur" in result:
        logger.error(result["erreur"])
    else:
        logger.info("Modele entraine : %s", result["metriques_modele"])
        logger.info("Baseline naive : %s", result["metriques_baseline_naive"])
        logger.info("Modele meilleur que baseline : %s", result["modele_meilleur_que_baseline"])

    out_path = run_dir / "resultat_modele.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"OK - resultat: {out_path}")
    if "erreur" in result:
        print(f"ATTENTION : {result['erreur']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
