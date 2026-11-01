#!/usr/bin/env python3
"""
Analyse un Termes de Reference (ToR) texte/Word et extrait les elements
structurants par detection de sections usuelles.

Deux passes, jamais confondues (meme principe que
survey_intelligence/project_intake.py) :
1. EXTRACTION DETERMINISTE -- jamais d'invention, section absente =
   "non_trouve" explicite.
2. PROPOSITION IA (Claude, optionnelle si ANTHROPIC_API_KEY configuree)
   -- pour les sections non detectees, propose une formulation
   plausible basee sur le texte integral, toujours marquee
   "proposition_ia" et a valider, jamais fusionnee avec une section
   reellement trouvee dans le document.

Usage:
    python tor_analyzer.py <fichier_tor.txt|.docx|.pdf> --output-dir output/
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

# Patterns ancres en debut de ligne (re.MULTILINE), deux-points
# obligatoire -- evite qu'un mot generique matche en plein milieu
# d'une phrase (meme bug trouve et corrige dans
# survey_intelligence/project_intake.py : "region" capturait du texte
# hors contexte sans cet ancrage).
SECTION_PATTERNS = {
    "objectifs": r"^\s*(?:objectifs?|but de la mission|purpose)\s*[:\-]\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "livrables": r"^\s*(?:livrables?|deliverables?|produits attendus)\s*[:\-]\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "echeance": r"^\s*(?:date limite|deadline|echeance|duree de la mission|delai)\s*[:\-]\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "budget_plafond": r"^\s*(?:budget|enveloppe financiere|montant maximum)\s*[:\-]\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
    "qualifications_requises": r"^\s*(?:qualifications?(?:\s+requises?)?|profil recherche|competences requises)\s*[:\-]\s*\n?(.+?)(?=\n[A-Z].{0,40}[:\-]|\Z)",
}

SECTION_LABELS = {
    "objectifs": "Objectifs de la mission",
    "livrables": "Livrables attendus",
    "echeance": "Echeance / duree",
    "budget_plafond": "Budget / enveloppe (si mentionne dans le ToR)",
    "qualifications_requises": "Qualifications requises",
}


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def extract_sections(text: str) -> dict:
    result = {}
    for key, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if match:
            content = match.group(1).strip()
            # Tronque a 2000 caracteres pour eviter de capturer tout le document en cas de pattern trop permissif
            result[key] = content[:2000] if content else None
        else:
            result[key] = None
    return result


def propose_missing_sections_with_ia(text: str, missing_keys: list[str]) -> dict:
    """Propose une formulation plausible pour les sections non
    detectees, basee UNIQUEMENT sur le texte reel du ToR. Chaque
    proposition porte sa justification (citation/paraphrase du
    passage source) -- si rien d'exploitable n'existe dans le texte,
    le modele doit le dire plutot que d'inventer.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))
    from llm_connector import get_claude_connector  # noqa: E402

    connector = get_claude_connector()
    labels_manquants = {k: SECTION_LABELS[k] for k in missing_keys}
    system_prompt = (
        "Tu es un assistant d'analyse de termes de reference (ToR) pour des missions de "
        "conseil/expertise. On te donne le texte integral d'un ToR et une liste de sections "
        "qui n'ont PAS ete detectees automatiquement par une extraction par mots-cles.\n\n"
        "Pour chaque section manquante, propose UNE formulation plausible basee UNIQUEMENT sur "
        "le contenu reel du texte fourni. Si le texte ne contient vraiment aucune information "
        "exploitable pour une section, dis-le explicitement plutot que d'inventer.\n\n"
        "Reponds UNIQUEMENT en JSON valide, sans texte autour, format exact :\n"
        '{"propositions": {"<cle>": {"texte_propose": "...", "confiance": "haute|moyenne|basse", '
        '"justification": "citation ou paraphrase courte du passage source, ou \'aucune information trouvee\'"}}}'
    )
    user_content = (
        f"Sections a proposer (cle -> libelle) :\n{json.dumps(labels_manquants, ensure_ascii=False, indent=2)}\n\n"
        f"Texte integral du ToR :\n{text[:15000]}"
    )
    result = connector.generate_json(system_prompt, user_content)
    propositions = result.get("propositions", {})
    return {k: v for k, v in propositions.items() if k in missing_keys}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tor_file")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--no-ia", action="store_true")
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
    missing = [k for k, v in sections.items() if v is None]
    for key in missing:
        logger.warning("Section non trouvee : %s -- ne pas deviner, verifier le ToR manuellement", key)

    propositions_ia = {}
    ia_erreur = None
    if missing and not args.no_ia:
        try:
            propositions_ia = propose_missing_sections_with_ia(text, missing)
            logger.info("Propositions IA generees pour %d/%d section(s) manquante(s)", len(propositions_ia), len(missing))
        except Exception as exc:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))
            from llm_connector import LLMNotConfiguredError
            if isinstance(exc, LLMNotConfiguredError):
                logger.info("Propositions IA desactivees : %s", exc)
            else:
                ia_erreur = str(exc)[:500]
                logger.warning("Propositions IA indisponibles (echec appel) : %s", ia_erreur)

    still_missing = [k for k in missing if k not in propositions_ia]

    analysis = {
        "fichier_source": str(tor_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "sections": sections,
        "propositions_ia": propositions_ia,
        "sections_non_trouvees": missing,
        "sections_reellement_manquantes": still_missing,
        "erreur_ia": ia_erreur,
        "avertissement": (
            "Les 'sections' sont detectees directement dans le texte source. Les "
            "'propositions_ia' sont des SUGGESTIONS, jamais confirmees -- a valider avant usage. "
            "Les 'sections_reellement_manquantes' doivent etre verifiees manuellement."
        ),
    }

    out_path = run_dir / "tor_analysis.json"
    out_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Analyse ecrite : %s (%d/%d section(s) detectee(s), %d proposition(s) IA)",
                out_path, n_found, len(sections), len(propositions_ia))
    print(f"OK - analyse: {out_path}")
    if still_missing:
        print(f"ATTENTION : {len(still_missing)} section(s) reellement manquante(s) : {still_missing}")
    if propositions_ia:
        print(f"INFO : {len(propositions_ia)} proposition(s) IA generee(s) -- a valider")
    return 0


if __name__ == "__main__":
    sys.exit(main())
