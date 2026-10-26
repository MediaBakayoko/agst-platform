#!/usr/bin/env python3
"""
Structure une description de projet en langage naturel (texte libre)
en elements explicites, par detection de sections/mots-cles usuels.

Ne devine JAMAIS un element absent -- le signale dans
"elements_non_detectes" plutot que de l'inventer. C'est volontairement
une extraction heuristique simple (mots-cles / sections), pas un
LLM -- deterministe et traçable, conforme a la regle "aucune donnee
inventee".

Usage:
    python project_intake.py sample_data/description_projet_test.txt --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("survey_intelligence.project_intake")

# Chaque element : liste de patterns regex (section explicite "Label:")
# ET mots-cles de secours si aucune section explicite n'est trouvee.
SECTION_PATTERNS = {
    "contexte_problematique": r"(?:contexte|problematique|probleme)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "objectifs_resultats": r"(?:objectifs?|resultats? attendus?)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "beneficiaires_population": r"(?:beneficiaires?|population cible)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "zone_geographique": r"(?:zone geographique|localisation|region|zone d'intervention)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "activites_duree": r"(?:activites?|duree du projet|calendrier)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "indicateurs_existants": r"(?:indicateurs? (?:deja )?definis?|indicateurs? existants?)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "besoins_collecte_suivi": r"(?:besoins? de collecte|suivi et reporting|collecte et suivi)\s*[:\-]?\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
}

REQUIRED_ELEMENTS = list(SECTION_PATTERNS.keys())


def extract_elements(text: str) -> dict:
    result = {}
    for key, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            result[key] = content[:3000] if content else None
        else:
            result[key] = None
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("description_file")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    desc_path = Path(args.description_file)
    if not desc_path.exists():
        print(f"Fichier introuvable : {desc_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"project_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    text = desc_path.read_text(encoding="utf-8", errors="replace")
    elements = extract_elements(text)

    missing = [k for k, v in elements.items() if v is None]
    for m in missing:
        logger.warning("Element non detecte dans la description : %s -- a demander explicitement a l'utilisateur", m)

    structured = {
        "fichier_source": str(desc_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "elements": elements,
        "elements_non_detectes": missing,
        "avertissement": (
            "Les elements non detectes doivent etre demandes explicitement a "
            "l'utilisateur -- aucune valeur n'a ete devinee ou inventee."
        ),
    }

    out_path = run_dir / "project_structured.json"
    out_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Projet structure : %d/%d element(s) detecte(s)", len(REQUIRED_ELEMENTS) - len(missing), len(REQUIRED_ELEMENTS))
    print(f"OK - projet structure: {out_path}")
    if missing:
        print(f"ATTENTION : {len(missing)} element(s) manquant(s), a demander a l'utilisateur : {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
