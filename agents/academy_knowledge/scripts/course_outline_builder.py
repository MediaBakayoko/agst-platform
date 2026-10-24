#!/usr/bin/env python3
"""
Genere un plan de cours structure a partir d'objectifs d'apprentissage.
Signale tout objectif trop vague pour etre traduit en module concret --
ne genere jamais un contenu detaille a partir d'un objectif ambigu.

Usage:
    python course_outline_builder.py --titre "..." --niveau debutant \
        --objectifs "obj1,obj2,obj3" --duree-heures 12 --output-dir output/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("academy_knowledge.course_outline_builder")

VALID_LEVELS = {"debutant", "intermediaire", "avance"}
VAGUE_VERBS = {"comprendre", "connaitre", "savoir", "apprehender", "decouvrir"}
CONCRETE_VERBS = {"calculer", "exporter", "creer", "produire", "configurer", "appliquer", "analyser", "construire", "comparer"}


def assess_objective_clarity(objectif: str) -> dict:
    """Signale un objectif purement vague (verbe flou, pas de livrable
    identifiable) plutot que de generer un module detaille dessus.
    """
    lower = objectif.lower()
    has_vague_only = any(v in lower for v in VAGUE_VERBS) and not any(v in lower for v in CONCRETE_VERBS)
    return {
        "objectif": objectif,
        "clair": not has_vague_only,
        "note": None if not has_vague_only else (
            "Objectif formule de maniere vague (verbe de comprehension sans livrable concret) -- "
            "a reformuler en action verifiable (ex: 'Calculer un NDVI' plutot que 'Comprendre le NDVI')"
        ),
    }


def build_outline(titre: str, niveau: str, objectifs: list[str], duree_heures: float) -> dict:
    issues = []
    if niveau not in VALID_LEVELS:
        issues.append(f"Niveau '{niveau}' invalide (attendu : {sorted(VALID_LEVELS)})")

    assessed = [assess_objective_clarity(o) for o in objectifs]
    n_vagues = sum(1 for a in assessed if not a["clair"])

    n_modules = max(len(objectifs), 1)
    duree_par_module = round(duree_heures / n_modules, 1) if n_modules else duree_heures

    modules = []
    for i, obj in enumerate(objectifs, start=1):
        modules.append({
            "module": i,
            "titre_module": f"Module {i} : {obj}",
            "duree_heures_indicative": duree_par_module,
            "objectif_source": obj,
        })

    return {
        "titre_cours": titre,
        "niveau": niveau,
        "duree_totale_heures": duree_heures,
        "n_modules": n_modules,
        "modules": modules,
        "evaluation_objectifs": assessed,
        "n_objectifs_vagues": n_vagues,
        "problemes_structurels": issues,
        "statut": "brouillon -- relecture par un instructeur qualifie requise avant diffusion",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titre", required=True)
    ap.add_argument("--niveau", required=True)
    ap.add_argument("--objectifs", required=True, help="Objectifs separes par des virgules")
    ap.add_argument("--duree-heures", type=float, required=True)
    ap.add_argument("--output-dir", default="output")
    args = ap.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"plan_cours_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                         handlers=[logging.FileHandler(run_dir / "journal.log", encoding="utf-8"), logging.StreamHandler()])

    objectifs = [o.strip() for o in args.objectifs.split(",") if o.strip()]
    outline = build_outline(args.titre, args.niveau, objectifs, args.duree_heures)

    for obj_eval in outline["evaluation_objectifs"]:
        if not obj_eval["clair"]:
            logger.warning("Objectif vague : %s -- %s", obj_eval["objectif"], obj_eval["note"])
    for issue in outline["problemes_structurels"]:
        logger.warning(issue)

    out_path = run_dir / "plan_cours.json"
    out_path.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Plan de cours genere : %d module(s), %d objectif(s) vague(s)", outline["n_modules"], outline["n_objectifs_vagues"])
    print(f"OK - plan de cours: {out_path}")
    if outline["n_objectifs_vagues"]:
        print(f"ATTENTION : {outline['n_objectifs_vagues']} objectif(s) a reformuler avant redaction du contenu")
    return 0


if __name__ == "__main__":
    sys.exit(main())
