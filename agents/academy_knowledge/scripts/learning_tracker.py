#!/usr/bin/env python3
"""
Registre de suivi des apprenants (CSV). Jamais de publication
automatique -- ce registre reste local, a diffuser uniquement sur
autorisation explicite.

Usage:
    python learning_tracker.py add --registry suivi.csv \
        --apprenant "ID_001" --module "Intro GEE" --statut complete --note 85
    python learning_tracker.py list --registry suivi.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = ["date", "apprenant", "module", "statut", "note"]
VALID_STATUTS = {"inscrit", "en_cours", "complete", "abandonne"}


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
        "date": datetime.now().strftime("%Y-%m-%d"),
        "apprenant": args.apprenant,
        "module": args.module,
        "statut": args.statut,
        "note": args.note if args.note is not None else "",
    }
    df = pd.DataFrame([new_row]) if df.empty else pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(registry_path, index=False)
    print(f"OK - entree ajoutee : {registry_path} ({len(df)} ligne(s) au total)")
    print("RAPPEL : ces donnees d'apprenants ne doivent pas etre diffusees sans autorisation.")
    return 0


def cmd_list(args) -> int:
    df = load_registry(Path(args.registry))
    if df.empty:
        print("Registre vide.")
        return 0
    print(df.to_string(index=False))
    print(f"\n{len(df)} entree(s) au total")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("--registry", required=True)
    add_p.add_argument("--apprenant", required=True)
    add_p.add_argument("--module", required=True)
    add_p.add_argument("--statut", required=True)
    add_p.add_argument("--note", type=float, default=None)

    list_p = sub.add_parser("list")
    list_p.add_argument("--registry", required=True)

    args = ap.parse_args()
    return cmd_add(args) if args.command == "add" else cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
