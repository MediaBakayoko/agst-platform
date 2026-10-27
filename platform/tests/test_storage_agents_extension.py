"""
Tests de la logique d'extension Supabase Storage aux 5 agents
restants (job_runner.AGENT_STORAGE_CATEGORY,
consulting_business.AGENT_PREFIX_STORAGE_CATEGORY). Ne refait pas les
tests reseau reels (deja executes manuellement avec des comptes
jetables -- voir rapport de mission) : verifie seulement que le
mapping categorie->agent est complet et correct, et que le
declenchement de sync_job_output_files est bien conditionnel au
prefixe/agent connu.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import job_runner  # noqa: E402
from app.routers import consulting_business as cb  # noqa: E402


def test_all_run_agent_job_agents_have_a_storage_category():
    for agent_name in job_runner.AGENT_SCRIPTS:
        assert agent_name in job_runner.AGENT_STORAGE_CATEGORY, (
            f"Agent {agent_name} gere par run_agent_job mais sans categorie Storage mappee"
        )


def test_agent_prefix_storage_category_covers_the_4_run_script_agents():
    """consulting_business, academy_knowledge, data_science_geoai et
    meal_project_performance utilisent tous _run_script -- chacun doit
    avoir une categorie mappee (sauf survey_intelligence, exclu
    deliberement car il fait sa propre synchronisation ciblee).
    """
    expected_prefixes = {"consulting_business", "academy_knowledge", "data_science_geoai", "meal"}
    assert expected_prefixes.issubset(cb.AGENT_PREFIX_STORAGE_CATEGORY.keys())
    assert "survey_intelligence" not in cb.AGENT_PREFIX_STORAGE_CATEGORY


def test_run_script_calls_sync_only_for_known_prefix(tmp_path):
    """Verifie que _run_script tente la synchronisation Storage
    uniquement pour un agent_label dont le prefixe est mappe --
    jamais pour survey_intelligence.* (deja gere ailleurs).
    """
    job_dir = tmp_path
    (job_dir / "fake_script.py").write_text("import sys; sys.exit(0)")

    with patch("app.core.storage_backend.sync_job_output_files") as mock_sync:
        cb._run_script(
            "fake_script.py", "survey_intelligence.something", job_dir,
            "00000000-0000-0000-0000-000000000000", "job_test", [], scripts_dir=job_dir,
        )
        mock_sync.assert_not_called()


def test_run_script_calls_sync_for_mapped_prefix(tmp_path):
    job_dir = tmp_path
    (job_dir / "fake_script.py").write_text("import sys; sys.exit(0)")

    with patch("app.core.storage_backend.sync_job_output_files") as mock_sync:
        cb._run_script(
            "fake_script.py", "academy_knowledge.course_outline_builder", job_dir,
            "00000000-0000-0000-0000-000000000000", "job_test", [], scripts_dir=job_dir,
        )
        mock_sync.assert_called_once()
        args, kwargs = mock_sync.call_args
        assert kwargs.get("categorie") == "rapport" or (len(args) >= 4 and args[3] == "rapport")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
