#!/usr/bin/env python3
"""
Structure une description de projet (TDR, note de cadrage...) en
elements explicites.

Deux passes complementaires, jamais confondues :
1. EXTRACTION DETERMINISTE (sections/mots-cles explicites du texte)
   -- ce que ce script faisait deja. Jamais d'invention : un element
   non trouve par cette passe reste `null`.
2. PROPOSITION IA (Claude, optionnelle -- activee uniquement si
   ANTHROPIC_API_KEY est configuree) -- pour les elements non
   detectes par la passe 1, Claude lit le texte complet du TDR et
   PROPOSE une formulation plausible, explicitement marquee
   "origine": "proposition_ia" et à valider par l'utilisateur. Ce
   n'est jamais ecrit comme un fait detecte -- toujours distinct
   visuellement dans le .docx et structurellement dans le JSON.

Sorties :
- project_structured.json : donnees completes (detecte + propositions
  IA + lacunes residuelles), pour chainage avec les agents suivants.
- cadrage_projet.docx : document lisible humain, sections "Detecte
  dans le TDR" vs "Proposition IA (a valider)" vs "A completer" bien
  distinguees visuellement (couleurs/encadres).

Usage:
    python project_intake.py sample_data/description_projet_test.txt --output-dir output/
    python project_intake.py tdr.pdf --output-dir output/ --no-ia   # desactive la passe IA
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger("survey_intelligence.project_intake")

# Chaque element : liste de patterns regex (section explicite "Label:")
# ET mots-cles de secours si aucune section explicite n'est trouvee.
# Chaque element : pattern ancre en DEBUT DE LIGNE (re.MULTILINE),
# avec deux-points obligatoire -- evite qu'un mot generique comme
# "region" matche n'importe ou en plein milieu d'une phrase (bug
# reel trouve : "region" dans "la region de San-Pedro souffre..."
# etait capture comme zone_geographique a la place du vrai en-tete
# "Zone geographique :").
SECTION_PATTERNS = {
    "contexte_problematique": r"^\s*(?:contexte|problematique|probleme)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "objectifs_resultats": r"^\s*(?:objectifs?|resultats? attendus?)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "beneficiaires_population": r"^\s*(?:beneficiaires?|population cible)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "zone_geographique": r"^\s*(?:zone geographique|localisation|zone d'intervention)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "activites_duree": r"^\s*(?:activites?|duree du projet|calendrier)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "indicateurs_existants": r"^\s*(?:indicateurs? (?:deja )?definis?|indicateurs? existants?)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
    "besoins_collecte_suivi": r"^\s*(?:besoins? de collecte|suivi et reporting|collecte et suivi)\s*[:\-]\s*\n?(.+?)(?=\n[A-ZÉÀ].{0,40}[:\-]|\Z)",
}

REQUIRED_ELEMENTS = list(SECTION_PATTERNS.keys())

ELEMENT_LABELS = {
    "contexte_problematique": "Contexte / problematique",
    "objectifs_resultats": "Objectifs / resultats attendus",
    "beneficiaires_population": "Beneficiaires / population cible",
    "zone_geographique": "Zone geographique",
    "activites_duree": "Activites / duree du projet",
    "indicateurs_existants": "Indicateurs deja definis",
    "besoins_collecte_suivi": "Besoins de collecte et de suivi",
}


def extract_elements(text: str) -> dict:
    """Passe 1 -- extraction deterministe par mots-cles/sections.
    Jamais d'invention : un element non trouve reste None.
    """
    result = {}
    for key, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if match:
            content = match.group(1).strip()
            result[key] = content[:3000] if content else None
        else:
            result[key] = None
    return result


def propose_missing_elements_with_ia(text: str, missing_keys: list[str]) -> dict:
    """Passe 2 (optionnelle) -- demande a Claude de proposer une
    formulation plausible pour chaque element non detecte par la
    passe 1, a partir du texte integral du TDR. Chaque proposition
    est retournee avec son origine explicite -- jamais fusionnee
    silencieusement avec une donnee detectee.

    Leve LLMNotConfiguredError si ANTHROPIC_API_KEY est absente --
    l'appelant doit alors continuer sans propositions IA, jamais
    simuler un succes.
    """
    from llm_connector import get_claude_connector

    connector = get_claude_connector()

    labels_manquants = {k: ELEMENT_LABELS[k] for k in missing_keys}
    system_prompt = (
        "Tu es un assistant d'analyse de termes de reference (TDR) pour des projets "
        "de developpement/geospatial/enquete terrain. On te donne le texte integral d'un "
        "TDR et une liste d'elements de cadrage qui n'ont PAS ete detectes automatiquement "
        "par une extraction par mots-cles (donc probablement presents dans le texte mais "
        "formules differemment, ou reellement absents du document).\n\n"
        "Pour chaque element manquant, propose UNE formulation plausible basee UNIQUEMENT "
        "sur le contenu reel du texte fourni -- jamais une donnee generique ou inventee hors "
        "contexte. Si le texte ne contient vraiment aucune information exploitable pour un "
        "element donne, dis-le explicitement plutot que d'inventer.\n\n"
        "Reponds UNIQUEMENT en JSON valide, sans texte autour, format exact :\n"
        '{"propositions": {"<cle_element>": {"texte_propose": "...", "confiance": "haute|moyenne|basse", '
        '"justification": "citation ou paraphrase courte du passage source, ou \'aucune information trouvee\'"}}}'
    )
    user_content = (
        f"Elements a proposer (cle technique -> libelle) :\n{json.dumps(labels_manquants, ensure_ascii=False, indent=2)}\n\n"
        f"Texte integral du TDR :\n{text[:15000]}"
    )

    result = connector.generate_json(system_prompt, user_content)
    propositions = result.get("propositions", {})
    # Ne garder que les cles reellement demandees -- jamais accepter
    # une cle inventee par le modele hors de la liste fournie.
    return {k: v for k, v in propositions.items() if k in missing_keys}


def build_docx(structured: dict, output_path: Path) -> None:
    """Genere un document Word lisible, avec distinction visuelle
    claire entre elements detectes, propositions IA (a valider) et
    elements reellement manquants.
    """
    doc = Document()

    title = doc.add_heading("Cadrage de projet -- document genere automatiquement", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta = doc.add_paragraph()
    meta.add_run(f"Fichier source : {structured['fichier_source']}\n").italic = True
    meta.add_run(f"Date d'analyse : {structured['date_analyse']}\n").italic = True
    doc.add_paragraph(
        "Ce document distingue trois categories : le texte DETECTE directement dans le "
        "document source, les PROPOSITIONS generees par IA (a valider explicitement avant "
        "usage), et les elements reellement ABSENTS a completer manuellement."
    )

    for key in REQUIRED_ELEMENTS:
        label = ELEMENT_LABELS[key]
        doc.add_heading(label, level=1)

        detected = structured["elements"].get(key)
        proposition = structured.get("propositions_ia", {}).get(key)

        if detected:
            p = doc.add_paragraph()
            run = p.add_run("[DETECTE DANS LE DOCUMENT]  ")
            run.bold = True
            run.font.color.rgb = RGBColor(0x1F, 0x7A, 0x1F)
            p.add_run(detected)
        elif proposition:
            p = doc.add_paragraph()
            run = p.add_run(
                f"[PROPOSITION IA -- CONFIANCE {proposition.get('confiance', 'inconnue').upper()} -- A VALIDER]  "
            )
            run.bold = True
            run.font.color.rgb = RGBColor(0xB8, 0x6A, 0x00)
            p.add_run(proposition.get("texte_propose", ""))
            just = doc.add_paragraph()
            just.add_run("Justification du modele : ").italic = True
            just.add_run(proposition.get("justification", "")).italic = True
        else:
            p = doc.add_paragraph()
            run = p.add_run("[ABSENT -- A RENSEIGNER MANUELLEMENT]")
            run.bold = True
            run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)

    doc.add_heading("Avertissement", level=1)
    doc.add_paragraph(
        "Les elements marques [PROPOSITION IA] n'ont jamais ete confirmes par une source "
        "humaine -- ils doivent etre valides, corriges ou rejetes avant toute utilisation "
        "operationnelle (construction d'indicateurs, formulaire de collecte, etc.)."
    )

    doc.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("description_file")
    ap.add_argument("--output-dir", default="output")
    ap.add_argument("--no-ia", action="store_true", help="Desactive la passe de proposition IA meme si ANTHROPIC_API_KEY est configuree")
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

    # Extraction du texte -- gere .txt directement ; .pdf/.docx via
    # les bibliotheques deja presentes dans requirements-agents.txt
    # si disponibles, sinon erreur explicite (jamais de texte vide
    # silencieux).
    suffix = desc_path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            print("Lecture PDF requiert 'pypdf' -- pip install pypdf", file=sys.stderr)
            return 1
        reader = PdfReader(str(desc_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".docx":
        doc_in = Document(str(desc_path))
        text = "\n".join(p.text for p in doc_in.paragraphs)
    else:
        text = desc_path.read_text(encoding="utf-8", errors="replace")

    elements = extract_elements(text)
    missing = [k for k, v in elements.items() if v is None]
    for m in missing:
        logger.warning("Element non detecte dans la description : %s -- a demander explicitement a l'utilisateur", m)

    propositions_ia = {}
    ia_erreur = None
    if missing and not args.no_ia:
        try:
            propositions_ia = propose_missing_elements_with_ia(text, missing)
            logger.info("Propositions IA generees pour %d/%d element(s) manquant(s)", len(propositions_ia), len(missing))
        except Exception as exc:
            from llm_connector import LLMNotConfiguredError
            if isinstance(exc, LLMNotConfiguredError):
                logger.info("Propositions IA desactivees : %s", exc)
            else:
                ia_erreur = str(exc)[:500]
                logger.warning("Propositions IA indisponibles (echec appel) : %s", ia_erreur)

    still_missing = [k for k in missing if k not in propositions_ia]

    structured = {
        "fichier_source": str(desc_path),
        "date_analyse": datetime.utcnow().isoformat() + "Z",
        "elements": elements,
        "propositions_ia": propositions_ia,
        "elements_non_detectes": missing,
        "elements_reellement_manquants": still_missing,
        "erreur_ia": ia_erreur,
        "avertissement": (
            "Les elements 'elements' sont detectes directement dans le texte source. "
            "Les elements 'propositions_ia' sont des SUGGESTIONS generees par IA, jamais "
            "confirmees -- a valider explicitement avant usage. "
            "Les elements 'elements_reellement_manquants' doivent etre demandes a l'utilisateur."
        ),
    }

    out_path = run_dir / "project_structured.json"
    out_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    docx_path = run_dir / "cadrage_projet.docx"
    build_docx(structured, docx_path)

    n_detected = len(REQUIRED_ELEMENTS) - len(missing)
    logger.info(
        "Projet structure : %d/%d detecte(s), %d proposition(s) IA, %d reellement manquant(s)",
        n_detected, len(REQUIRED_ELEMENTS), len(propositions_ia), len(still_missing),
    )
    print(f"OK - projet structure (JSON): {out_path}")
    print(f"OK - cadrage lisible (Word): {docx_path}")
    if still_missing:
        print(f"ATTENTION : {len(still_missing)} element(s) reellement manquant(s), a demander a l'utilisateur : {still_missing}")
    if propositions_ia:
        print(f"INFO : {len(propositions_ia)} proposition(s) IA generee(s) -- a valider dans le document Word")
    return 0


if __name__ == "__main__":
    sys.exit(main())
