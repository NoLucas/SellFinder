#!/usr/bin/env python3
"""Lightweight SQL migration runner (backend/RECONCILIATION.md §4, decided
2026-08-17: a raw-SQL runner over Alembic+SQLAlchemy - this project has no
ORM anywhere and RLS's actual defenses (FORCE ROW LEVEL SECURITY, policies,
SET LOCAL session variables) live outside what an ORM models anyway, so
raw SQL keeps the real mechanism visible in the code instead of behind a
migration-generator abstraction).

This is the runner *mechanism* only. It does not yet apply any RLS policy
or tenant schema - that content is still gated on jin's go-ahead for the
Postgres+RLS design itself. Building this now means that once approved,
turning the design into a running schema is "write the .sql files", not
"also build tooling at that point."

Usage:
    python tools/migrate.py                 # apply all pending migrations
    python tools/migrate.py --dry-run        # list pending, apply nothing
    python tools/migrate.py --database-url postgresql://...

Reads SELLFINDER_DATABASE_URL (matches the existing SELLFINDER_ env prefix,
app/config.py) if --database-url isn't given.

Requires psycopg (backend/requirements.txt) - not imported at module level
so `--dry-run`-free static inspection and the filename-parsing unit tests
(tests/test_migrate.py) don't need a real driver installed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_FILENAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[str, Path]]:
    """Returns (version, path) pairs sorted by version. version is the
    4-digit numeric prefix as a string (e.g. "0001") - sorted as a string
    on purpose, not int(), so version numbers stay a fixed width by
    convention rather than by a runtime check silently allowing "10" to
    sort before "9"."""
    migrations = []
    for path in migrations_dir.glob("*.sql"):
        match = _FILENAME_RE.match(path.name)
        if not match:
            raise ValueError(
                f"{path.name}: migration filenames must match NNNN_description.sql "
                "(4-digit zero-padded version, e.g. 0001_schema_migrations.sql)"
            )
        migrations.append((match.group(1), path))
    migrations.sort(key=lambda pair: pair[0])
    return migrations


def pending_migrations(applied_versions: set[str], migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[str, Path]]:
    return [(v, p) for v, p in discover_migrations(migrations_dir) if v not in applied_versions]


def _applied_versions(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'schema_migrations')"
        )
        (exists,) = cur.fetchone()
        if not exists:
            return set()
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def apply_migrations(database_url: str, dry_run: bool = False) -> list[str]:
    """Returns the list of versions applied (or, in dry-run, that would be
    applied). Each migration runs in its own transaction, recorded in the
    same transaction it ran in - if the migration fails, nothing about it
    is recorded as applied."""
    import psycopg  # deferred - see module docstring

    with psycopg.connect(database_url) as conn:
        applied = _applied_versions(conn)
        pending = pending_migrations(applied)

        if dry_run:
            return [v for v, _ in pending]

        newly_applied = []
        for version, path in pending:
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                    )
            newly_applied.append(version)
        return newly_applied


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="list pending migrations, apply none")
    ap.add_argument(
        "--database-url",
        default=os.environ.get("SELLFINDER_DATABASE_URL"),
        help="defaults to SELLFINDER_DATABASE_URL",
    )
    args = ap.parse_args()

    if not args.database_url:
        print("error: no database URL (pass --database-url or set SELLFINDER_DATABASE_URL)", file=sys.stderr)
        return 2

    result = apply_migrations(args.database_url, dry_run=args.dry_run)

    if args.dry_run:
        if result:
            print(f"{len(result)} pending migration(s):")
            for version in result:
                print(f"  {version}")
        else:
            print("no pending migrations")
    else:
        if result:
            print(f"applied {len(result)} migration(s):")
            for version in result:
                print(f"  {version}")
        else:
            print("nothing to apply - already up to date")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
