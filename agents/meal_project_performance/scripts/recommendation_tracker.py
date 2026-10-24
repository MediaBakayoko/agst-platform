#!/usr/bin/env python3
"""
Registre des recommandations et actions correctives (CSV). Chaque
ajout est explicite -- jamais de recommandation generee ou ajoutee
automatiquement sans commande de l'utilisateur.

Usage:
    python recommendation_tracker.py add --registry registre.csv \
        --constat "..." --recommandation "..." --responsable "..." \
        --echeance 2026-12-01 --statut ouverte

    python recommendation_tracker.py list --registry registre.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = ["date_ajout", "constat", "recommandation", "responsable", "echeance", "statut"]
VALID_STATUTS = {"ouverte", "en_cours", "cloturee", "abandonnee"}


def load_registry(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=COLUMNS)


def cmd_add(args) -> int:
    registry_path = Path(args.registry)
    df = load_registry(registry_path)

    if args.statut not in VALID_STATUTS:
        print(f"Statut invalide : {args.statut}. Valeurs possibles : {sorted(VALID_STATUTS)}", file=sys.stderr)
        return 1

    new_row = {
        "date_ajout": datetime.now().strftime("%Y-%m-%d"),
        "constat": args.constat,
        "recommandation": args.recommandation,
        "responsable": args.responsable,
        "echeance": args.echeance,
        "statut": args.statut,
    }
    if df.empty:
        df = pd.DataFrame([new_row])
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(registry_path, index=False)
    print(f"OK - recommandation ajoutee : {registry_path} ({len(df)} ligne(s) au total)")
    return 0


def cmd_list(args) -> int:
    registry_path = Path(args.registry)
    df = load_registry(registry_path)
    if df.empty:
        print("Registre vide.")
        return 0
    print(df.to_string(index=False))
    n_ouvertes = (df["statut"] == "ouverte").sum()
    print(f"\n{n_ouvertes} recommandation(s) ouverte(s) sur {len(df)} au total")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("--registry", required=True)
    add_p.add_argument("--constat", required=True)
    add_p.add_argument("--recommandation", required=True)
    add_p.add_argument("--responsable", required=True)
    add_p.add_argument("--echeance", required=True)
    add_p.add_argument("--statut", required=True)

    list_p = sub.add_parser("list")
    list_p.add_argument("--registry", required=True)

    args = ap.parse_args()
    return cmd_add(args) if args.command == "add" else cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
