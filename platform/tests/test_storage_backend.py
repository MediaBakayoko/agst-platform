"""
Tests unitaires de storage_backend.py -- couvrent la logique
testable sans connexion reseau reelle (validation, cle de stockage,
configuration). Les tests d'integration reels (upload/download/
isolation contre le vrai projet Supabase) ont ete executes
manuellement avec des comptes de test jetables -- voir le rapport de
mission pour le detail (non reproduits ici en CI car ils necessitent
des credentials reels et creent des comptes Auth).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import storage_backend as sb  # noqa: E402


def test_file_too_large_rejected():
    with pytest.raises(sb.FileTooLarge):
        sb._validate_upload("gros.csv", b"x" * (sb.MAX_FILE_SIZE_BYTES + 1))


def test_unsupported_extension_rejected():
    with pytest.raises(sb.UnsupportedFileType):
        sb._validate_upload("script.exe", b"MZ")


def test_valid_extension_accepted():
    sb._validate_upload("matrice.xlsx", b"contenu")  # ne doit pas lever


def test_storage_key_is_not_predictable_and_uses_client_prefix():
    key1 = sb._safe_storage_key("client-abc")
    key2 = sb._safe_storage_key("client-abc")
    assert key1 != key2  # jamais la meme cle deux fois
    assert key1.startswith("client-abc/")
    assert "matrice" not in key1  # le nom original n'apparait jamais dans la cle


def test_extension_to_mime_consistent_with_bucket_allowed_types():
    """Verifie que chaque extension autorisee a un type MIME associe
    coherent -- evite une regression comme celle rencontree en test
    reel (mimetypes.guess_type incoherent avec le bucket configure).
    """
    for ext in sb.ALLOWED_EXTENSIONS:
        assert ext in sb.EXTENSION_TO_MIME, f"Extension {ext} autorisee mais sans mapping MIME explicite"


def test_not_configured_raises_when_env_missing(monkeypatch):
    monkeypatch.setattr(sb, "SUPABASE_URL", None)
    monkeypatch.setattr(sb, "SUPABASE_SERVICE_ROLE_KEY", None)
    monkeypatch.setattr(sb, "SUPABASE_DB_URL", None)
    with pytest.raises(sb.StorageNotConfigured):
        sb.upload_file("client-abc", "f.csv", b"x", "autre")


def test_invalid_category_rejected(monkeypatch):
    monkeypatch.setattr(sb, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setattr(sb, "SUPABASE_SERVICE_ROLE_KEY", "fake-key")
    monkeypatch.setattr(sb, "SUPABASE_DB_URL", "postgresql://fake")
    with pytest.raises(sb.StorageError):
        sb.upload_file("client-abc", "f.csv", b"x", "categorie_inventee")


def test_sync_job_output_files_returns_empty_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "SUPABASE_URL", None)
    monkeypatch.setattr(sb, "SUPABASE_SERVICE_ROLE_KEY", None)
    monkeypatch.setattr(sb, "SUPABASE_DB_URL", None)
    (tmp_path / "test.csv").write_text("a,b\n1,2\n")
    result = sb.sync_job_output_files("client-abc", "job1", tmp_path, "autre")
    assert result == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
