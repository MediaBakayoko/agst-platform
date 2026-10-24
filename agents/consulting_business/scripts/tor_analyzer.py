#!/usr/bin/env python3
"""
Analyse un Termes de Reference (ToR) texte/Word et extrait les elements
structurants par detection de sections usuelles.

Ne devine jamais le contenu d'une section absente -- la signale comme
"non_trouve" dans la sortie JSON.

Usage:
    python tor_analyzer.py <fichier_tor.txt|.docx> --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("consulting_business.tor_analyzer")

SECTION_PATTERNS = {
    "objectifs": r"(?:objectifs?|but de la mission|purpose)\s*[:\-]?\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "livrables": r"(?:livrables?|deliverables?|produits attendus)\s*[:\-]?\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "echeance": r"(?:date limite|deadline|echeance|duree de la mission|delai)\s*[:\-]?\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "budget_plafond": r"(?:budget|enveloppe financiere|montant maximum)\s*[:\-]?\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "qualifications_requises": r"(?:qualifications?|profil recherche|competences requises)\s*[:\-]?\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
}


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


def extract_sections(text: str) -> dict:
    result = {}
    for key, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Tronque a 2000 caracteres pour eviter de capturer tout le document en cas de pattern trop permissif
            result[key] = content[:2000] if content else None
        else:
            result[key] = None
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tor_file")
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    tor_path = Path(args.tor_file)
    if not tor_path.exists():
        print(f"Fichier introuvable : {tor_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{tor_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    text = read_text(tor_path)
    sections = extract_sections(text)

    n_found = sum(1 for v in sections.values() if v)
    n_missing = len(sections) - n_found
    logger.info("ToR analyse : %d section(s) trouvee(s), %d non trouvee(s)", n_found, n_missing)
    for key, val in sections.items():
        if val is None:
            logger.warning("Section non trouvee : %s -- ne pas deviner, verifier le ToR manuellement", key)

    analysis = {
        "fichier_source": str(tor_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
        "sections_non_trouvees": [k for k, v in sections.items() if v is None],
        "avertissement": (
            "Les sections non trouvees doivent etre verifiees manuellement dans le "
            "document original -- cet outil ne devine jamais un contenu absent."
        ),
    }

    out_path = run_dir / "tor_analysis.json"
    out_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Analyse ecrite : %s", out_path)
    print(f"OK - analyse: {out_path}")
    if n_missing:
        print(f"ATTENTION : {n_missing} section(s) non detectee(s) -- verifier manuellement : {analysis['sections_non_trouvees']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
