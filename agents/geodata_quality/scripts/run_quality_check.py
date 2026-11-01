#!/usr/bin/env python3
"""
CLI du moteur GeoData Quality.

Usage:
    python run_quality_check.py <input_file> \
        --output-dir output/ \
        --required-fields nom,surface_ha \
        --numeric-fields surface_ha \
        --area-field surface_ha \
        --area-tolerance-pct 20 \
        --dup-tolerance-m 0 \
        --id-field id_parcelle

Ne modifie jamais le fichier d'entree. Toute sortie va dans un
sous-dossier horodate de --output-dir.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))

sys.path.insert(0, str(Path(__file__).parent))
from quality_checks import run_quality_checks  # noqa: E402


def _parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def generate_synthesis_with_ia(result) -> dict | None:
    """Demande a Claude une synthese en langage clair des anomalies
    REELLEMENT detectees (jamais une nouvelle anomalie inventee) --
    priorisation et explications pour un non-specialiste. Retourne
    None si aucune cle API configuree ou si l'appel echoue --
    l'appelant doit alors continuer avec le rapport habituel (tableau
    brut), jamais simuler une synthese.
    """
    from llm_connector import get_claude_connector, LLMNotConfiguredError, LLMAPIError

    summary_df = result.summary_by_type()
    if summary_df.empty:
        return None
    counts = summary_df.to_dict(orient="records")

    try:
        connector = get_claude_connector()
        system_prompt = (
            "Tu es un expert qualite de donnees geospatiales (SIG). On te donne le RELEVE REEL "
            "des anomalies detectees par un controle automatique (types et nombres, deja "
            "calcules -- tu ne dois JAMAIS inventer une anomalie ou un chiffre absent de cette "
            "liste). Ta tache : produire une synthese en langage clair pour un utilisateur "
            "non-specialiste SIG, avec priorisation des problemes a traiter en premier et une "
            "explication courte de pourquoi chaque type d'anomalie importe.\n\n"
            "Reponds UNIQUEMENT en JSON valide :\n"
            '{"synthese_generale": "2-3 phrases resumant l\'etat global", '
            '"priorites": [{"type_anomalie": "...", "pourquoi_important": "...", "action_recommandee": "..."}]}'
        )
        user_content = (
            f"Releve reel des anomalies (type_anomalie, severite, nombre) :\n{json.dumps(counts, ensure_ascii=False, indent=2)}\n"
            f"Nombre total d'entites analysees : {result.n_features}"
        )
        synthesis = connector.generate_json(system_prompt, user_content)
        # Verrou : ne garder que les priorites portant sur des types
        # d'anomalie reellement presents dans le releve -- jamais un
        # type invente par le modele.
        known_types = {c["type_anomalie"] for c in counts}
        synthesis["priorites"] = [p for p in synthesis.get("priorites", []) if p.get("type_anomalie") in known_types]
        return synthesis
    except LLMNotConfiguredError as exc:
        logging.getLogger("geodata_quality.cli").info("Synthese IA desactivee : %s", exc)
        return None
    except LLMAPIError as exc:
        logging.getLogger("geodata_quality.cli").warning("Synthese IA indisponible (echec appel) : %s", str(exc)[:500])
        return None


def write_excel_report(result, output_path: Path, synthesis: dict | None = None) -> None:
    wb = openpyxl.Workbook()

    # --- Feuille Resume ---
    ws = wb.active
    ws.title = "Resume"
    header_fill = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    rows = [
        ("Fichier source", result.input_path),
        ("Nombre d'entites", result.n_features),
        ("Entites avec au moins une anomalie", len(result.anomaly_feature_ids)),
        ("CRS d'origine", result.crs_origine or "(non defini)"),
        ("CRS utilise pour calculs de surface", result.crs_calcul or "(non calcule)"),
        ("Debut du traitement (UTC)", result.started_at),
        ("Fin du traitement (UTC)", result.finished_at),
        ("Nombre total d'anomalies", len(result.anomalies)),
    ]
    for r, (label, value) in enumerate(rows, start=1):
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws.cell(row=r, column=2, value=value)

    ws.cell(row=len(rows) + 2, column=1, value="Repartition par type d'anomalie").font = Font(bold=True, size=12)
    summary_df = result.summary_by_type()
    start_row = len(rows) + 3
    headers = ["type_anomalie", "severite", "nombre"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font
    for i, row in enumerate(summary_df.itertuples(index=False), start=1):
        for c, val in enumerate(row, start=1):
            ws.cell(row=start_row + i, column=c, value=val)

    for col in range(1, 4):
        ws.column_dimensions[get_column_letter(col)].width = 35

    # --- Feuille Anomalies detaillees ---
    ws2 = wb.create_sheet("Anomalies")
    detail_df = result.to_dataframe()
    headers2 = list(detail_df.columns)
    for c, h in enumerate(headers2, start=1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.fill = header_fill
        cell.font = header_font
    severity_fill = {
        "erreur": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
        "a_verifier": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    }
    for i, row in enumerate(detail_df.itertuples(index=False), start=2):
        row_dict = dict(zip(headers2, row))
        for c, h in enumerate(headers2, start=1):
            ws2.cell(row=i, column=c, value=row_dict[h])
        sev = row_dict.get("severite")
        if sev in severity_fill:
            for c in range(1, len(headers2) + 1):
                ws2.cell(row=i, column=c).fill = severity_fill[sev]
    for col in range(1, len(headers2) + 1):
        ws2.column_dimensions[get_column_letter(col)].width = 28

    # --- Feuille Parametres ---
    ws3 = wb.create_sheet("Parametres")
    ws3.cell(row=1, column=1, value="Parametre").font = Font(bold=True)
    ws3.cell(row=1, column=2, value="Valeur").font = Font(bold=True)
    for i, (k, v) in enumerate(result.params.items(), start=2):
        ws3.cell(row=i, column=1, value=k)
        ws3.cell(row=i, column=2, value=str(v))
    ws3.column_dimensions["A"].width = 30
    ws3.column_dimensions["B"].width = 50

    # --- Feuille Synthese & recommandations (IA, optionnelle) ---
    if synthesis:
        ws4 = wb.create_sheet("Synthese IA")
        ws4.cell(row=1, column=1, value="SYNTHESE EN LANGAGE CLAIR -- genere par IA, a valider").font = Font(bold=True, color="1F3864", size=12)
        ws4.cell(row=2, column=1, value="Base uniquement sur les anomalies reellement detectees ci-dessus -- aucun chiffre invente.").font = Font(italic=True)
        ws4.cell(row=4, column=1, value=synthesis.get("synthese_generale", ""))
        ws4.cell(row=4, column=1).alignment = openpyxl.styles.Alignment(wrap_text=True)
        ws4.row_dimensions[4].height = 40

        ws4.cell(row=6, column=1, value="Priorite").font = Font(bold=True, color="FFFFFF")
        ws4.cell(row=6, column=1).fill = header_fill
        ws4.cell(row=6, column=2, value="Pourquoi c'est important").font = Font(bold=True, color="FFFFFF")
        ws4.cell(row=6, column=2).fill = header_fill
        ws4.cell(row=6, column=3, value="Action recommandee").font = Font(bold=True, color="FFFFFF")
        ws4.cell(row=6, column=3).fill = header_fill
        for i, p in enumerate(synthesis.get("priorites", []), start=7):
            ws4.cell(row=i, column=1, value=p.get("type_anomalie", ""))
            ws4.cell(row=i, column=2, value=p.get("pourquoi_important", ""))
            ws4.cell(row=i, column=3, value=p.get("action_recommandee", ""))
        ws4.column_dimensions["A"].width = 28
        ws4.column_dimensions["B"].width = 50
        ws4.column_dimensions["C"].width = 50

    wb.save(output_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file", help="Fichier geospatial a controler (GeoPackage, Shapefile, GeoJSON, CSV geolocalise)")
    ap.add_argument("--output-dir", default="output", help="Dossier racine des sorties (defaut: output/)")
    ap.add_argument("--layer", default=None, help="Nom de la couche si le fichier en contient plusieurs (GeoPackage)")
    ap.add_argument("--id-field", default=None, help="Champ a utiliser comme identifiant d'entite dans le rapport")
    ap.add_argument("--required-fields", default="", help="Champs obligatoires, separes par des virgules")
    ap.add_argument("--numeric-fields", default="", help="Champs qui doivent etre numeriques, separes par des virgules")
    ap.add_argument("--dedup-key-fields", default="", help="Champs cles pour detecter les doublons attributaires")
    ap.add_argument("--area-field", default=None, help="Champ de surface declaree (en hectares) a comparer au calcul SIG")
    ap.add_argument("--area-tolerance-pct", type=float, default=20.0, help="Tolerance d'ecart surface declaree vs SIG, en %% (defaut 20)")
    ap.add_argument("--dup-tolerance-m", type=float, default=0.0, help="Tolerance de distance pour les doublons geometriques, en metres (defaut 0 = identite stricte)")
    ap.add_argument("--no-ia", action="store_true", help="Desactive la synthese IA")
    args = ap.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Fichier introuvable : {input_path}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"{input_path.stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / "journal.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )
    logger = logging.getLogger("geodata_quality.cli")
    logger.info("Demarrage du controle qualite sur %s", input_path)
    logger.info("Parametres CLI : %s", vars(args))

    result = run_quality_checks(
        input_path=str(input_path),
        required_fields=_parse_list(args.required_fields),
        numeric_fields=_parse_list(args.numeric_fields),
        key_fields_for_dedup=_parse_list(args.dedup_key_fields),
        area_field=args.area_field,
        area_tolerance_pct=args.area_tolerance_pct,
        dup_tolerance_m=args.dup_tolerance_m,
        layer=args.layer,
        id_field=args.id_field,
    )

    excel_path = run_dir / "rapport_qualite.xlsx"
    synthesis = None if args.no_ia else generate_synthesis_with_ia(result)
    write_excel_report(result, excel_path, synthesis=synthesis)
    logger.info("Rapport Excel ecrit : %s%s", excel_path, " (avec synthese IA)" if synthesis else "")

    gdf = getattr(result, "_gdf", None)
    gpkg_path = None
    if gdf is not None and result.anomaly_feature_ids:
        anomalous = gdf[gdf["_feature_id"].isin(result.anomaly_feature_ids)].copy()
        if not anomalous.empty:
            gpkg_path = run_dir / "anomalies.gpkg"
            anomalous.drop(columns=["_feature_id"], errors="ignore").to_file(gpkg_path, driver="GPKG")
            logger.info("Couche des anomalies ecrite : %s (%d entites)", gpkg_path, len(anomalous))

    logger.info(
        "Termine. %d entite(s) analysee(s), %d anomalie(s) detectee(s) sur %d entite(s) concernee(s).",
        result.n_features, len(result.anomalies), len(result.anomaly_feature_ids),
    )

    print(f"OK - rapport: {excel_path}")
    if gpkg_path:
        print(f"OK - couche anomalies: {gpkg_path}")
    print(f"OK - journal: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
