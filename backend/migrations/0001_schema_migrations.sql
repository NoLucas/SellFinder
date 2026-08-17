-- Migration bookkeeping only. No RLS / tenant schema content lives here yet -
-- that's still gated on jin's separate go-ahead for the Postgres+RLS design
-- itself (backend/RECONCILIATION.md, 2026-08-17). This migration just gives
-- tools/migrate.py somewhere to record which migrations have run, so the
-- runner mechanism can be built and tested ahead of the schema it will
-- eventually apply.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
