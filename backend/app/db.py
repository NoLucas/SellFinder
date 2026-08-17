"""Staged for the PostgreSQL+RLS cutover (backend/RECONCILIATION.md,
2026-08-17). Not imported by app/main.py or any router yet - prediction_store.py
still runs entirely in memory. This module exists so wiring up a route means
"add `conn = Depends(get_db_session)`", not "also design the session/RLS
plumbing at that point."

get_db_session is the single place a connection is ever checked out and the
tenant session variable is ever set - the same reasoning as
app.security.get_tenant_id (ADR-003 §3, the one place tokens are parsed) and
routers/predictions.py's _build_views() (VF-013, the one place a redacted
value is ever assembled). Every prior "leaked through the one path nobody
funneled through the choke point" incident (VF-002/VF-005/VF-010/VF-013) is
the reason this is a single dependency instead of something every route
re-implements.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends

from app.config import settings
from app.security import get_tenant_id

# Built once at process start (mirrors app.services.intelligence_client's
# _STORE - "don't rebuild the expensive/stateful thing per request"),
# not per-request. Actual construction is deferred into get_pool() so
# importing this module doesn't require a reachable database - matters for
# tests that only exercise unrelated routes and never call get_db_session.
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        import psycopg_pool

        _pool = psycopg_pool.AsyncConnectionPool(
            settings.database_url, open=False, min_size=1, max_size=10
        )
    return _pool


async def get_db_session(
    tenant_id: str = Depends(get_tenant_id),
) -> AsyncIterator["psycopg.AsyncConnection"]:  # noqa: F821 - psycopg imported lazily below
    """Every route that touches prediction_run/region_score/idempotency_key/
    audit_log depends on this instead of calling prediction_store's
    dict-backed functions directly (once those are cut over to Postgres).

    Yields a connection inside an open transaction with
    app.current_tenant_id already set for that transaction via SET LOCAL
    (via set_config(), never a bare SET - a bare SET's value survives past
    this transaction and would leak into the next request that reuses the
    same pooled connection, handing it another tenant's session variable.
    set_config() over string-interpolated SQL because tenant_id ultimately
    derives from a bearer token value - set_config is a normal parameterized
    function call, not a literal spliced into `SET LOCAL ... = '<value>'`).

    RLS policies (backend/migrations/0003_row_level_security.sql) do the
    actual enforcement; this function's only job is making sure they always
    have something correct to check against.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', %s, true)", (tenant_id,)
            )
            yield conn
