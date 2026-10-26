#!/usr/bin/env python3
"""
Valide la coherence d'un XLSForm AVANT toute approbation ou tout
deploiement. Deux couches de validation :

1. pyxform (bibliotheque officielle utilisee par KoboToolbox/ODK en
   interne) -- tente une conversion reelle XLSForm -> XForm XML. Si
   pyxform rejette le formulaire, c'est une erreur bloquante certaine :
   le formulaire ne serait pas accepte par un vrai serveur Kobo.
2. Controles complementaires maison (noms uniques, types reconnus,
   references de listes de choix, groupes repeat bien fermes,
   coherence relevant/${champ}) -- messages plus explicites en
   francais que les erreurs brutes de pyxform.

Ne deploie rien -- rapporte seulement les erreurs bloquantes (le
formulaire ne peut pas etre utilise tel quel) separement des
avertissements (fonctionnera mais a ameliorer).

Usage:
    python xlsform_validator.py output/xlsform_xxx/formulaire.xlsx --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger("survey_intelligence.xlsform_validator")

VALID_BASE_TYPES = {
    "text", "integer", "decimal", "date", "datetime", "time", "geopoint",
    "select_one", "select_multiple", "calculate", "note", "start", "end",
    "today", "deviceid", "username", "begin repeat", "end repeat",
}


def validate_with_pyxform(xlsform_path: Path) -> dict:
    """Tente une conversion reelle avec pyxform (bibliotheque officielle
    ODK/Kobo). Renvoie {disponible, valide, erreur} -- si pyxform n'est
    pas installe, disponible=False et ce controle est simplement
    ignore (pas traite comme un echec de validation).

    NOTE : la validation finale XML stricte de pyxform (option
    validate=True) necessite Java (ODK Validate) -- absent de cet
    environnement. On utilise donc validate=False : la conversion
    XLSForm -> XForm elle-meme (structure, types, choices, logique
    conditionnelle, repeats) reste un test reel et significatif ;
    seule la toute derniere passe de validation XML stricte cote ODK
    n'est pas executee ici. C'est signale explicitement, jamais
    cache.
    """
    try:
        from pyxform.xls2xform import xls2xform_convert
    except ImportError:
        return {"disponible": False, "valide": None, "erreur": None}

    with tempfile.TemporaryDirectory() as tmp:
        xform_path = Path(tmp) / "form.xml"
        try:
            warnings_list = xls2xform_convert(str(xlsform_path), str(xform_path), validate=False)
            return {"disponible": True, "valide": True, "erreur": None,
                     "avertissements_pyxform": [str(w) for w in (warnings_list or [])],
                     "validation_odk_java_executee": False}
        except Exception as exc:
            return {"disponible": True, "valide": False, "erreur": str(exc), "avertissements_pyxform": [],
                     "validation_odk_java_executee": False}


def validate_xlsform(xlsform_path: Path) -> dict:
    errors = []
    warnings = []

    pyxform_result = validate_with_pyxform(xlsform_path)
    if pyxform_result["disponible"]:
        if not pyxform_result["valide"]:
            errors.append(f"pyxform (validateur officiel ODK/Kobo) rejette le formulaire : {pyxform_result['erreur']}")
        warnings.extend(f"pyxform : {w}" for w in pyxform_result.get("avertissements_pyxform", []))
        warnings.append("Validation ODK finale (Java/ODK Validate) non executee dans cet environnement -- conversion XLSForm->XForm reussie uniquement.")
    else:
        warnings.append("pyxform non installe -- validation limitee aux controles internes (moins fiable que le validateur officiel)")

    try:
        xls = pd.ExcelFile(xlsform_path)
    except Exception as exc:
        return {"valide": False, "erreurs_bloquantes": [f"Fichier illisible : {exc}"], "avertissements": [],
                "pyxform_disponible": pyxform_result["disponible"]}

    required_sheets = {"survey", "choices", "settings"}
    missing_sheets = required_sheets - set(xls.sheet_names)
    if missing_sheets:
        errors.append(f"Feuille(s) obligatoire(s) absente(s) : {missing_sheets}")
        return {"valide": False, "erreurs_bloquantes": errors, "avertissements": warnings,
                "pyxform_disponible": pyxform_result["disponible"]}

    survey_df = pd.read_excel(xls, sheet_name="survey")
    choices_df = pd.read_excel(xls, sheet_name="choices")
    settings_df = pd.read_excel(xls, sheet_name="settings")

    if "name" not in survey_df.columns or "type" not in survey_df.columns:
        errors.append("La feuille 'survey' doit contenir au minimum les colonnes 'type' et 'name'")
        return {"valide": False, "erreurs_bloquantes": errors, "avertissements": warnings,
                "pyxform_disponible": pyxform_result["disponible"]}

    names = survey_df[survey_df["type"].astype(str).str.strip().isin(
        ["text", "integer", "decimal", "date", "datetime", "time", "geopoint", "calculate", "note"]
        + [t for t in survey_df["type"].astype(str) if t.startswith(("select_one ", "select_multiple "))]
    )]["name"].dropna().astype(str)
    duplicates = names[names.duplicated()].unique().tolist()
    if duplicates:
        errors.append(f"Nom(s) de question dupliques dans 'survey' : {duplicates}")

    choice_lists_available = set(choices_df["list_name"].dropna().astype(str)) if "list_name" in choices_df.columns else set()
    known_field_names = set(survey_df["name"].dropna().astype(str))

    open_repeats = 0
    for idx, row in survey_df.iterrows():
        type_raw = str(row.get("type", "")).strip()
        type_base = type_raw.split()[0] if type_raw and type_raw.split()[0] != "begin" and not type_raw.startswith("begin repeat") else type_raw
        if type_raw.startswith("begin repeat"):
            type_base = "begin repeat"
            open_repeats += 1
        elif type_raw.startswith("end repeat"):
            type_base = "end repeat"
            open_repeats -= 1
        else:
            type_base = type_raw.split()[0] if type_raw else ""
        name = row.get("name", f"ligne_{idx}")

        if type_base not in VALID_BASE_TYPES:
            errors.append(f"Question '{name}' : type '{type_base}' non reconnu dans les types XLSForm supportes")
            continue

        if type_base in ("select_one", "select_multiple"):
            parts = type_raw.split(maxsplit=1)
            if len(parts) < 2:
                errors.append(f"Question '{name}' : type '{type_base}' sans reference de liste de choix")
                continue
            list_name = parts[1].strip()
            if list_name not in choice_lists_available:
                errors.append(f"Question '{name}' : reference une liste de choix '{list_name}' absente de la feuille 'choices'")
            else:
                n_choices = len(choices_df[choices_df["list_name"] == list_name])
                if n_choices == 0:
                    errors.append(f"Question '{name}' : liste de choix '{list_name}' existe mais est vide")

        relevant_expr = row.get("relevant") if "relevant" in survey_df.columns else None
        if relevant_expr and not pd.isna(relevant_expr):
            referenced = re.findall(r"\$\{([a-zA-Z0-9_]+)\}", str(relevant_expr))
            for ref in referenced:
                if ref not in known_field_names:
                    errors.append(f"Question '{name}' : expression relevant reference un champ inexistant '${{{ref}}}'")

        if pd.isna(row.get("label")) or str(row.get("label", "")).strip() == "":
            if type_base not in ("start", "end", "today", "deviceid", "username", "begin repeat", "end repeat"):
                warnings.append(f"Question '{name}' : label vide -- a completer avant diffusion aux enqueteurs")

    if open_repeats != 0:
        errors.append(f"Groupe(s) 'begin repeat' non ferme(s) correctement (ecart={open_repeats}) -- structure de repetition invalide")

    if settings_df.empty or "form_title" not in settings_df.columns:
        errors.append("Feuille 'settings' doit contenir au moins 'form_title'")
    elif settings_df["form_title"].isna().all():
        errors.append("'form_title' est vide dans 'settings'")

    n_questions = len(survey_df[~survey_df["type"].astype(str).str.split().str[0].isin(
        ["start", "end", "today", "deviceid", "username", "begin", "end"]
    )])
    if n_questions == 0:
        errors.append("Aucune question (hors start/end/metadonnees) dans le formulaire")

    return {
        "valide": len(errors) == 0,
        "n_questions": int(n_questions),
        "erreurs_bloquantes": errors,
        "avertissements": warnings,
        "pyxform_disponible": pyxform_result["disponible"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsform_file")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    xlsform_path = Path(args.xlsform_file)
    if not xlsform_path.exists():
        print(f"Fichier introuvable : {xlsform_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"validation_xlsform_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    result = validate_xlsform(xlsform_path)

    for e in result.get("erreurs_bloquantes", []):
        logger.error(e)
    for w in result.get("avertissements", []):
        logger.warning(w)

    logger.info("Validation terminee : valide=%s, %d erreur(s) bloquante(s), %d avertissement(s)",
                result["valide"], len(result.get("erreurs_bloquantes", [])), len(result.get("avertissements", [])))

    out_path = run_dir / "validation_xlsform.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK - validation: {out_path}")
    print(f"Resultat : {'VALIDE' if result['valide'] else 'INVALIDE -- NE PAS APPROUVER/DEPLOYER'}")
    return 0 if result["valide"] else 1


if __name__ == "__main__":
    sys.exit(main())
