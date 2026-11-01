"""
Field2Report — generation du rapport Word final.

Le rapport ne contient que des informations calculees reellement a
partir des donnees. La section "Limites" est toujours generee a partir
des biais et anomalies reellement detectes, jamais d'un texte generique
vide de sens.

Section "Interpretation" (optionnelle, IA) : si ANTHROPIC_API_KEY est
configuree, Claude redige une interpretation en langage clair des
statistiques REELLEMENT calculees (jamais un chiffre invente) --
toujours marquee "[INTERPRETATION IA -- A VALIDER]".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Mm, Pt, RGBColor


def interpret_results_with_ia(stats_df, anomalies: list[dict], bias_notes: list[str]) -> str | None:
    """Demande a Claude une interpretation en langage clair des
    statistiques REELLEMENT calculees (stats_df), sans jamais
    inventer un chiffre absent de ce tableau. Retourne None si
    aucune cle API configuree ou si l'appel echoue.
    """
    if stats_df is None or stats_df.empty:
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))
    from llm_connector import get_claude_connector, LLMNotConfiguredError, LLMAPIError
    import logging
    logger = logging.getLogger("field2report.report_builder")

    try:
        connector = get_claude_connector()
        system_prompt = (
            "Tu es un statisticien/geomaticien specialise en enquetes terrain. On te donne "
            "des statistiques descriptives REELLEMENT calculees sur des donnees d'enquete "
            "(tableau complet), les anomalies detectees et les biais signales -- tu ne dois "
            "JAMAIS inventer un chiffre absent de ces donnees. Redige une interpretation en "
            "langage clair (3-5 phrases) pour un non-statisticien : ce que montrent les "
            "chiffres, les points de vigilance (lies aux anomalies/biais reels), sans tirer de "
            "conclusion causale non justifiee par de simples statistiques descriptives.\n\n"
            "Reponds UNIQUEMENT en JSON valide : {\"interpretation\": \"...\"}"
        )
        user_content = (
            f"Statistiques calculees :\n{stats_df.to_json(orient='records', force_ascii=False)}\n\n"
            f"Anomalies detectees (nombre) : {len(anomalies)}\n"
            f"Notes de biais signalees : {json.dumps(bias_notes, ensure_ascii=False)}"
        )
        result = connector.generate_json(system_prompt, user_content)
        return result.get("interpretation")
    except LLMNotConfiguredError as exc:
        logger.info("Interpretation IA desactivee : %s", exc)
        return None
    except LLMAPIError as exc:
        logger.warning("Interpretation IA indisponible (echec appel) : %s", str(exc)[:500])
        return None


def build_report(
    output_path: Path,
    source_file: str,
    n_rows_raw: int,
    n_rows_clean: int,
    cleaning_actions: list,
    anomalies: list[dict],
    stats_df,
    bias_notes: list[str],
    map_path: Optional[Path],
    group_field: Optional[str],
    started_at: str,
    finished_at: str,
    no_ia: bool = False,
) -> None:
    doc = Document()
    section = doc.sections[0]
    section.left_margin = Mm(20)
    section.right_margin = Mm(20)

    title = doc.add_heading("Rapport d'analyse — Field2Report", level=0)
    for run in title.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)

    p = doc.add_paragraph()
    p.add_run(f"Fichier source : {source_file}\n").bold = True
    p.add_run(f"Période de traitement (UTC) : {started_at} → {finished_at}\n")
    p.add_run(f"Lignes brutes : {n_rows_raw}  |  Lignes après nettoyage : {n_rows_clean}")

    doc.add_heading("1. Méthodologie", level=1)
    doc.add_paragraph(
        "Les données brutes sont conservées sans modification. Les actions de "
        "nettoyage listées ci-dessous sont les seules transformations appliquées ; "
        "aucune valeur manquante n'a été complétée ou estimée automatiquement."
    )
    if cleaning_actions:
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text = "Action", "Champ", "Lignes concernées"
        for a in cleaning_actions:
            row = table.add_row().cells
            row[0].text = a.action
            row[1].text = a.champ or "-"
            row[2].text = str(a.n_lignes_concernees)
    else:
        doc.add_paragraph("Aucune action de nettoyage n'a été nécessaire.")

    doc.add_heading("2. Contrôle qualité — anomalies détectées", level=1)
    if anomalies:
        n_erreurs = sum(1 for a in anomalies if a.get("severite") == "erreur")
        n_a_verifier = sum(1 for a in anomalies if a.get("severite") == "a_verifier")
        doc.add_paragraph(
            f"{len(anomalies)} anomalie(s) détectée(s) : {n_erreurs} erreur(s) certaine(s), "
            f"{n_a_verifier} anomalie(s) à vérifier par l'équipe terrain."
        )
        table = doc.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        hdr = table.rows[0].cells
        hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Type", "Sévérité", "Ligne", "Description"
        for a in anomalies[:200]:  # limite d'affichage ; le detail complet est dans le journal
            row = table.add_row().cells
            row[0].text = str(a.get("type_anomalie", ""))
            row[1].text = str(a.get("severite", ""))
            row[2].text = str(a.get("ligne", ""))
            row[3].text = str(a.get("description", ""))
        if len(anomalies) > 200:
            doc.add_paragraph(f"(+{len(anomalies) - 200} anomalie(s) supplémentaire(s) — voir journal.log)")
    else:
        doc.add_paragraph("Aucune anomalie détectée sur les contrôles effectués.")

    doc.add_heading("3. Statistiques descriptives", level=1)
    if stats_df is not None and not stats_df.empty:
        cols = list(stats_df.columns)
        table = doc.add_table(rows=1, cols=len(cols))
        table.style = "Table Grid"
        for i, c in enumerate(cols):
            table.rows[0].cells[i].text = c
        for _, row in stats_df.iterrows():
            cells = table.add_row().cells
            for i, c in enumerate(cols):
                val = row[c]
                cells[i].text = f"{val:.2f}" if isinstance(val, float) else str(val)
        n_unreliable = (stats_df["fiabilite"] == "n_insuffisant").sum() if "fiabilite" in stats_df.columns else 0
        if n_unreliable:
            doc.add_paragraph(
                f"⚠ {n_unreliable} ligne(s) statistique(s) basée(s) sur un effectif jugé "
                "insuffisant (n<3) — à interpréter avec prudence, non supprimées du tableau."
            ).italic = True
    else:
        doc.add_paragraph("Aucune variable numérique à analyser n'a été fournie.")

    interpretation = None if no_ia else interpret_results_with_ia(stats_df, anomalies, bias_notes)
    if interpretation:
        doc.add_heading("Interprétation (brouillon)", level=2)
        p = doc.add_paragraph()
        run = p.add_run("[INTERPRETATION IA -- A VALIDER]  ")
        run.bold = True
        run.font.color.rgb = RGBColor(0xB8, 0x6A, 0x00)
        p.add_run(interpretation)

    if map_path and Path(map_path).exists():
        doc.add_heading("4. Cartographie", level=1)
        doc.add_picture(str(map_path), width=Mm(150))

    doc.add_heading("5. Limites et biais identifiés", level=1)
    if bias_notes:
        for note in bias_notes:
            doc.add_paragraph(note, style="List Bullet")
    else:
        doc.add_paragraph("Aucun déséquilibre manifeste détecté par les contrôles automatiques.")
    doc.add_paragraph(
        "Cette analyse est produite automatiquement à partir des données fournies. "
        "Elle ne remplace pas la validation d'un géomaticien/statisticien sur les "
        "anomalies et biais signalés ci-dessus."
    ).italic = True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
