#!/usr/bin/env python3
"""
Construit la matrice d'indicateurs XLSX a partir du projet structure
(project_intake.py) et d'une liste d'indicateurs fournie par
l'utilisateur (CSV).

N'invente JAMAIS une cible, baseline ou donnee -- tout champ absent du
CSV source reste vide dans la matrice, avec une colonne "a_completer"
qui liste les champs manquants pour cet indicateur.

CSV indicateurs attendu (colonnes, toutes optionnelles sauf intitule) :
    intitule, definition, formule, unite, source_verification,
    frequence, desagregation, cible, question_necessaire, regle_qualite

Usage:
    python indicator_matrix_builder.py \
        --project output/project_xxx/project_structured.json \
        --indicators sample_data/indicateurs_matrice_test.csv \
        --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

logger = logging.getLogger("survey_intelligence.indicator_matrix_builder")

MATRIX_COLUMNS = [
    "objectif", "resultat_associe", "intitule", "type_indicateur", "definition",
    "formule", "numerateur", "denominateur", "unite", "valeur_reference", "cible",
    "source_verification", "methode_collecte", "frequence", "desagregation",
    "question_necessaire", "regle_qualite", "limites_methodologiques", "statut_validation",
]
REQUIRED_FOR_DEPLOY = ["intitule", "definition", "formule", "source_verification", "frequence"]
TYPES_INDICATEUR_VALIDES = {"realisation", "resultat", "impact"}
STATUTS_VALIDATION_VALIDES = {"propose", "approuve", "rejete"}
DEFAULT_STATUT_VALIDATION = "propose"


def build_matrix(indicators_df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Normalise les colonnes (ajoute les colonnes manquantes en vide,
    jamais en les inventant) et calcule les champs a completer par
    indicateur.
    """
    missing_cols = [c for c in MATRIX_COLUMNS if c not in indicators_df.columns]
    df = indicators_df.copy()
    for c in missing_cols:
        df[c] = None
    df = df[MATRIX_COLUMNS]

    # statut_validation : valeur fournie si reconnue, sinon "propose"
    # par defaut (jamais "approuve" invente).
    def _normalize_statut(v):
        v_str = str(v).strip().lower() if not pd.isna(v) else ""
        return v_str if v_str in STATUTS_VALIDATION_VALIDES else DEFAULT_STATUT_VALIDATION
    df["statut_validation"] = df["statut_validation"].apply(_normalize_statut)

    gaps = []
    type_warnings = []
    for idx, row in df.iterrows():
        a_completer = [c for c in REQUIRED_FOR_DEPLOY if pd.isna(row[c]) or str(row[c]).strip() == ""]
        if a_completer:
            gaps.append({"indicateur": row.get("intitule", f"ligne_{idx}"), "champs_manquants": a_completer})
        if pd.isna(row["cible"]) or str(row["cible"]).strip() == "":
            gaps.append({"indicateur": row.get("intitule", f"ligne_{idx}"), "champs_manquants": ["cible (non fournie -- arbitrage utilisateur requis)"]})
        if pd.isna(row["valeur_reference"]) or str(row["valeur_reference"]).strip() == "":
            gaps.append({"indicateur": row.get("intitule", f"ligne_{idx}"), "champs_manquants": ["valeur_reference (non fournie -- jamais devinee)"]})
        type_ind = str(row["type_indicateur"]).strip().lower() if not pd.isna(row["type_indicateur"]) else ""
        if type_ind and type_ind not in TYPES_INDICATEUR_VALIDES:
            type_warnings.append(f"Indicateur '{row.get('intitule')}' : type_indicateur '{type_ind}' non reconnu (attendu: realisation/resultat/impact) -- a corriger")
        elif not type_ind:
            gaps.append({"indicateur": row.get("intitule", f"ligne_{idx}"), "champs_manquants": ["type_indicateur (realisation/resultat/impact non precise)"]})
    return df, gaps, type_warnings


def write_matrix_excel(df: pd.DataFrame, gaps: list[dict], project_elements: dict, output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Matrice indicateurs"
    header_fill = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    gap_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    for c, h in enumerate(MATRIX_COLUMNS, start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font

    gap_indicators = {g["indicateur"] for g in gaps}
    for i, row in enumerate(df.itertuples(index=False), start=2):
        row_dict = dict(zip(MATRIX_COLUMNS, row))
        for c, col in enumerate(MATRIX_COLUMNS, start=1):
            ws.cell(row=i, column=c, value=row_dict[col])
        if row_dict["intitule"] in gap_indicators:
            for c in range(1, len(MATRIX_COLUMNS) + 1):
                ws.cell(row=i, column=c).fill = gap_fill

    for c in range(1, len(MATRIX_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 24

    ws2 = wb.create_sheet("Contexte projet")
    ws2.cell(row=1, column=1, value="Element").font = Font(bold=True)
    ws2.cell(row=1, column=2, value="Contenu (ou 'non fourni')").font = Font(bold=True)
    for i, (key, val) in enumerate(project_elements.items(), start=2):
        ws2.cell(row=i, column=1, value=key)
        ws2.cell(row=i, column=2, value=val or "non fourni -- a demander a l'utilisateur")
    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 80

    ws3 = wb.create_sheet("A completer")
    ws3.cell(row=1, column=1, value="AVERTISSEMENT").font = Font(bold=True, color="C00000", size=12)
    ws3.cell(row=2, column=1, value="Aucune cible ou donnee n'a ete inventee. Les elements ci-dessous necessitent un arbitrage ou une donnee de l'utilisateur avant validation de la matrice.")
    ws3.cell(row=4, column=1, value="Indicateur").font = Font(bold=True)
    ws3.cell(row=4, column=2, value="Champs manquants").font = Font(bold=True)
    for i, g in enumerate(gaps, start=5):
        ws3.cell(row=i, column=1, value=g["indicateur"])
        ws3.cell(row=i, column=2, value=", ".join(g["champs_manquants"]))
    ws3.column_dimensions["A"].width = 30
    ws3.column_dimensions["B"].width = 60

    wb.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="JSON produit par project_intake.py")
    ap.add_argument("--indicators", required=True, help="CSV d'indicateurs fournis par l'utilisateur")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    project_path = Path(args.project)
    indicators_path = Path(args.indicators)
    if not project_path.exists() or not indicators_path.exists():
        print("Fichier projet ou indicateurs introuvable", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"matrix_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    project = json.loads(project_path.read_text(encoding="utf-8"))
    indicators_df = pd.read_csv(indicators_path)
    logger.info("Chargement : projet (%d element(s) detecte(s)), %d indicateur(s)",
                sum(1 for v in project["elements"].values() if v), len(indicators_df))

    matrix_df, gaps, type_warnings = build_matrix(indicators_df)
    for g in gaps:
        logger.warning("Indicateur '%s' : champs manquants %s", g["indicateur"], g["champs_manquants"])
    for w in type_warnings:
        logger.warning(w)

    excel_path = run_dir / "matrice_indicateurs.xlsx"
    write_matrix_excel(matrix_df, gaps, project["elements"], excel_path)

    logger.info("Matrice ecrite : %s (%d indicateur(s), %d lacune(s) signalee(s), %d avertissement(s) de type)",
                excel_path, len(matrix_df), len(gaps), len(type_warnings))
    print(f"OK - matrice: {excel_path}")
    if gaps:
        print(f"ATTENTION : {len(gaps)} lacune(s) a arbitrer avant approbation -- voir feuille 'A completer'")
    if type_warnings:
        print(f"ATTENTION : {len(type_warnings)} type(s) d'indicateur non reconnu(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
