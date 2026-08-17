"""Unit tests for tools/migrate.py's filename-parsing / pending-detection
logic only - no live Postgres needed (there isn't one in CI yet; the
Postgres+RLS design itself is still gated on jin's approval,
backend/RECONCILIATION.md 2026-08-17). apply_migrations() (the part that
actually needs psycopg + a real connection) is exercised only once a real
database is available - not tested here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import migrate  # noqa: E402


def test_discover_migrations_finds_the_real_migrations_dir() -> None:
    """Sanity check against the actual backend/migrations/ directory, not
    a fixture - if 0001_schema_migrations.sql is ever renamed or deleted
    without updating this, that's exactly the kind of drift this test
    should catch."""
    found = migrate.discover_migrations()
    versions = [v for v, _ in found]
    assert "0001" in versions


def test_discover_migrations_sorted_by_version(tmp_path) -> None:
    (tmp_path / "0002_second.sql").write_text("-- second", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("-- first", encoding="utf-8")
    (tmp_path / "0010_tenth.sql").write_text("-- tenth", encoding="utf-8")

    found = migrate.discover_migrations(tmp_path)
    assert [v for v, _ in found] == ["0001", "0002", "0010"]


def test_discover_migrations_rejects_bad_filenames(tmp_path) -> None:
    (tmp_path / "not_a_migration.sql").write_text("-- oops", encoding="utf-8")
    try:
        migrate.discover_migrations(tmp_path)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not_a_migration.sql" in str(exc)


def test_pending_migrations_excludes_applied(tmp_path) -> None:
    (tmp_path / "0001_a.sql").write_text("-- a", encoding="utf-8")
    (tmp_path / "0002_b.sql").write_text("-- b", encoding="utf-8")

    pending = migrate.pending_migrations({"0001"}, tmp_path)
    assert [v for v, _ in pending] == ["0002"]


def test_pending_migrations_all_pending_when_nothing_applied(tmp_path) -> None:
    (tmp_path / "0001_a.sql").write_text("-- a", encoding="utf-8")
    pending = migrate.pending_migrations(set(), tmp_path)
    assert [v for v, _ in pending] == ["0001"]


def test_pending_migrations_empty_when_all_applied(tmp_path) -> None:
    (tmp_path / "0001_a.sql").write_text("-- a", encoding="utf-8")
    pending = migrate.pending_migrations({"0001"}, tmp_path)
    assert pending == []
