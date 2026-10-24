#!/usr/bin/env python3
"""
Genere un exercice pratique structure. Verifie que les donnees
mentionnees existent reellement avant de les referencer dans
l'exercice -- ne pretend jamais qu'un fichier de donnees est disponible
s'il ne l'est pas.

Usage:
    python exercise_builder.py --titre "..." --contexte "..." \
        --donnees-requises sample_data/exemple.geojson --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("academy_knowledge.exercise_builder")


def build_exercise(titre: str, contexte: str, donnees_requises: list[str]) -> dict:
    data_checks = []
    for d in donnees_requises:
        path = Path(d)
        exists = path.exists()
        data_checks.append({"fichier": d, "existe": exists})
        if not exists:
            logger.warning("Fichier de donnees reference mais introuvable : %s -- a fournir avant publication", d)

    missing = [c["fichier"] for c in data_checks if not c["existe"]]

    return {
        "titre": titre,
        "contexte": contexte,
        "donnees_requises": data_checks,
        "donnees_manquantes": missing,
        "structure": {
            "introduction": f"Contexte : {contexte}",
            "etapes": [
                "[A COMPLETER] Etape 1 : ...",
                "[A COMPLETER] Etape 2 : ...",
                "[A COMPLETER] Etape 3 : ...",
            ],
            "critere_de_reussite": "[A DEFINIR] Resultat attendu verifiable par l'apprenant",
        },
        "statut": (
            "brouillon -- donnees manquantes a fournir" if missing
            else "brouillon -- etapes et critere a rediger, relecture instructeur requise"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titre", required=True)
    ap.add_argument("--contexte", required=True)
    ap.add_argument("--donnees-requises", default="", help="Chemins de fichiers separes par des virgules")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"exercice_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    donnees = [d.strip() for d in args.donnees_requises.split(",") if d.strip()]
    exercise = build_exercise(args.titre, args.contexte, donnees)

    out_path = run_dir / "exercice.json"
    out_path.write_text(json.dumps(exercise, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Exercice genere : statut=%s, %d fichier(s) manquant(s)", exercise["statut"], len(exercise["donnees_manquantes"]))
    print(f"OK - exercice: {out_path}")
    if exercise["donnees_manquantes"]:
        print(f"ATTENTION : fichier(s) de donnees manquant(s) : {exercise['donnees_manquantes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
