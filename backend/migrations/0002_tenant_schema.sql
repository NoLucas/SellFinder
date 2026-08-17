-- Staged for the PostgreSQL+RLS design (backend/RECONCILIATION.md,
-- 2026-08-17). This file is *ready to run* but nothing runs it yet - there
-- is no live database anywhere (dev/CI/prod) pointed at these migrations.
-- It exists so that once jin approves the schema itself, starting means
-- "point tools/migrate.py at a real database", not "also write the SQL
-- at that point."
--
-- Matches the schema in RECONCILIATION.md's design proposal exactly -
-- copied from there, not re-derived, so the two can't drift apart.
-- RLS itself (ENABLE/FORCE/POLICY/roles) is 0003, kept separate so the
-- two concerns (what the tables are vs. how they're isolated) review
-- independently.

CREATE TABLE prediction_run (
    run_id            text PRIMARY KEY,
    tenant_id         text NOT NULL,
    data_tier         text NOT NULL CHECK (data_tier IN ('T0','T1','T2')),
    region_level      text NOT NULL CHECK (region_level IN ('sido','sigungu','adm_dong','custom_catchment')),
    objective         text NOT NULL,
    boundary_vintage  text,
    status            text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','succeeded','failed')),
    failure_reason    text,
    -- 06_governance.md §4 재현성 3요소: params(요청 원문 전체 스냅샷, 씨드 포함)
    -- + model_version + feature_as_of를 run 생성 시점에 고정 기록한다.
    params            jsonb NOT NULL,
    model_version     text,
    feature_as_of     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE region_score (
    id                    bigserial PRIMARY KEY,
    run_id                text NOT NULL REFERENCES prediction_run(run_id) ON DELETE CASCADE,
    -- tenant_id를 여기에도 중복 저장한다(정규화 위반처럼 보이지만 의도적이다) -
    -- RLS 정책은 이 테이블 자체의 컬럼만 본다. prediction_run과 조인해서 tenant_id를
    -- 알아내는 정책을 쓰면, 조인을 빠뜨린 쿼리 하나가 바로 "한 곳만 빠뜨려도 유출"의
    -- 실례가 된다.
    tenant_id             text NOT NULL,
    region_id             text NOT NULL,
    region_name           text NOT NULL,
    rank                  integer NOT NULL,
    opportunity_score     double precision NOT NULL,
    score_percentile      double precision NOT NULL,
    expected_revenue_p10  bigint,
    expected_revenue_p50  bigint,
    expected_revenue_p90  bigint,
    confidence_level      text NOT NULL CHECK (confidence_level IN ('low','medium','high')),
    data_coverage         double precision NOT NULL,
    coverage_flag         text CHECK (coverage_flag IN ('actual','estimated','suppressed')),
    UNIQUE (run_id, region_id)
);

CREATE TABLE idempotency_key (
    tenant_id   text NOT NULL,
    key         text NOT NULL,
    run_id      text NOT NULL REFERENCES prediction_run(run_id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, key)
);

-- 06_governance.md §4 필수 기록: 누가/언제/무엇을. C-4(request_id 미들웨어)가
-- 지금 로그 파일에만 남기고 있는 것을 3년 보관 가능한 형태로 옮기는 자리.
CREATE TABLE audit_log (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,
    actor_user_id text,
    request_id    text NOT NULL,
    action        text NOT NULL,       -- 'prediction.create' | 'prediction.view' | 'prediction.export' 등
    run_id        text,
    params        jsonb,
    occurred_at   timestamptz NOT NULL DEFAULT now()
);
