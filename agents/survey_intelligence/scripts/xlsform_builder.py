#!/usr/bin/env python3
"""
Genere un XLSForm (survey / choices / settings) conforme aux
specifications KoboToolbox/ODK, a partir de la matrice d'indicateurs
approuvee (question_necessaire par indicateur).

Ne deploie rien -- produit uniquement le fichier .xlsx telechargeable
pour revue/validation humaine (voir xlsform_validator.py pour la
validation automatique avant approbation).

Format de la colonne "question_necessaire" dans la matrice (texte
libre, interprete heuristiquement). Champs separes par "|" apres le
type de base :
    "text:Nom du repondant"
    "integer:Age du repondant"
    "select_one:Sexe:Masculin,Feminin"
    "select_multiple:Cultures:Cacao,Hevea,Cafe"
    "decimal:Surface de la parcelle (ha)"
    "date:Date de la visite"
    "geopoint:Localisation GPS"
    "calculate:Surface totale (ha)|expr=surface_ha * 1"
Qualificatifs optionnels (ajoutes apres des "|") :
    required=no                  -> champ facultatif (defaut: yes)
    relevant=${champ}='valeur'   -> logique conditionnelle (saut)
    constraint=. >= 0            -> contrainte de validation XLSForm
    constraint_message=texte     -> message d'erreur affiche si violee
    repeat_group=nom_groupe      -> place la question dans un groupe
                                     "begin repeat"/"end repeat" nomme
    hint=texte d'aide

Metadonnees d'enqueteur : si --add-enumerator-metadata est passe, ajoute
automatiquement start/end/today/deviceid/username (type note/calculate
standard XLSForm) en tete du formulaire.

Si le format n'est pas reconnu, le champ est cree en "text" generique
et SIGNALE comme necessitant une revue manuelle -- jamais une
supposition silencieuse du type de question.

Usage:
    python xlsform_builder.py --matrix output/matrix_xxx/matrice_indicateurs.xlsx --output-dir output/ --add-enumerator-metadata
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

logger = logging.getLogger("survey_intelligence.xlsform_builder")

SUPPORTED_TYPES = {
    "text", "integer", "decimal", "date", "datetime", "time", "geopoint",
    "select_one", "select_multiple", "calculate", "note",
}
ENUMERATOR_METADATA_ROWS = [
    {"type": "start", "name": "start", "label": ""},
    {"type": "end", "name": "end", "label": ""},
    {"type": "today", "name": "today", "label": ""},
    {"type": "deviceid", "name": "deviceid", "label": ""},
    {"type": "username", "name": "username", "label": ""},
]


def slugify(text: str, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", text.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len] or "champ"


def parse_question_spec(spec: str, fallback_label: str) -> dict:
    """Parse une specification de question ; si non reconnue, retombe
    sur un champ texte generique ET le signale explicitement.

    Qualificatifs optionnels apres le 2e/3e segment, prefixes "cle=valeur"
    separes par "|" : required, relevant, constraint, constraint_message,
    repeat_group, hint, expr (pour calculate).
    """
    result = {
        "type": "text", "label": fallback_label, "choices": None, "reconnu": False,
        "required": "yes", "relevant": None, "constraint": None,
        "constraint_message": None, "repeat_group": None, "hint": None, "expr": None,
    }
    if not spec or pd.isna(spec):
        return result

    segments = str(spec).split("|")
    main_spec = segments[0]
    qualifiers = segments[1:]

    for q in qualifiers:
        if "=" not in q:
            continue
        key, _, value = q.partition("=")
        key = key.strip().lower()
        if key in ("required", "relevant", "constraint", "constraint_message", "repeat_group", "hint", "expr"):
            result[key] = value.strip()

    parts = main_spec.split(":")
    qtype = parts[0].strip().lower()
    if qtype not in SUPPORTED_TYPES:
        return result

    label = parts[1].strip() if len(parts) > 1 else fallback_label
    choices = None
    if qtype in ("select_one", "select_multiple") and len(parts) > 2:
        choices = [c.strip() for c in parts[2].split(",") if c.strip()]

    result.update({"type": qtype, "label": label, "choices": choices, "reconnu": True})
    return result


def build_xlsform(matrix_df: pd.DataFrame, form_title: str, add_enumerator_metadata: bool = False) -> tuple[list[dict], list[dict], dict, list[str]]:
    """Construit les lignes survey/choices/settings. Renvoie aussi la
    liste des avertissements (champs non reconnus, intitules dupliques).

    Gere les groupes de repetition (repeat_group) en encadrant les
    questions concernees par begin repeat/end repeat, en preservant
    l'ordre d'apparition dans la matrice.
    """
    survey_rows = []
    choices_rows = []
    warnings = []
    used_names = set()
    open_repeat_group = None

    survey_rows.append({"type": "start", "name": "start", "label": ""})
    if add_enumerator_metadata:
        for meta_row in ENUMERATOR_METADATA_ROWS[2:]:  # today/deviceid/username (start/end geres a part)
            survey_rows.append(dict(meta_row))

    for _, row in matrix_df.iterrows():
        intitule = str(row.get("intitule", "")).strip()
        spec_text = row.get("question_necessaire")
        parsed = parse_question_spec(spec_text, fallback_label=intitule)

        if not parsed["reconnu"]:
            warnings.append(
                f"Indicateur '{intitule}' : specification de question non reconnue ou absente "
                f"('{spec_text}') -- champ texte generique cree, A REVOIR MANUELLEMENT."
            )

        base_name = slugify(intitule)
        name = base_name
        suffix = 1
        while name in used_names:
            suffix += 1
            name = f"{base_name}_{suffix}"
            warnings.append(f"Nom de champ '{base_name}' deja utilise -- renomme en '{name}' pour eviter un doublon.")
        used_names.add(name)

        # Gestion des groupes de repetition : ouvre/ferme selon la
        # transition par rapport a la ligne precedente.
        target_group = parsed["repeat_group"]
        if target_group != open_repeat_group:
            if open_repeat_group is not None:
                survey_rows.append({"type": "end repeat", "name": f"end_{slugify(open_repeat_group)}", "label": ""})
            if target_group:
                survey_rows.append({"type": "begin repeat", "name": slugify(target_group), "label": target_group})
            open_repeat_group = target_group

        survey_row = {
            "type": parsed["type"], "name": name, "label": parsed["label"],
            "required": parsed["required"] or "yes",
        }
        if parsed["relevant"]:
            survey_row["relevant"] = parsed["relevant"]
        if parsed["constraint"]:
            survey_row["constraint"] = parsed["constraint"]
        if parsed["constraint_message"]:
            survey_row["constraint_message"] = parsed["constraint_message"]
        if parsed["hint"]:
            survey_row["hint"] = parsed["hint"]
        if parsed["type"] == "calculate" and parsed["expr"]:
            survey_row["calculation"] = parsed["expr"]
        elif parsed["type"] == "calculate" and not parsed["expr"]:
            warnings.append(f"Champ '{name}' de type calculate sans expression (expr=...) -- A COMPLETER MANUELLEMENT.")

        if parsed["type"] in ("select_one", "select_multiple") and parsed["choices"]:
            list_name = f"{name}_choices"
            survey_row["type"] = f"{parsed['type']} {list_name}"
            for choice_label in parsed["choices"]:
                choices_rows.append({"list_name": list_name, "name": slugify(choice_label, 20), "label": choice_label})
        elif parsed["type"] in ("select_one", "select_multiple"):
            warnings.append(f"Champ '{name}' de type {parsed['type']} sans choix fournis -- cree sans liste, A COMPLETER MANUELLEMENT.")

        survey_rows.append(survey_row)

    if open_repeat_group is not None:
        survey_rows.append({"type": "end repeat", "name": f"end_{slugify(open_repeat_group)}", "label": ""})

    survey_rows.append({"type": "end", "name": "end", "label": ""})

    settings = {"form_title": form_title, "form_id": slugify(form_title, 40)}
    return survey_rows, choices_rows, settings, warnings


def write_xlsform(survey_rows: list[dict], choices_rows: list[dict], settings: dict, output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws_survey = wb.active
    ws_survey.title = "survey"
    survey_headers = ["type", "name", "label", "required", "relevant", "constraint", "constraint_message", "calculation", "hint"]
    ws_survey.append(survey_headers)
    for row in survey_rows:
        ws_survey.append([row.get(h, "") for h in survey_headers])

    ws_choices = wb.create_sheet("choices")
    choices_headers = ["list_name", "name", "label"]
    ws_choices.append(choices_headers)
    for row in choices_rows:
        ws_choices.append([row.get(h, "") for h in choices_headers])

    ws_settings = wb.create_sheet("settings")
    ws_settings.append(["form_title", "form_id"])
    ws_settings.append([settings["form_title"], settings["form_id"]])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--form-title", default=None)
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--add-enumerator-metadata", action="store_true",
                     help="Ajoute today/deviceid/username en tete du formulaire")
    args = ap.parse_args()

    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        print(f"Fichier matrice introuvable : {matrix_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"xlsform_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    matrix_df = pd.read_excel(matrix_path, sheet_name="Matrice indicateurs")
    logger.info("Matrice chargee : %d indicateur(s)", len(matrix_df))

    form_title = args.form_title or f"Enquete {matrix_path.stem}"
    survey_rows, choices_rows, settings, warnings = build_xlsform(matrix_df, form_title, args.add_enumerator_metadata)
    for w in warnings:
        logger.warning(w)

    output_path = run_dir / "formulaire.xlsx"
    write_xlsform(survey_rows, choices_rows, settings, output_path)

    n_questions = len([r for r in survey_rows if r["type"] not in ("start", "end", "today", "deviceid", "username", "begin repeat", "end repeat")])
    logger.info("XLSForm genere : %d question(s), %d avertissement(s)", n_questions, len(warnings))
    print(f"OK - xlsform: {output_path}")
    if warnings:
        print(f"ATTENTION : {len(warnings)} point(s) a revoir manuellement avant approbation")
    print("RAPPEL : ce formulaire n'est PAS deploye -- validation (xlsform_validator.py) puis approbation humaine requises.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

