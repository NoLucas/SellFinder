# CONTRACT_CHANGE_REQUEST — /backend (에이전트 C)

작성일: 2026-08-15

jin의 직접 지시로 아래 세 가지를 이미 구현했습니다. `shared/contracts/*`는 여기서 직접 고치지
않았으므로, 실제 계약 파일(`04_api_contract.yaml`, `01_domain_model.json`) 반영은 이 문서 기록
후 검토·병합해 주세요.

---

## 1. `/predictions/{run_id}/tiles/{z}/{x}/{y}.mvt` 제거

- **대상 파일**: `04_api_contract.yaml`
- **현재 정의**: `GET /predictions/{run_id}/tiles/{z}/{x}/{y}.mvt` — 벡터타일 히트맵 렌더링용, `/backend` 소유.
- **제안 정의**: 이 엔드포인트를 계약에서 삭제. 대신 콘솔은 (2)의 매니페스트로 경계 지오메트리를,
  (3)의 지역 점수 응답으로 `opportunity_score`를 각각 받아 `region_id` 기준으로 클라이언트에서 조인한다.
- **사유**: `/backend`의 벡터타일 생성/프록시 주체가 A(경계 생성)와 C(엔드포인트 소유) 중 불명확했음
  (`backend/RECONCILIATION.md` §6). jin이 타일 생성·프록시를 아예 만들지 않는 방향으로 결정.
- **영향받는 에이전트**: D(console) — 지도 렌더링을 벡터타일 대신 (경계 GeoJSON + 점수 목록) 클라이언트
  조인 방식으로 구현해야 함. A(data-platform) — 경계 지오메트리를 정적 아티팩트(GeoJSON 등)로 발행하는
  주체가 됨(타일 서버가 아니어도 됨).

## 2. `GET /basemap/regions/manifest` 신설

- **대상 파일**: `04_api_contract.yaml` (신규 path 추가)
- **제안 정의**:
  ```yaml
  /basemap/regions/manifest:
    get:
      tags: [reference]
      summary: 지역 경계 아티팩트 매니페스트
      description: |
        /data-platform이 발행한 경계 아티팩트(GeoJSON 등)의 URL만 반환한다.
        /backend는 지오메트리를 생성하거나 프록시하지 않는다. 서명이 필요한
        아티팩트는 만료 시각이 포함된 서명 URL로 반환한다.
      responses:
        '200':
          content:
            application/json:
              example:
                boundary_vintage: "2026-08"
                levels:
                  - { level: "sido", format: "geojson", url: "https://.../sido/2026-08.geojson" }
                  - { level: "sigungu", format: "geojson", url: "https://.../sigungu/2026-08.geojson" }
                  - { level: "adm_dong", format: "geojson", url: "https://.../adm_dong/2026-08.geojson?expires=...&sig=..." }
  ```
- **구현 상태**: `/backend`에 완료. `app/services/basemap_registry.py`에 URL 레지스트리 자리를 만들어뒀으나,
  A가 아직 실제 경계 아티팩트를 발행하지 않아(`data-platform/RECONCILIATION.md` §5-1 진행 전) 지금은
  플레이스홀더 URL을 반환한다. A가 실제 저장 위치를 정하면 `_ARTIFACTS` 목록만 교체하면 됨.
- **영향받는 에이전트**: A(data-platform) — 실제 경계 아티팩트 저장 위치/포맷 확정 필요. D(console) — 이
  엔드포인트로 경계 지오메트리를 받아 지도에 로드해야 함.

## 3. `prediction_run.boundary_vintage` 필드 추가

- **대상 파일**: `01_domain_model.json`의 `prediction_run` 엔티티, `04_api_contract.yaml`의
  `/predictions/{run_id}/regions` 응답 스키마.
- **현재 정의**: `prediction_run`에 경계 버전을 기록하는 필드 없음. `/predictions/{run_id}/regions`
  응답에도 없음.
- **제안 정의**: `prediction_run.boundary_vintage: string` (run 생성 시점의 (2) 매니페스트
  `boundary_vintage`를 그대로 기록, `feature_as_of`와 같은 재현성 목적). `/predictions/{run_id}/regions`
  응답 최상위에 `boundary_vintage`를 실어 보낸다 (지역별이 아니라 run 단위 값이므로 `data` 배열이 아닌
  응답 최상위).
- **사유**: 행정구역 개편으로 경계가 바뀌어도 과거 run의 `region_id`가 어떤 경계 버전 기준이었는지
  추적 가능해야 재현성이 유지된다(`region_code_mapping` 문제와 동일 계열, A의 RECONCILIATION §3-1 참조).
- **구현 상태**: `/backend`에 완료. `app/services/prediction_store.py`의 `create_run()`이 생성 시점에
  `basemap_registry.BOUNDARY_VINTAGE`를 고정 기록하고, `GET /predictions/{run_id}/regions`가 이를
  응답에 포함한다.
- **영향받는 에이전트**: 없음 (A/B/D는 이 필드를 아직 참조하지 않음).
