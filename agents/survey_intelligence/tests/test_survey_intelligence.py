"""
Tests automatises du pipeline survey_intelligence. Executes reellement
avec pytest -- verrouillent les comportements critiques (aucune cible
inventee, classification correcte de severite, detection d'erreur
XLSForm) pour eviter les regressions silencieuses.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from indicator_matrix_builder import build_matrix  # noqa: E402
from xlsform_builder import build_xlsform, parse_question_spec, slugify  # noqa: E402
from xlsform_validator import validate_xlsform  # noqa: E402
from survey_quality_checks import (  # noqa: E402
    SEVERITY_MAP,
    build_alert_registry,
    check_consistency_rules,
    check_outliers_iqr,
)


def test_matrix_never_invents_missing_target():
    """Aucune cible absente du CSV source ne doit apparaitre dans la
    matrice -- elle doit rester vide et signalee comme lacune.
    """
    df = pd.DataFrame([{"intitule": "Indicateur test", "definition": "def", "formule": "f",
                         "unite": "u", "source_verification": "sv", "frequence": "freq",
                         "cible": None}])
    matrix_df, gaps, _ = build_matrix(df)
    assert pd.isna(matrix_df.iloc[0]["cible"])
    assert any("cible" in str(g["champs_manquants"]) for g in gaps)


def test_matrix_never_invents_baseline():
    """Aucune valeur de reference absente ne doit etre inventee."""
    df = pd.DataFrame([{"intitule": "Indicateur test", "definition": "def", "formule": "f",
                         "source_verification": "sv", "frequence": "freq", "cible": "100",
                         "valeur_reference": None}])
    matrix_df, gaps, _ = build_matrix(df)
    assert pd.isna(matrix_df.iloc[0]["valeur_reference"])
    assert any("valeur_reference" in str(g["champs_manquants"]) for g in gaps)


def test_matrix_signals_missing_required_field():
    df = pd.DataFrame([{"intitule": "Indicateur incomplet", "definition": None, "formule": "f",
                         "source_verification": "sv", "frequence": "freq", "cible": "100"}])
    matrix_df, gaps, _ = build_matrix(df)
    gap_for_this = next(g for g in gaps if g["indicateur"] == "Indicateur incomplet")
    assert "definition" in gap_for_this["champs_manquants"]


def test_matrix_preserves_explicit_approved_status():
    """Un statut_validation explicitement fourni et reconnu (ex:
    'approuve') ne doit jamais etre ecrase par le defaut.
    """
    df = pd.DataFrame([{"intitule": "Ind1", "definition": "d", "formule": "f",
                         "source_verification": "sv", "frequence": "freq", "cible": "10",
                         "valeur_reference": "0", "statut_validation": "approuve"}])
    matrix_df, _, _ = build_matrix(df)
    assert matrix_df.iloc[0]["statut_validation"] == "approuve"


def test_matrix_unrecognized_status_falls_back_to_propose():
    df = pd.DataFrame([{"intitule": "Ind1", "definition": "d", "formule": "f",
                         "source_verification": "sv", "frequence": "freq", "cible": "10",
                         "valeur_reference": "0", "statut_validation": "n_importe_quoi"}])
    matrix_df, _, _ = build_matrix(df)
    assert matrix_df.iloc[0]["statut_validation"] == "propose"


def test_question_spec_parsing_select_one():
    parsed = parse_question_spec("select_one:Sexe:Masculin,Feminin", "fallback")
    assert parsed["type"] == "select_one"
    assert parsed["choices"] == ["Masculin", "Feminin"]
    assert parsed["reconnu"] is True


def test_question_spec_unrecognized_falls_back_to_text_and_flags():
    parsed = parse_question_spec("type_bizarre:xyz", "Label de secours")
    assert parsed["type"] == "text"
    assert parsed["reconnu"] is False
    assert parsed["label"] == "Label de secours"


def test_slugify_produces_valid_xlsform_name():
    assert slugify("Nom du producteur !") == "nom_du_producteur"
    assert slugify("") == "champ"


def test_xlsform_builder_handles_duplicate_names():
    df = pd.DataFrame([
        {"intitule": "Age", "question_necessaire": "integer:Age"},
        {"intitule": "Age", "question_necessaire": "integer:Age (bis)"},
    ])
    survey_rows, choices_rows, settings, warnings = build_xlsform(df, "Test form")
    names = [r["name"] for r in survey_rows if r["name"] not in ("start", "end")]
    assert len(names) == len(set(names)), "les noms de champs doivent etre uniques"
    assert any("deja utilise" in w for w in warnings)


def test_xlsform_builder_parses_relevant_and_constraint():
    parsed = parse_question_spec(
        "decimal:Surface|relevant=${a_une_parcelle}='oui'|constraint=. > 0|constraint_message=Doit etre positif",
        "fallback",
    )
    assert parsed["type"] == "decimal"
    assert parsed["relevant"] == "${a_une_parcelle}='oui'"
    assert parsed["constraint"] == ". > 0"
    assert parsed["constraint_message"] == "Doit etre positif"


def test_xlsform_builder_handles_repeat_group():
    df = pd.DataFrame([
        {"intitule": "Annee", "question_necessaire": "integer:Annee|repeat_group=historique"},
        {"intitule": "Quantite", "question_necessaire": "decimal:Quantite|repeat_group=historique"},
        {"intitule": "Commentaire", "question_necessaire": "text:Commentaire"},
    ])
    survey_rows, _, _, _ = build_xlsform(df, "Test repeat")
    types = [r["type"] for r in survey_rows]
    assert "begin repeat" in types
    assert "end repeat" in types
    begin_idx = types.index("begin repeat")
    end_idx = types.index("end repeat")
    assert begin_idx < end_idx
    # "Commentaire" (hors groupe) doit etre apres la fermeture du groupe
    commentaire_idx = next(i for i, r in enumerate(survey_rows) if r["name"] == "commentaire")
    assert commentaire_idx > end_idx


def test_xlsform_builder_calculate_field_without_expr_warns():
    df = pd.DataFrame([{"intitule": "Champ calcule", "question_necessaire": "calculate:Champ calcule"}])
    _, _, _, warnings = build_xlsform(df, "Test calc")
    assert any("sans expression" in w for w in warnings)


def test_xlsform_validator_detects_missing_choice_list(tmp_path):
    import openpyxl
    path = tmp_path / "invalide.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(["type", "name", "label", "required"])
    ws.append(["start", "start", "", ""])
    ws.append(["select_one liste_absente", "q1", "Question", "yes"])
    ws.append(["end", "end", "", ""])
    ws2 = wb.create_sheet("choices")
    ws2.append(["list_name", "name", "label"])
    ws3 = wb.create_sheet("settings")
    ws3.append(["form_title", "form_id"])
    ws3.append(["Titre", "id"])
    wb.save(path)

    result = validate_xlsform(path)
    assert result["valide"] is False
    assert any("liste_absente" in e for e in result["erreurs_bloquantes"])


def test_xlsform_validator_accepts_well_formed_form(tmp_path):
    import openpyxl
    path = tmp_path / "valide.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(["type", "name", "label", "required"])
    ws.append(["start", "start", "", ""])
    ws.append(["text", "nom", "Nom", "yes"])
    ws.append(["end", "end", "", ""])
    ws2 = wb.create_sheet("choices")
    ws2.append(["list_name", "name", "label"])
    ws3 = wb.create_sheet("settings")
    ws3.append(["form_title", "form_id"])
    ws3.append(["Titre", "id"])
    wb.save(path)

    result = validate_xlsform(path)
    assert result["valide"] is True
    assert result["erreurs_bloquantes"] == []


def test_xlsform_validator_detects_relevant_referencing_unknown_field(tmp_path):
    """Une expression relevant qui reference un champ absent du
    formulaire doit etre une erreur bloquante -- detectee par les
    controles maison meme si pyxform est indisponible dans
    l'environnement de test.
    """
    import openpyxl
    path = tmp_path / "relevant_invalide.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(["type", "name", "label", "required", "relevant"])
    ws.append(["start", "start", "", "", ""])
    ws.append(["text", "q1", "Question 1", "yes", ""])
    ws.append(["text", "q2", "Question 2", "yes", "${champ_inexistant}='x'"])
    ws.append(["end", "end", "", "", ""])
    ws2 = wb.create_sheet("choices")
    ws2.append(["list_name", "name", "label"])
    ws3 = wb.create_sheet("settings")
    ws3.append(["form_title", "form_id"])
    ws3.append(["Titre", "id"])
    wb.save(path)

    result = validate_xlsform(path)
    assert result["valide"] is False
    assert any("champ_inexistant" in e for e in result["erreurs_bloquantes"])


def test_xlsform_validator_detects_unclosed_repeat_group(tmp_path):
    import openpyxl
    path = tmp_path / "repeat_non_ferme.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "survey"
    ws.append(["type", "name", "label", "required"])
    ws.append(["start", "start", "", ""])
    ws.append(["begin repeat", "groupe1", "Groupe 1", ""])
    ws.append(["text", "q1", "Question 1", "yes"])
    ws.append(["end", "end", "", ""])  # pas de "end repeat" -- erreur attendue
    ws2 = wb.create_sheet("choices")
    ws2.append(["list_name", "name", "label"])
    ws3 = wb.create_sheet("settings")
    ws3.append(["form_title", "form_id"])
    ws3.append(["Titre", "id"])
    wb.save(path)

    result = validate_xlsform(path)
    assert result["valide"] is False
    assert any("non ferme" in e.lower() for e in result["erreurs_bloquantes"])


def test_outlier_detection_never_labeled_as_error():
    """Une valeur hors IQR doit toujours etre classee valeur_inhabituelle,
    jamais erreur_bloquante.
    """
    df = pd.DataFrame({"age": [30, 32, 31, 29, 33, 150]})
    anomalies = check_outliers_iqr(df, ["age"])
    assert len(anomalies) == 1
    severity = SEVERITY_MAP.get(anomalies[0]["type_anomalie"])
    assert severity == "valeur_inhabituelle"
    assert severity != "erreur_bloquante"


def test_consistency_rule_detects_violation():
    df = pd.DataFrame({"age_min": [18, 70], "age_max": [65, 65]})
    rules = pd.DataFrame([{"champ_a": "age_min", "operateur": "<", "champ_b": "age_max"}])
    anomalies = check_consistency_rules(df, rules)
    assert len(anomalies) == 1
    assert anomalies[0]["ligne"] == 1


def test_alert_registry_has_all_required_columns():
    anomalies = [{"type_anomalie": "reponse_manquante", "ligne": 0, "champ": "x", "description": "test"}]
    registry = build_alert_registry(anomalies, "projet_test")
    required_cols = {
        "projet", "id_soumission", "date_detection", "enqueteur", "regle_declenchee",
        "valeur_concernee", "niveau_gravite", "justification", "indicateur_potentiellement_affecte",
        "action_recommandee", "responsable_verification", "statut_resolution", "historique_corrections",
    }
    assert required_cols.issubset(set(registry.columns))
    assert registry.iloc[0]["niveau_gravite"] == "erreur_bloquante"
    assert registry.iloc[0]["statut_resolution"] == "nouvelle"


def test_date_consistency_detects_unparseable_and_out_of_range():
    from survey_quality_checks import check_date_consistency
    df = pd.DataFrame({"date_visite": ["2026-01-15", "pas_une_date", "2030-01-01"]})
    anomalies = check_date_consistency(df, ["date_visite"], min_date="2025-01-01", max_date="2026-12-31")
    types_lignes = {(a["ligne"]) for a in anomalies}
    assert 1 in types_lignes  # non parseable
    assert 2 in types_lignes  # hors bornes (futur)


def test_gps_within_zone_flags_outside_bbox():
    from survey_quality_checks import check_gps_within_zone
    df = pd.DataFrame({"lat": [4.75, 10.5], "lon": [-6.6, -6.6]})
    anomalies = check_gps_within_zone(df, "lat", "lon", lat_min=4.0, lat_max=5.5, lon_min=-7.0, lon_max=-6.0)
    assert len(anomalies) == 1
    assert anomalies[0]["ligne"] == 1


def test_interview_duration_flags_too_short():
    from survey_quality_checks import check_interview_duration
    df = pd.DataFrame({
        "debut": ["2026-01-01T10:00:00", "2026-01-01T10:00:00"],
        "fin": ["2026-01-01T10:00:30", "2026-01-01T10:20:00"],
    })
    anomalies = check_interview_duration(df, "debut", "fin", min_minutes=2.0, max_minutes=180.0)
    assert len(anomalies) == 1
    assert anomalies[0]["ligne"] == 0
    assert SEVERITY_MAP[anomalies[0]["type_anomalie"]] == "anomalie_probable"


def test_modified_after_analysis_detects_change(tmp_path):
    from survey_quality_checks import check_modified_after_analysis
    hashes_path = tmp_path / "hashes.json"
    df1 = pd.DataFrame({"id": ["s1", "s2"], "valeur": [10, 20]})
    _, hashes1 = check_modified_after_analysis(df1, "id", hashes_path)
    hashes_path.write_text(__import__("json").dumps(hashes1), encoding="utf-8")

    df2 = pd.DataFrame({"id": ["s1", "s2"], "valeur": [10, 999]})  # s2 modifie
    anomalies2, _ = check_modified_after_analysis(df2, "id", hashes_path)
    assert len(anomalies2) == 1
    assert anomalies2[0]["description"].find("s2") != -1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
