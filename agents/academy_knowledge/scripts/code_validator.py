#!/usr/bin/env python3
"""
Execute reellement un extrait de code Python dans un sous-processus
isole et rapporte succes/echec effectif. Ne declare jamais un exemple
"valide" sans l'avoir execute.

Usage:
    python code_validator.py sample_data/exemple_code.py --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("academy_knowledge.code_validator")


def validate_code(script_path: Path, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=timeout,
        )
        return {
            "fichier": str(script_path),
            "execute_avec_succes": result.returncode == 0,
            "code_retour": result.returncode,
            "stdout": result.stdout[-3000:],
            "stderr": result.stderr[-3000:],
        }
    except subprocess.TimeoutExpired:
        return {
            "fichier": str(script_path),
            "execute_avec_succes": False,
            "erreur": f"Timeout apres {timeout}s -- a verifier (boucle infinie ou traitement trop long pour un exemple pedagogique)",
        }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code_file")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    code_path = Path(args.code_file)
    if not code_path.exists():
        print(f"Fichier introuvable : {code_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"validation_{code_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    result = validate_code(code_path, timeout=args.timeout)

    if result["execute_avec_succes"]:
        logger.info("Code execute avec succes : %s", code_path)
    else:
        logger.warning("Echec d'execution : %s -- NE PAS PUBLIER cet exemple sans correction", code_path)

    out_path = run_dir / "validation.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK - validation: {out_path}")
    print(f"Resultat : {'SUCCES' if result['execute_avec_succes'] else 'ECHEC -- ne pas publier tel quel'}")
    return 0 if result["execute_avec_succes"] else 1


if __name__ == "__main__":
    sys.exit(main())
