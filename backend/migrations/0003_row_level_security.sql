-- Staged, not yet run - see 0002's header. This is the part that actually
-- enforces 06_governance.md §1.2 ("애플리케이션 WHERE 절만 믿지 않는다").
--
-- Order matters within this file: role first, then FORCE (before any
-- policy exists, so there's never a window where the app role could read
-- unrestricted), then policies, then grants.

-- The application connects as this role, never as the table owner (the
-- role that ran these migrations) and never as a superuser. Table
-- owners/superusers bypass RLS by default even with ENABLE - that's what
-- FORCE below is for, but a low-privilege role is the first line of
-- defense regardless. BYPASSRLS is deliberately never granted.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sellfinder_app') THEN
        -- LOGIN password set out-of-band (secret manager), not hardcoded here
        -- (06_governance.md §6 "코드/리포지토리에 자격증명 하드코딩 금지").
        CREATE ROLE sellfinder_app LOGIN;
    END IF;
END
$$;

ALTER TABLE prediction_run   ENABLE ROW LEVEL SECURITY;
ALTER TABLE region_score     ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_key  ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log        ENABLE ROW LEVEL SECURITY;

-- FORCE가 핵심이다: 기본값(ENABLE만)은 테이블 소유자(이 마이그레이션을 실행한
-- 롤)에게는 RLS가 적용되지 않는다. sellfinder_app이 소유자가 아니게 만드는 것과는
-- 별개로, FORCE가 없으면 실수로 소유자 계정으로 접속했을 때 정책이 조용히 무의미해진다.
ALTER TABLE prediction_run   FORCE ROW LEVEL SECURITY;
ALTER TABLE region_score     FORCE ROW LEVEL SECURITY;
ALTER TABLE idempotency_key  FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log        FORCE ROW LEVEL SECURITY;

-- GUC 이름은 계약(06_governance.md §1.2)이 예시로 준 것을 그대로 쓴다 - 지어낸
-- 이름을 쓰면 나중에 계약 예시와 실제 코드가 어긋난다(VF-004와 같은 실수).
CREATE POLICY tenant_isolation ON prediction_run
    USING       (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK  (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_isolation ON region_score
    USING       (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK  (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_isolation ON idempotency_key
    USING       (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK  (tenant_id = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_isolation ON audit_log
    USING       (tenant_id = current_setting('app.current_tenant_id', true))
    WITH CHECK  (tenant_id = current_setting('app.current_tenant_id', true));

GRANT SELECT, INSERT, UPDATE, DELETE ON prediction_run, region_score, idempotency_key, audit_log
    TO sellfinder_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sellfinder_app;
