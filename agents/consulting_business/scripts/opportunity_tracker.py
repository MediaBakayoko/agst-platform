#!/usr/bin/env python3
"""
Registre des opportunites commerciales (CSV). Toute addition/mise a
jour est faite explicitement par commande -- jamais d'ajout automatique
d'une opportunite non confirmee par l'utilisateur.

Usage:
    python opportunity_tracker.py add --registry registre.csv \
        --client "Nom" --titre "Intitule" --echeance 2026-12-01 \
        --montant-hypothese 0 --statut "a_preparer"

    python opportunity_tracker.py list --registry registre.csv
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = ["date_ajout", "client", "titre", "echeance", "montant_hypothese_fcfa", "statut", "probabilite"]
VALID_STATUTS = {"a_preparer", "soumise", "en_negociation", "gagnee", "perdue", "abandonnee"}


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
        "client": args.client,
        "titre": args.titre,
        "echeance": args.echeance,
        "montant_hypothese_fcfa": args.montant_hypothese,
        "statut": args.statut,
        "probabilite": args.probabilite if args.probabilite is not None else "",
    }
    if df.empty:
        df = pd.DataFrame([new_row])
    else:
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(registry_path, index=False)
    print(f"OK - opportunite ajoutee au registre : {registry_path} ({len(df)} ligne(s) au total)")
    return 0


def cmd_list(args) -> int:
    registry_path = Path(args.registry)
    df = load_registry(registry_path)
    if df.empty:
        print("Registre vide.")
        return 0
    print(df.to_string(index=False))
    print(f"\nTotal : {len(df)} opportunite(s)")
    for statut in sorted(df["statut"].dropna().unique()):
        print(f"  {statut}: {(df['statut'] == statut).sum()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add")
    add_p.add_argument("--registry", required=True)
    add_p.add_argument("--client", required=True)
    add_p.add_argument("--titre", required=True)
    add_p.add_argument("--echeance", required=True)
    add_p.add_argument("--montant-hypothese", type=float, default=0, dest="montant_hypothese")
    add_p.add_argument("--statut", required=True)
    add_p.add_argument("--probabilite", type=float, default=None)

    list_p = sub.add_parser("list")
    list_p.add_argument("--registry", required=True)

    args = ap.parse_args()
    if args.command == "add":
        return cmd_add(args)
    return cmd_list(args)


if __name__ == "__main__":
    sys.exit(main())
