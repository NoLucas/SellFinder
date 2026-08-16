# 검증 결과

> 형식은 `verification/CHARTER.md` §8 참조.
> 확인된 것만 적는다. 추정은 별도 절에 분리한다. 모든 항목에 재현 경로 필수.
> 번호(VF-nnn)는 재사용하지 않는다. 해결돼도 번호는 남긴다.

---

## 회차: 7회차 · 2026-08-17 · CI 자체 감사 + RLS 검증 계획 준비 (판정 기준 HEAD `2791644`)

정식 회차 지시 없이 총괄자가 준비 작업 두 건을 요청했다. A/B/C/D 는 3차 사이클 지시를
받았으나 이 회차 작업 중에도 계속 커밋이 들어왔다(예: C 의 `6df2b19` VF-016 수정) — 이번
회차가 그 커밋들을 판정하는 회차는 아니다. CI 감사는 총괄자가 지목한 커밋 `2791644` 를
기준으로 고정했다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 0 | **1** | 0 | 16 | 2(RLS 는 여전히 확인 불가 — 설계안 대기, 계획만 준비) |

CI 게이트 3개 중 2개(seam, mutation)는 실코드 회귀로 직접 검증해 **진짜로 작동함**을
확인했다. **1개(privacy-and-honesty 의 T0 검사 절반)는 검증 도중 진짜로 가짜인 것을
발견했고, 검증자 소유 픽스처 수정으로 그 자리에서 닫았다** (VF-017, S2 — 발견 즉시 해소).

---

## 1. CI 게이트 감사 — "통과만 보지 말고 고장을 내서 빨간불이 나는지 봐라"

GitHub Actions 를 직접 트리거하지 않았다(원격 저장소에 실제로 존재하는 CI 라 푸시는
공유 상태에 영향을 준다 — 총괄자 지시는 "보고만 해라"였지 트리거해도 된다는 뜻이 아니었다).
대신 `git worktree` 로 격리한 사본에서 **ci.yml 에 적힌 명령을 문자 그대로**, 각 잡이 쓰는
것과 동일한 방식으로 클린 venv 를 만들어 재현했다 — 공유 워킹트리는 전혀 건드리지 않았다.

### seam 잡 — 진짜로 작동한다

클린 venv(`pip install -r data-platform/requirements.txt`)로 `vf_56_dump_features.py
--source fixture` → `vf_56_join.mjs --strict` 를 그대로 실행:

```
정상 상태: exit 0, "5 feature(s) received a score - no violation"
backend/samples/scores.json 의 region_id 를 의도적으로 오염(BROKEN_ 접두):
  exit 1, "STRICT: 0 features received a score - join is broken (VF-003 shape)"
```

**판정: 진짜.** 실제 파일을 깨면 실제로 빨간불이 난다.

### mutation 잡 — 진짜로 작동한다

`intelligence/tests/test_factor_model.py` 를 VF-001 수정 **이전** 버전(커밋 `a8f1e34`,
항등식만 검사하던 버전)으로 격리 사본에서 교체하고 CI 스텝을 그대로 실행:

```
M1: "GATE WOULD FAIL (exit 1) - correctly detected weak safety net"
M2: "GATE WOULD FAIL (exit 1) - correctly detected weak safety net"
```

**판정: 진짜.** 안전망이 실제로 약해지면 게이트가 실제로 빨간불을 낸다.

### privacy-and-honesty 잡 — 절반은 가짜였다 (VF-017)

`tenant_id` 주입 검사는 격리 사본에서 `security.py` 의 `_reject_tenant_id_injection`
호출을 실제로 지우고 재현 — **exit 1, 위반 7건 정확히 나열.** 진짜다.

**T0 검사가 문제였다.** `routers/predictions.py` 의 `_confidence_for_tier` 클램프와
`_expected_revenue_for` 의 T0 null 처리를 실제로 지우고 `vf_t0_api.py --strict` 를
그대로 실행했더니:

```
$ (T0 신뢰도 클램프 + T0 금액 null 처리 둘 다 코드에서 제거한 상태)
exit 0
  above ceiling (=='high')        : 0   (contract: must be 0)
  rows with non-null expected_revenue_krw : 0
STRICT: no violations
```

**두 겹 다 지웠는데도 게이트가 초록불을 냈다.** 원인을 추적하니 픽스처의 결함이 아니라
**픽스처가 건드리는 실제 파이프라인 자체가 지금 이 값들을 절대로 만들어내지 않는다**:

- `prediction_store.compute_regions()` 는 `confidence_level="low"` 를 **하드코딩**한다
  (신뢰도 산식 자체가 아직 미구현 — Step 4/5). "low" 는 "medium" 상한을 절대 초과하지
  않으므로, 클램프 코드를 완전히 지워도 아무 것도 안 걸린다.
- `intelligence_client` 가 반환하는 `expected_revenue_krw` 도 **모든 tier 에서** 항상
  `None` 이다(Step 5 미구현, README §5). T0 전용 null 처리를 지워도 애초에 null 로 채울
  값 자체가 없으니 아무 것도 안 걸린다.

즉 `vf_t0_api.py` 가 만드는 `run_t0probe` 는 **실제 `/predictions` 파이프라인(진짜
compute_regions 경로)을 그대로 태우는데**, 그 파이프라인이 지금 이 순간 "high" 신뢰도나
"non-null" 금액을 낼 수 있는 상태 자체가 아니라서, 클램프·redact 코드가 있든 없든 검사가
**항상 통과한다.** CHARTER 가 말하는 "빈 테스트"의 정확한 사례다 — 이름은 검사처럼 보이지만
실제로는 상시 참을 단언한다.

**4~6회차의 내 이전 "독립 검증"들이 왜 이걸 못 잡았는가**: 그때는 `create_run(...,
regions=[...])` 로 `confidence_level='high'` 인 지역을 **직접 만들어** 주입해서 클램프
자체를 시험했다 — 맞는 방법이었지만, **CI 가 실제로 돌리는 `vf_t0_api.py` 는 그렇게 하지
않는다.** CI 게이트와 내 수기 검증이 서로 다른 것을 테스트하고 있었다.

**같은 회차 안에서 해소했다** (검증자 소유 `verification/fixtures/` 안의 수정이라 결함
수정이 아니라 픽스처 보강으로 처리, VF 번호는 매겼다 — 이게 CI 게이트를 무력화하는 실재
결함이었기 때문이다):

`vf_t0_api.py` 에 **명시적 시드 시나리오**를 추가했다 — `compute_regions()` 를 거치지
않고 `create_run(..., regions=[RegionScore(confidence_level="high", expected_revenue_p50=
200_000_000, ...)])` 로 직접 만든 지역 하나를 T0 run 에 넣어, 클램프/redact 코드
자체를 파이프라인 준비 상태와 무관하게 시험한다. 격리 사본에서 같은 회귀(클램프+redact
둘 다 제거)를 다시 주입해 재확인:

```
exit 1
STRICT: 3 violation(s):
  - T0 /regions (explicit-seed) returned non-null expected_revenue_krw ...
  - T0 /regions (explicit-seed) returned confidence.level=='high' ...
  - T0 /scores (explicit-seed) returned confidence_level=='high' ...
```

기존 "실 파이프라인" 시나리오는 **지우지 않고 그대로 남겼다** — "지금 실제로 무슨 값이
나오는가"를 정직하게 보여주는 것도 가치가 있고, Step 4/5 가 들어오면 그 시나리오도 저절로
의미를 갖게 된다. 둘 다 `--strict` 판정에 들어간다.

### S2 — VF-017 · `privacy-and-honesty` CI 게이트의 T0 검사가 실제 파이프라인에 대해 상시-통과였다 (검증자, 발견 즉시 해소)

- 위치: `verification/fixtures/vf_t0_api.py`(원인은 픽스처가 아니라 파이프라인의 미구현
  상태였지만, 게이트를 진짜로 만드는 책임은 픽스처 소유자인 검증자에게 있다)
- 재현: 위 "privacy-and-honesty 잡" 절 참조. `_confidence_for_tier` 클램프와
  `_expected_revenue_for` 의 T0 null 처리를 실제로 제거한 상태에서 원래 픽스처는
  `--strict` 로도 0 위반을 보고했다(거짓 초록불).
- 해소: 명시적 시드 시나리오 추가. 같은 회귀 재주입 시 3건 위반 정확히 검출 확인.
- 영향 범위: `privacy-and-honesty` 잡의 tenant_id 주입 검사는 영향 없음(별도 확인). 다른
  두 잡(seam, mutation)도 영향 없음.
- 근거: `05_scoring_spec.md` §2·§8-2, `DECISIONS.md` D-03, CHARTER "빈 테스트" 유형
- 담당: 검증자 (해소 완료)
- 나이: 7회차 신규 → 같은 회차에 해소

---

## 2. RLS 검증 계획 — C 의 설계안 도착 전 준비 (판정 아님)

`backend/`·`orchestrator/` 전체를 검색했으나 PostgreSQL/RLS 설계 문서는 아직 없다
(계약 문서의 요구사항 텍스트만 있음). 도착하면 아래 기준으로 판정한다.

### 핵심 질문: 애플리케이션 `WHERE` 절 격리인가, DB 정책 강제인가

총괄자가 짚은 그대로가 판정 기준이다 — **`WHERE tenant_id = ?` 를 의도적으로 빼고도 다른
테넌트 데이터가 안 나와야 진짜 RLS 다.** 이걸 확인하려면 애플리케이션 코드(ORM, ai 생성
쿼리)를 거치지 않고 **DB 에 직접** 접속해서 확인해야 한다 — 앱 코드가 맞게 짰는지를 보는
게 아니라, 앱 코드가 **틀리게 짜도** DB 가 막아주는지를 봐야 하기 때문이다.

### 체크리스트 (설계안이 오면 이 순서로 검증)

1. **`FORCE ROW LEVEL SECURITY` 가 걸려 있는가, `ENABLE` 만인가.**
   가장 흔한 함정 — `ENABLE ROW LEVEL SECURITY` 만 걸면 **테이블 소유자(owner) 역할은
   정책을 무조건 우회한다.** 앱이 테이블을 만든 역할로 접속하면(개발 환경에서 흔함)
   RLS 가 있는 것처럼 보이지만 실제로는 전혀 안 걸린다. `FORCE` 가 없으면 그 자체로 findings.
2. **앱의 런타임 DB 접속 역할이 superuser 도 table owner 도 아닌가.**
   둘 다 RLS 를 무조건 우회한다(정책과 무관하게). `\du`, `information_schema` 로 확인.
3. **정책의 `USING` 절이 세션 변수(`current_setting('app.tenant_id')` 등)를 참조하는가,
   아니면 상수/조건 없음(사실상 전체 허용)인가.**
4. **테넌트 컨텍스트를 `SET LOCAL` 로 세팅하는가, `SET`(세션 전체) 인가.**
   커넥션 풀링(pgbouncer 등)을 쓰면 `SET` 은 다음 요청까지 남아 **다른 테넌트로 재사용된
   커넥션에 이전 테넌트 컨텍스트가 새는** 고전적 사고 유형이다. `SET LOCAL` 은 트랜잭션
   종료 시 자동 리셋된다 — 이게 필수 조건이다.
5. **재현 스크립트로 직접 확인** — 앱 코드/ORM 을 전혀 거치지 않고, raw driver(예:
   `psycopg`)로 앱과 동일한 런타임 역할로 접속해:
   - 테넌트 A 컨텍스트를 세팅하고 `SELECT * FROM <table>` (WHERE 없이) 실행 →
     테넌트 A 행만 나와야 함.
   - 컨텍스트를 아예 세팅하지 않고 같은 쿼리 실행 → **0행이거나 에러**여야 함(기본값이
     "전체 허용"이면 그 자체가 결함 — deny-by-default 여야 한다).
   - 이 스크립트가 `verification/fixtures/` 산출물이 된다 — `vf_52_tenant.py` 가 앱
     레이어에서 하는 것과 같은 역할을, DB 레이어에서 한다.
6. **커넥션 풀 재사용 시나리오** — 같은 커넥션으로 테넌트 A → 테넌트 B 순서로 두 요청을
   흘려보내 B 요청에서 A 데이터가 안 보이는지 확인(4번의 실사용 시나리오 버전).

### 이번 회차에 미리 정해둔 판정 기준

- 1·2번 중 하나라도 실패 → **S1 후보**(RLS 가 있는 것처럼 보이지만 실제로 우회 가능).
- 4번에서 `SET`(LOCAL 아님) 사용 + 커넥션 풀링 사용 → **S1 후보**(풀링 환경에서 실제 유출
  경로).
- 5번의 "컨텍스트 미설정 시 0행/에러"가 아니라 전체 테넌트 데이터가 나오면 → **S1**
  (deny-by-default 위반, `06_governance.md` §1.2 자체 위반).
- 전부 통과하면 그때 "확인 불가" 를 "O" 로 전환한다 — 그 전까지는 설계 문서만으로
  판정하지 않는다(문서가 맞다고 적혀 있어도 실제 DB 로 재현 전엔 추정 등급).

### 추가 — C 의 설계안(`a6c4630`)이 이 회차 작업 도중 실제로 도착했다

체크리스트를 쓰는 중에 C 가 `backend/RECONCILIATION.md` 에 설계안을 올렸다(코드 변경
없음, "구현 안 함" 명시). **문서 검토만 했다 — 위 §2 의 5·6번(raw driver 재현, 실제 DB)은
구현이 없어 아직 실행할 수 없다. 아래는 "문서가 스스로 말하는 것"과 위 체크리스트를
대조한 결과이지, DB 로 재현한 판정이 아니다. RLS 는 여전히 확인 불가로 남긴다.**

| 체크리스트 항목 | 설계안이 다루는가 |
|---|---|
| 1. FORCE vs ENABLE | **다룸.** 4개 테이블 전부 `FORCE ROW LEVEL SECURITY` 명시, ENABLE 만으로는 소유자가 우회한다는 이유까지 정확히 적음 |
| 2. 앱 런타임 롤이 owner/superuser 아님 | **다룸.** `sellfinder_app` 이라는 별도 저권한 롤(`BYPASSRLS` 없음) 을 마이그레이션 롤과 분리 |
| 3. `USING` 이 세션 변수 참조 | **다룸.** `current_setting('app.current_tenant_id', true)` — 계약(`06_governance.md` §1.2)이 예시로 든 GUC 이름을 그대로 써서 VF-004 류의 "이름이 계약과 어긋남" 재발을 피함. `missing_ok=true` 로 세팅 누락 시 결과가 "새는 것"이 아니라 "전부 거부"가 되는 것까지 설계 이유를 정확히 적음(내 체크리스트가 요구한 것보다 한 걸음 더 나감) |
| 4. `SET LOCAL` vs `SET` | **다룸.** 트랜잭션 안에서 `set_config(..., true)` 로 강제, 단일 진입점(`get_db_session`) 으로 모아 라우터마다 반복 안 하게 함 — `get_tenant_id`/`_build_views()` 와 같은 패턴 재사용 |
| 5. raw driver 재현 스크립트 | **구현 전이라 없음.** 대신 "인메모리 목업으로 RLS 테스트하는 건 무의미하다, CI 에 진짜 Postgres 서비스 컨테이너가 있어야 한다"고 명시 — 내 계획과 같은 결론 |
| 6. 커넥션 풀 재사용 시나리오 | **다룸.** §3 이 "SET 을 커넥션 풀에서 쓰다 다음 요청에 값이 새는" 사고를 RLS 자체보다 흔한 실제 유출 경로로 명시하고 그게 이 설계의 핵심 근거임 |

체크리스트에 없던 것 중 눈에 띄는 것: `WITH CHECK` 절(조회뿐 아니라 삽입·수정 시에도
tenant_id 불일치를 거부 — 애플리케이션 버그가 있어도 2차 방어), `region_score` 에
`tenant_id` 를 비정규화(조인을 빠뜨리는 정책 실수 자체를 구조적으로 없앰), `set_config`
파라미터 바인딩으로 tenant_id 문자열 이어붙이기(SQL 인젝션 표면) 회피, 향후 뷰 생성 시
`security_invoker` 필요성까지 미리 남겨둠.

**잠정 판정: 문서 수준에서는 이 회차 체크리스트가 요구하는 6개 항목을 전부 다루고 있고,
일부는 더 신중하다.** 그러나 이건 "문서가 맞다"는 확인이지 "DB 가 실제로 막는다"는
확인이 아니다 — §2 의 원칙을 스스로 어기지 않기 위해 등급을 올리지 않는다. jin 승인 후
구현이 들어오면 5·6번(raw driver 스크립트, 풀 재사용 시나리오)을 실제 Postgres 에 대고
돌려서 최종 판정한다.

---


## 회차: 6회차 · 2026-08-17 · 판정 기준 HEAD `8e047fe` (판정 시작 시점에 고정)

지시받은 두 건을 판정하고, `verification/fixtures/` 세 개에 `--strict` 를 추가했다.
판정 시작 직후 `git rev-parse --short HEAD` → `8e047fe`, 워킹트리 클린 확인 후 시작했다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | **1** | 0 | 16 | 2 |

VF-013 확장 판정(정렬+필터+집계) 해소, evidence 규칙 4개 조항 자동 테스트 해소.
신규 S4 1건(VF-016, 무관한 관측). `verification/fixtures/vf_56_join.mjs`·`vf_t0_api.py`·
`vf_52_tenant.py` 에 `--strict` 추가 — CI 문자열 매칭 의존성 제거용, 결함 수정이 아니라
검증 인프라 변경이라 VF 번호를 매기지 않는다.

---

## 1. VF-013 확장 판정 — 정렬만이 아니라 필터·집계까지 같은 차단 뷰 위에서 일어나는가

C 가 이미 스스로 이 질문을 던지고 답한 상태였다 — 커밋 `2b8633e`(라운드 4 자체 재확인)가
`min_confidence` 필터에서 별도의 구멍(원시 confidence 로 필터링해 T0 클램프 우회)을 찾아
`_RegionView`/`_build_views()` 단일 초크포인트로 리팩터했다. **검증자는 이 주장을 그대로
받지 않고 세 벡터를 전부 새 시나리오로 독립 재현했다** (C 가 커밋 메시지에 적은 것과
다른 원시값·다른 지역 구성 사용):

```
[정렬] 원시 p50=555,555,555(suppressed) vs 15,000,000(일반), sort=revenue_desc/profit_desc:
  둘 다 -> [('77002', {p50:15,000,000}), ('77001', None)]   suppressed 지역이 꼴찌.

[필터] T0 run, 지역 원시confidence='high'(화면표시는 'medium'로 클램프됨):
  GET /regions?min_confidence=high -> 0 rows (클램프 이전 값이면 1 rows 나왔을 것)

[집계/페이지네이션] limit=2, sort=revenue_desc, 5개 지역(그중 1개 suppressed):
  page1: [('77002', 15M), ('77100', 2M)]  next_cursor 발급
  page2(cursor 사용): [('77101', 2M), ('77102', 2M)]  경계에서 값 뒤섞임·중복 없음
```

- `GET /scores` 도 같은 `_build_views()` 를 쓰는지 확인 — T0 run 의 `/scores` 응답도
  `confidence_level` 이 `'high'` 가 아니라 `'medium'` 으로 나옴을 확인 (두 엔드포인트가
  실제로 같은 소스에서 나온다).
- `pytest backend/tests -q` → **61 passed, 1 failed**(무관한 실패, 아래 VF-016 참조).

**판정: 정렬만 막은 게 아니다.** `_build_views()` 가 `/regions`·`/scores` 양쪽에서 필터·
정렬·페이지네이션·직렬화 전부의 유일한 데이터 소스이고, 셋 다 독립 재현으로 확인했다.
VF-013 **해소.**

---

## 2. evidence 규칙(§6) 4개 조항 — 자동 테스트가 진짜인지

5회차 시점엔 `intelligence/tests/test_evidence_rules.py` 가 미커밋이라 판정에서 뺐다.
이번 HEAD(`8e047fe`)에 `95d8a8e` 로 커밋된 것을 확인했다.

```
$ cd intelligence && python -m unittest tests.test_evidence_rules -v
7 tests, OK
$ python -m unittest discover -s tests -v
81 tests, OK
```

**"통과시키면서도 null 피처를 인용하게 만들 수 있으면 가짜다"** — B 가 자기 커밋 메시지에서
변이로 증명했다고 주장한 것을 **검증자가 B 의 변이와 다른 변이로 독립 재현**했다(B 가 고른
변이 지점을 그대로 베끼지 않았다 — `income_decile` 을 null 로 만드는 wrapper store 대신,
`price_acceptance` 함수 자체를 몽키패치해 "추정치"라는 그럴듯한 문구로 소득분위 6을 지어내는
변이를 주입):

```
[규칙3 변이] price_acceptance 를 패치 - income_decile=None 인데 "소득 6분위 ... - 추정치"를
  지어내도록 변경 → 7개 테스트 중 2개 FAIL:
  CAUGHT BY: test_evidence_is_a_known_placeholder_when_value_is_none
  CAUGHT BY: test_null_feature_never_leaks_a_fabricated_number_into_evidence
```

나머지 세 조항도 각각 별도 변이로 확인했다(B 의 커밋이 이미 자체 변이 증명을 했다고 주장한
지점과 겹치지 않게, category_penetration/competition/addressable_demand 세 함수를 패치):

```
[규칙1 — 값 인용] category_penetration 이 실제 지수 대신 "카테고리 소비 신호가 관측됨"
  이라고만 쓰도록 변이 → 3개 테스트 FAIL (값 인용 검사 + 비교 기준 검사 2개까지 동반 실패)
[규칙2 — 비교 기준] competition 이 benchmark 숫자·비교 단어를 다 빼도록 변이
  → 2개 테스트 FAIL
[규칙4 — 인과 금지] addressable_demand 에 "인구가 많기 때문에 잘 팔릴 것으로 예상됨"을
  덧붙이도록 변이 → 1개 테스트 FAIL (test_evidence_never_uses_causal_language)
```

**4개 조항 전부, 검증자가 고른 별도의 변이로 실패를 재현했다. 안전망이 실재한다.**

부수 확인: B 의 커밋 메시지가 "감사 중 크래시 버그 3개(addressable_demand, channel_availability
두 갈래)를 발견해 고쳤다"고 적은 부분 — `factors.py` 에 `if benchmark_value:` 가드 3곳
(L124, L261, L276) 실제로 들어가 있음을 코드로 직접 확인. 5회차에서 "이론상 가능하나
당시 표본으로는 재현 안 됨"으로 남겨둔 크래시 우려가 실제 근거 있는 것이었음이 이번에
드러났다 — 그때 판정("위반 없음")을 뒤집을 필요는 없다(그 표본에서는 실제로 안 터졌다),
다만 B 의 감사가 더 넓은 표본(희소 rural 요청)에서 진짜 버그를 찾아낸 것은 기록해 둔다.

**판정: 4개 조항 모두 자동 테스트로 강제된다. §6 전체가 더 이상 구멍이 아니다.**

---

## 3. CI 픽스처 판정 방식 — 문자열 매칭 대신 `--strict` 종료 코드

총괄자 지적대로 `vf_56_join.mjs`·`vf_t0_api.py`·`vf_52_tenant.py` 는 결과와 무관하게
exit 0 이었다. CI(`8e047fe`)는 이걸 알고도 출력 문자열 grep 으로 임시 우회했는데, 스스로
"출력 형식이 바뀌면 조용히 깨진다"고 명시했다 — 정확한 진단이다.

**세 픽스처 모두 `--strict` 플래그를 추가했다.** 기본 동작(플래그 없음)은 **완전히 그대로**다
— 기존 출력 문자열 한 줄도 안 바꿨다(`git diff` 로 확인: 삭제된 진단 출력 줄 0개, 전부
추가만). `--strict` 를 주면 위반을 내부적으로 집계해 있으면 종료코드 1, 없으면 0을 반환한다.
정상/고장 양방향을 전부 직접 재현해 확인했다(고장 재현은 공유 워킹트리를 건드리지 않으려고
`git worktree` 로 격리한 사본에서 진행 — vf_t0_api/vf_52_tenant 는 몽키패치, vf_56_join
은 `backend/samples/scores.json` 사본을 의도적으로 깨뜨림):

| 픽스처 | 정상 상태 `--strict` | 고장 주입 `--strict` |
|---|---|---|
| `vf_t0_api.py` | exit 0, "no violations" | T0 confidence 클램프 무력화 → exit 1, 위반 2건 나열 |
| `vf_52_tenant.py` | exit 0, "no violations" | `get_tenant_id` 무력화 → exit 1, 위반 7건 나열 |
| `vf_56_join.mjs` | exit 0, "5 feature(s)... no violation" | `scores.json` region_id 오염 → exit 1 |

**CI 쪽(`​.github/workflows/ci.yml`) 은 총괄자 소유라 직접 고치지 않았다** —
`verification/` 만 쓴다는 경계를 지켰다. 대신 아래를 그대로 적용하면 grep 세 군데가
전부 없어진다:

```yaml
# seam job:
- run: |
    python verification/fixtures/vf_56_dump_features.py --source fixture
    node verification/fixtures/vf_56_join.mjs --strict

# privacy-and-honesty job:
- run: python verification/fixtures/vf_t0_api.py --strict
- run: python verification/fixtures/vf_52_tenant.py --strict
```

이 변경 자체는 결함 수정이 아니라 검증 인프라 개선이라 VF 번호를 매기지 않는다.

---

## S4 — 낮음 (신규, 이번 회차 범위 밖 관측)

### VF-016 · `test_manifest_sigungu_prefers_real_vintage_over_fixture` 가 A 의 새 실데이터 발행 때문에 깨져 있다 (C, 무관 관측)

- 위치: `backend/tests/test_basemap.py:68`
- 내용: `pytest backend/tests -q` 실행 중 발견(이번 회차 지정 작업과 무관, 우연히 관측).
  `assert body["boundary_vintage"] == "2026-01-01"` 인데 실제로는 `"2026-07-01"` 반환.
  A 가 `45b7f3d`(DISPATCH-4, admdongkor 실경계)에서 sigungu 에 더 최신 실빈티지를 발행한
  게 원인 — 로직은 **올바르게** 최신 실빈티지를 골랐다(D-13). 테스트가 A 의 새 발행을
  못 따라간 것이지 회귀가 아니다.
- 근거: 없음(관측 기록용) — 결함이 아니라 낡은 기대값
- 담당: C
- 나이: 6회차 신규 — **0일**

---


## 회차: 5회차 · 2026-08-16 · 판정 기준 HEAD `525594a` (판정 시작 시점에 고정)

**판정 기준을 먼저 못 박는다.** 이번 회차는 `orchestrator/DISPATCH-2.md` §8 종료조건 4개를
판정한다. 대상 커밋: A `3925555` · B `bb55f25` · C `3e7e6e3` · D `acc99ac`. 판정 시작 직후
`git rev-parse --short HEAD` 로 `525594a` 를 먼저 기록했고, **아래 모든 판정은 이 커밋 기준이다.**
2회차에서 C-7 을 미커밋으로 오판했던 것과 같은 사고를 막기 위해, 이번엔 판정 도중 실제로
같은 상황이 재발했다 — 어떻게 처리했는지 §0 에 남긴다.

### §0. 판정 도중 발견한 워킹트리 오염 — 격리해서 처리했다

Check 4(§6 evidence 규칙)를 실행하려고 `intelligence/` 를 import 하던 중, 다음이 **미커밋
상태로 워킹트리에 이미 존재**하는 것을 발견했다:

```
 M intelligence/scoring/MODEL_CARD.md
 M intelligence/scoring/factors.py
?? intelligence/tests/test_evidence_rules.py   (untracked, git log 상 어떤 커밋에도 없음)
```

B 세션이 evidence 규칙 관련 작업을 **지금 이 순간에도 진행 중**이라는 뜻이다. 워킹트리에서
그냥 import 했다면 판정이 `525594a` 가 아니라 "판정 시점에 우연히 얼마나 진행돼 있었는가"에
좌우됐을 것이다. 그래서:

1. `git worktree add --detach <임시경로> 525594a` 로 **판정 전용 격리 체크아웃**을 만들었다
   (B 의 라이브 세션이 쓰고 있는 공유 워킹트리는 전혀 건드리지 않음 — 다른 폴더를 새로 만드는
   `git worktree`는 원본 워킹트리에 영향이 없다).
2. Check 4 는 전부 이 격리 체크아웃 안에서만 실행했다.
3. 끝난 뒤 `git worktree remove`로 정리했다 — 저장소에 흔적이 남지 않는다.

B 의 미커밋 변경(`factors.py`의 `benchmark_value` None/0 방어, `test_evidence_rules.py`)은
**이번 회차 판정에 전혀 쓰지 않았다.** 다음 회차가 커밋된 뒤 판정한다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | **1(+VF-013 이월)** | 0 | 15 | 2 |

**DISPATCH-2 §8 종료조건 4개 — 넷 다 `525594a` 기준으로 PASS.** 새 결함은 없다.
1건(VF-015, S4)은 문서-코드 사소 불일치. **VF-013 은 지시대로 이번 회차 판정 대상에서
제외했다** — 수정 커밋(`5982238`)이 이 HEAD 의 조상에 있지만, 그 자체를 검증하는 것은
다음 회차 일이다.

---

## DISPATCH-2 §8 종료조건 4개 — 판정

### 1. `POST /predictions` 가 202+`run_id` 를 반환하고 그 run 의 `/scores` 가 B 가 계산한 값을 준다

C 자신의 이음매 테스트(아래 조건 3)와는 **별개로** 검증자가 직접 새 시나리오로 재현했다:

```
POST /v1/predictions {product_ids:[prd_x], region_level: adm_dong} → 202, elapsed 0.0150s
  body: {run_id: run_ccff2d9ed413, status: queued, estimated_seconds: 30, data_tier: T1}
POST 리턴 직후 run.status == 'queued'  ← 계산이 끝나기 전에 202 가 나갔다는 증거
...대기...
run.status == 'succeeded', n_regions=5

독립적으로 intelligence_client.run_prediction() 을 직접 호출한 ground truth 순위:
  ['91001001', '91001003', '91001004', '91001005', '91001002']
GET /scores 가 실제로 반환한 순위:
  ['91001001', '91001003', '91001004', '91001005', '91001002']
match: True
```

202 가 **동기 계산을 기다리지 않고** 나가는 것(15ms, wall-clock)과 `/scores` 가 B 의 실제
`predict_batch` 순위와 바이트 단위로 일치하는 것 둘 다 확인. **PASS**

### 2. `backend` 에 `_build_demo_regions()` 가 존재하지 않는다

```
$ grep -rn "_build_demo_regions" backend/ --include=*.py
backend/app/services/job_runner.py:12: (주석 — "삭제했다"는 설명)
backend/app/services/prediction_store.py:15: (주석 — "더 이상 여기 없다"는 설명)
$ grep -n "def _build_demo_regions" backend/app/services/*.py
(0건)
```

함수 정의 자체는 0건 — 남은 건 "이걸 지웠다"는 주석뿐이다. **PASS**

### 3. B↔C 이음매 테스트가 어느 쪽 스위트에서든 실행되고 통과한다

`backend/tests/test_intelligence_seam.py` — B 의 `predict_batch` 를 직접 호출한 결과를
ground truth 로 삼고, 그 **동일 요청**을 실제 HTTP + job worker 경로로 흘려보내 순위가
같은지 비교한다(위조 불가 — "후보 지역 전부 같은 점수"가 아님을 먼저 확인하는 자기 검증
테스트까지 포함).

```
$ backend/.venv/Scripts/python.exe -m pytest backend/tests/test_intelligence_seam.py -v
test_predict_batch_ground_truth_is_not_degenerate PASSED
test_scores_response_matches_predict_batch_ranking PASSED
2 passed

$ backend/.venv/Scripts/python.exe -m pytest backend/tests -q
60 passed  (4회차 대비 +21 — C-1~C-5 신규 테스트 포함)
```

VF-003 이 재발하지 않도록 설계된 테스트라는 점을 코드로 확인했다 (`test_intelligence_seam.py`
독스트링이 VF-003 을 직접 인용). **PASS**

### 4. 검증이 evidence 규칙(§6) 4개 조항에 대해 구멍이 아닌 판정을 낸다

**가장 중요한 조건이라 가장 크게 봤다.** §0 의 격리 체크아웃 안에서, B 의 실제
`model.predict_batch()` 를 호출 조합 4가지(cvs/mid, hypermarket/premium, online_marketplace/
value, cvs/luxury) × adm_dong 지역 50개 × 8요인으로 돌려 **evidence 문자열 1,600개**를 얻고
네 조항을 전수 검사했다.

```
total evidence strings: 1600
crashes: 0
causal violations: 0            (금지1: 인과 표현 "때문에/그래서/덕분에" 등)
null-cites-number violations: 0 (금지2: value=None 인데 evidence 가 숫자를 지어냄)
no-comparison false-positives만 50건 (전부 "온라인 채널은 경쟁강도를 안 씀" 류의 규칙
  설명 — 애초에 값·비교가 필요 없는 문장이라 §6.1-2 적용 대상이 아님. 수기로 50건 전부
  확인, 실제 위반 0건)
```

조항별 판정:

| 조항 | 요구 | 판정 | 근거 |
|---|---|---|---|
| §6 반드시 1 — 실제 피처값 인용 | value 가 있으면 evidence 에 그 값이 보여야 함 | **위반 없음** | 코드 레벨: `factors.py` 의 모든 factor 함수가 evidence f-string 을 `FactorResult` 에 넣는 **바로 그 변수**(`relevant_pop`, `spend_index`, `density`, `income_decile` 등)로 만든다 — 독립된 두 번째 숫자가 아니라 같은 변수의 두 표현. 1,600건 실측 0 위반. |
| §6 반드시 2 — 비교 기준 동반 | benchmark 가 있으면 그 값과 "평균/대비/기준" 표현 동반 | **위반 없음** | 1,600건 실측, "평균"/"대비"/"전국 평균 100" 류 표현이 benchmark 있는 모든 케이스에 동반. |
| §6 금지 2 — 모델이 안 쓴 근거 지어내기(null 피처 인용 포함) | value=None 인 factor 의 evidence 가 숫자를 지어내면 안 됨 | **위반 없음** | value=None 케이스(온라인 채널 competition, 소득분위 없음 등) 전부 "~데이터 없음 - 중립(1.0)으로 처리" 류 정직한 문구뿐, 수치 0건. 각 factor 함수가 `if X is None: return FactorResult(..., None, ..., "~없음")` 형태로 **조기 반환**하는 구조상 애초에 없는 값을 포맷 문자열에 넣을 코드 경로가 없다. |
| §6 금지 3 — 인과 주장 | "때문에/그래서 잘 팔릴 것" 류 상관→인과 비약 금지 | **위반 없음** | 1,600건 전수 검색 0건. evidence 는 전부 "X 대비 Y배" 식 비율 서술이지 "그래서 팔린다"류 서술이 아니다. |

**부기 — 이 판정과 별개로, 이 규칙을 강제하는 자동 회귀 테스트는 `525594a` 시점에 아직
없다.** B 가 `test_evidence_rules.py` 를 작업 중이지만(§0) 미커밋이라 이번 판정엔 안 썼다.
즉 "지금 코드가 규칙을 지킨다"는 확인됐지만 "미래의 변경도 계속 지킨다"는 아직 자동으로
보장되지 않는다 — 다음 회차에서 그 테스트가 커밋되면 재확인 대상이다(신규 VF 번호를 매기지
않는다. 결함이 아니라 아직 안전망이 없는 상태라서 VF-001 의 "안전망 부재"와 같은 결이지만,
지금 코드 자체는 실측으로 깨끗해서 findings 로 올리지 않는다).

**PASS** — 4개 조항 모두 "구멍"이 아니라 "위반 없음"으로 판정을 냈다.

---

## 종료 조건 총평

**넷 다 참이다. DISPATCH-2 2차 사이클이 `525594a` 기준으로 종료 조건을 충족했다.**
1차 사이클(DISPATCH.md §6)이 "지도가 실제로 칠해지는가"를 검증했다면, 이번은 "예측이
실제로 생성되는가"였다 — POST 부터 B 의 실제 계산을 거쳐 evidence 문장까지 인위적 데이터
없이 전 구간을 검증자가 직접 재현했다.

---

## S4 — 낮음 (신규)

### VF-015 · `intelligence/README.md` 의 `predict_batch` 시그니처 문서와 실제 호출부가 살짝 다르다 (B/C, 정보성)

- 위치: `intelligence/README.md`(B-1 산출물) vs `backend/app/services/intelligence_client.py`
- 내용: C 의 `run_prediction()` 은 README 가 공개한 시그니처를 따라 `predict_batch` 를
  호출하지만, `product_attributes`/`price_tier`/`seasonality_profile` 등 선택 인자를
  아직 넘기지 않는다(`intelligence_client.py` 자신의 주석이 이유를 밝힘 — "Backend has
  no product catalog yet"). 그 결과 지금 `/scores` 에 실리는 예측은 8요인 중 다수가 중립
  (1.0)으로 나온다 — **틀린 값이 아니라 입력이 아직 다 안 채워진 것**이고, 그 사실이
  코드 주석에 정직하게 적혀 있다. 계약 위반도 은폐도 아니라 S4.
- 판단: DISPATCH-2 C-1~C-5 어디에도 "product_attributes 전달"이 지시 항목으로 없었으므로
  미이행이 아니라 **다음 사이클 범위**. 기록만 해 둔다 — 나중에 "왜 evidence 가 대부분
  중립인가"를 다시 묻는 일을 막기 위해서다.
- 근거: `intelligence/README.md`, `backend/app/services/intelligence_client.py`
- 담당: C (다음 사이클 후보)
- 나이: 5회차 신규 — **0일**

---

## 이월 — 이번 회차에서 판정하지 않음

- **VF-013** (S2, `sort=revenue_desc`/`profit_desc` 원시값 정렬) — 총괄자 지시로 이번 회차
  판정 대상에서 명시적으로 제외했다. 수정 커밋 `5982238` 이 이 HEAD(`525594a`)의 조상에
  이미 들어있는 것은 확인했지만(`git log --oneline`), **그 수정이 실제로 문제를 닫는지는
  검증하지 않았다** — 지시대로 다음 회차로 넘긴다.

---


## 회차: 4회차 · 2026-08-16 · HEAD `822a259`

검증 범위: 총괄자가 지정한 2건만 — B 의 VF-012 해소(`7f2222a`), C 의 VF-010 해소(`19373ff`).
3회차 종료 시점 미해결은 이 둘뿐이었고, 나머지 폴더는 이번 회차 대상이 아니다. 커밋 직전
재현: `git log --oneline -3` (3회차의 절차 메모 적용) — 이 둘 이후 새 에이전트 커밋 없음
(`c5deeb0`·`822a259`는 총괄자 자신의 기록 커밋).

두 지시 모두 **자기 테스트를 그대로 믿지 않고, 지시받은 대로 독립된 재현으로 다시 확인했다.**
그 과정에서 지시받은 두 건과는 별개로 **신규 결함 1건(VF-013)** 과 **문서 사소 결함 1건(VF-014)**
을 찾았다 — 둘 다 열어둔다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 1 | **2** | 0 | 11 | 2 |

이번 회차 해소: VF-010 · VF-012 (지시받은 2건, 아래 상세).
이번 회차 신규: **VF-013**(S2, 신규 — sort=revenue_desc 가 미차단 원시값으로 순위를 매김)
· **VF-014**(S4, 신규 — 모델 카드 지역유형별 표에 재현 명령 누락, 수치 자체는 독립 재현 성공).

---

## 해결 확인됨 (4회차)

### VF-010 · suppressed 셀 원시값 차단 (C, `19373ff`)

C 는 응답·로그·에러 메시지 세 경로를 동시에 막았다고 주장했다. 지시받은 대로 **예외 유도를
직접 시험**했다 — C 자신의 테스트(`tests/test_privacy.py`, 원시값 `918273645`를 심어 7개
시나리오 검사, `pytest backend/tests -q` → **39 passed**)를 재실행한 뒤, **C 가 고르지 않은
별도의 예외 시나리오**를 검증자가 직접 만들어 독립적으로 시험했다:

```
# C의 SuppressedValueError 가 아니라 완전히 다른, 흔한 버그 모양의 예외를 주입:
# "미래에 어떤 코드가 실수로 원시값을 문자열에 끼워 넣는" 상황을 재현
ValueError(f"unexpected internal state: raw value was {RAW} for region 11290")
→ prediction_store.get_run 을 이 예외를 던지도록 몽키패치, /v1/predictions/.../regions 호출

결과: status 500, body {"error":{"code":"internal_error","message":"일시적인 오류가 발생했습니다."}}
RAW value leaked in body? False
```

전역 `Exception` 핸들러(`app/main.py`)가 예외 타입과 무관하게 `str(exc)`를 클라이언트에
돌려주지 않는다는 주장이 **C 가 상정한 시나리오 밖에서도** 성립함을 확인했다. 서버 로그
(`exc_info`)에는 traceback 이 남지만 이는 계약이 막는 "응답"이 아니라 운영자 전용 채널이라
위반이 아니다.

- **응답 경로**: `_expected_revenue_for()`가 `data_tier=="T0"` 와 `coverage_flag=="suppressed"`
  둘 다 독립적으로 검사 — VF-005(한 겹만 막아 신뢰도가 새던 사례)를 의식한 이중 검사.
- **로그 경로**: `privacy.redact()`가 사실만 로그(`region_id`·`field`), 원시값은 로그 인자에
  아예 전달되지 않음 — 코드 구조상 못 새는 형태 (`caplog` 로 재검증).
- **에러 메시지 경로**: `SuppressedValueError.__str__`가 생성자 시점부터 원시값을 받지
  않음 + 전역 핸들러가 심층 방어. 위에서 C 가 안 쓴 예외 타입으로도 확인.
- 근거: `06_governance.md` §2.3, `05_scoring_spec.md` §8-6
- 담당: C, 커밋: `19373ff`

**단, 이 판정은 "지시받은 세 경로"에 한정된다 — 검증 도중 네 번째 경로(정렬 순서)가 열려
있는 것을 발견했다. VF-013 참조.**

### VF-012 · 백테스트 wMAPE·PI coverage + 모델 카드 (B, `7f2222a`)

지시받은 대로 지표가 실제로 계산되는지, 상수나 항등식이 아닌지, 그럴듯한지, 누수 가드가
여전히 작동하는지 전부 독립적으로 재현했다.

**1) 지표가 실제 계산인지 — 상수/항등식 여부 검사**

```
perfect wmape: 0.0
garbage wmape (무작위 예측, 커야 함): 15.64
narrow-band coverage, perfect 예측 (거의 1이어야 함): 1.0
narrow-band coverage, garbage 예측 (0으로 붕괴해야 함): 0.0
```

무작위/왜곡된 입력에 대해 지표가 실제로 나빠진다 — VF-001 이 잡았던 "합이 자기 자신과만
비교되는 항등식" 부류의 가짜가 아니다. `test_wmape_worked_example`·`test_pi_coverage_worked_example`
도 손계산값(35/300, 0.75)과 직접 대조하는 방식이라 항등식이 아니다.

**2) B 가 카드에 올린 수치를 검증자가 독립적으로 재현**

```
$ cd intelligence && python -c "... harness.run_backtest(...) ..."
n_splits=6 mean_rho=0.922 mean_lift=2.737 mean_wmape=0.425 mean_coverage=0.800
  2026-01: rho=0.941 lift=2.698 wmape=0.482 cov=0.818
  2026-02: rho=0.919 lift=2.522 wmape=0.459 cov=0.786
  2026-03: rho=0.892 lift=2.669 wmape=0.494 cov=0.837
  2026-04: rho=0.947 lift=2.835 wmape=0.392 cov=0.773
  2026-05: rho=0.893 lift=2.789 wmape=0.385 cov=0.814
  2026-06: rho=0.941 lift=2.910 wmape=0.335 cov=0.773
```

`intelligence/scoring/MODEL_CARD.md` §3 표와 **소수점까지 정확히 일치.**

**3) 지역유형별 분해 표도 별도로 독립 재현** (카드에 재현 명령이 없어 검증자가 직접
`model.predict_batch` + `dataset["_profiles"]`의 `region_type` 으로 그룹핑해 재구성):

```
major_city   n=  60 rho=0.678 wmape=0.567 coverage=0.883
metro        n=  96 rho=0.782 wmape=0.343 coverage=0.865
mid_city     n=  84 rho=0.688 wmape=0.695 coverage=0.810
rural        n=  20 rho=0.451 wmape=0.844 coverage=0.200
```

카드의 표와 **정확히 일치** — 지어낸 숫자가 아니다. (이 표 자체엔 재현 명령이 빠져 있다는
점은 별도로 VF-014 로 남긴다.)

**4) 누수 가드가 여전히 작동하는지 재확인**: `test_guard_actually_fires_against_a_store_with_the_bug`
가 60개 테스트 안에 포함돼 통과 (`cd intelligence && python -m unittest discover -s tests -v`
→ **60 passed**, 3회차 대비 신규 회귀 없음). `_leaky_latest_value` 를 주입한 깨진 스토어에
대해 `assert_no_leakage_before_cutoff` 가 여전히 `LeakageDetectedError` 를 던진다.

**5) 모델 카드 내용이 실제 코드와 맞는지 대조** (지시받은 두 가지 특히 확인):

- **"전부 합성 데이터"**: `intelligence/synthetic/`·`intelligence/scoring/` 전체에서 CSV 읽기·
  HTTP 요청·외부 파일 로드 코드 0건 (`grep`). 생성기(`generate.py`, seed=42)만 데이터 소스.
- **"`spend_krw` 는 항상 null" (ADR-004)**: `synthetic/demand_gen.py:134` 에 `"spend_krw": None`
  가 하드코딩돼 있고 이 값을 다른 경로로 채우는 코드가 없음 — `test_spend_krw_is_always_null_card_mcc_not_licensed`
  통과와 코드 양쪽으로 일치.
- **"`tenant_calibration` 전 tier 중립 고정"**: 2·3회차에서 이미 확인된 사실과 모순 없음
  (`scoring/factors.py`, 변경 없음).

카드에 적힌 수치·전제 전부가 검증자의 독립 재현·코드 대조와 일치한다. `wMAPE 0.43 (목표
≤0.25 미달)`처럼 목표 미달을 숨기지 않고 그대로 실은 것도 확인 — "거짓 완료" 유형이 아니다.

- 근거: `05_scoring_spec.md` §5.2·§5.3
- 담당: B, 커밋: `7f2222a`

---

## S2 — 심각 (신규)

### VF-013 · `sort=revenue_desc`/`profit_desc` 가 미차단 원시값으로 정렬해 suppressed 셀의 상대 크기가 샌다 (C)

- 위치: `backend/app/routers/predictions.py` (VF-010 수정 범위 밖 — diff 에 없던 기존 코드)
  ```python
  if sort in ("revenue_desc", "profit_desc"):
      regions.sort(key=lambda r: r.expected_revenue_p50 or -1, reverse=True)
  ```
  이 정렬은 `r.expected_revenue_p50` **원본**을 쓴다 — `privacy.redact()`를 거친 뒤의 값이
  아니라, 응답에 실제로 나가는 `expected_revenue_krw`(=null)가 계산되기 **전** 단계.
- 재현:
  ```
  suppressed 지역(region_id=99999, 원시 p50=999,999,999)과
  일반 지역(region_id=11305, p50=20,000,000)을 같은 run 에 넣고
  GET /v1/predictions/{run_id}/regions?sort=revenue_desc

  결과: [('99999', None), ('11305', {'p10':10000000,'p50':20000000,'p90':30000000})]
  ```
  `expected_revenue_krw` 는 `null` 로 정확히 가려지지만, **정렬 순서가 원시값을 그대로
  반영해 suppressed 지역이 1위로 올라온다.** 클라이언트는 금액을 못 보지만 "이 지역이
  일반 지역보다 수요가 크다"는 상대 정보를 얻는다 — suppression(k-익명성 하한 이하 셀은
  비교조차 노출하지 않음)의 취지를 우회한다.
- **VF-010 이 막은 세 경로(응답 본문·로그·에러 메시지)와는 다른 네 번째 경로다.** C 의
  `privacy.redact()`설계는 "값이 응답에 실리는 자리"를 한 곳으로 모았지만, 정렬 키 계산은
  그 초크포인트를 거치지 않고 원본 필드를 직접 읽는다 — VF-005 가 보여준 "한 겹만 막고
  다른 겹을 놓친" 실패 모양과 같은 종류다(이번엔 C 자신의 커밋 메시지가 그 정확한 교훈을
  언급했는데, 그 교훈이 미친 범위 밖에 이 정렬 코드가 있었다).
- 근거: `06_governance.md` §2.3, `05_scoring_spec.md` §8-6
- 담당: **C**
- 나이: 4회차 신규 — **0일**

---

## S4 — 낮음 (신규)

### VF-014 · 모델 카드의 지역유형별 분해 표에 재현 명령이 빠져 있다 (B) — 문서 사소 결함

- 위치: `intelligence/scoring/MODEL_CARD.md` — 파일 서두에 "재현 명령은 각 절에 붙여뒀다",
  말미에 "재현 불가능한 수치는 이 카드에 올리지 않았다"고 적혀 있으나, 코드 펜스(` ``` `)는
  파일 전체에 **한 쌍뿐**(§3 전체 백테스트 표용). 지역유형별 분해 표(metro/major_city/
  mid_city/rural)는 별도 재현 명령이 없다.
- 결과: **수치 자체는 지어낸 게 아니다** — 검증자가 `dataset["_profiles"]`의 `region_type`
  으로 직접 그룹핑해 독립 재현했고 카드 표와 정확히 일치했다 (위 VF-012 §해결 확인 3번 참조).
  즉 이건 "거짓 완료"가 아니라 카드가 스스로 한 약속(모든 절에 재현 명령)을 그 표 하나에서만
  못 지킨 문서 완성도 문제다.
- 근거: `05_scoring_spec.md` §5.3 (모델 카드 요구사항)
- 담당: **B**
- 나이: 4회차 신규 — **0일**

---

## 남은 미해결 — 명시

**총괄자가 이번 회차에 지정한 VF-010·VF-012 는 둘 다 닫혔다.** 대신 검증 도중 신규 2건이
열렸다:

| VF | 등급 | 상태 | 왜 남았는가 |
|---|---|---|---|
| VF-013 | S2 | 열림 | `sort=revenue_desc`/`profit_desc` 가 redact 되지 않은 원시값으로 정렬 — 이번 회차에 처음 발견, 아직 수정 커밋 없음 |
| VF-014 | S4 | 열림 | 모델 카드 §3 지역유형별 표에 재현 명령 누락 — 수치는 검증됨, 문서만 보완 필요 |

3회차까지 열려 있던 항목(VF-001~012) 중 이번 회차 대상이 아니었던 것은 없다 — 3회차
종료 시점에 미해결이던 건 VF-010·VF-012 두 개뿐이었고 이번에 둘 다 닫혔다. **1~3회차에서
연 것 중 지금 열려 있는 건 없다.**

---


## 회차: 3회차 · 2026-08-16 · HEAD `641cfa2`

**정정: 2회차 VF-004 판정이 관측 시점 오류였다.** `git log` 상 `a760b31`(C-7·C-8, 하드코딩
3종 제거) 이 검증자의 2회차 커밋(`0497f4f`)**보다 먼저** 마스터에 올라가 있었다. 검증자가
워킹트리를 관측한 시점엔 `a760b31` 이 아직 없었는데, findings 를 쓰고 커밋하는 사이 C 의
커밋이 먼저 들어갔고, 커밋 직전 재확인을 하지 않아 이미 해소된 것을 "여전히 열림"으로
기록했다. C 가 `backend/RECONCILIATION.md`(`641cfa2`)에서 먼저 이 순서를 지적하고 자체
재확인 결과를 남겼다 — 검증자는 그 지적을 그대로 믿지 않고 **독립적으로 다시 실행**해
아래에 확인했다.

### VF-004 · 재확인 → 해결 확인됨

- 재현: `PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py`
- 결과 (HEAD `641cfa2`, 독립 재실행):
  ```
  A 실제 발행: sido=['2026-01-01','2026-07-01'] sigungu=['2026-01-01'] adm_dong=['2026-01-01']
  C 광고:      sido=['2026-07-01','2026-01-01'] sigungu=['2026-01-01','fixture'] adm_dong=['2026-01-01']

  C.get(sido, 2026-01-01) -> 200   C.get(sido, 2026-07-01) -> 200
  C.get(sigungu, 2026-01-01) -> 200   C.get(adm_dong, 2026-01-01) -> 200
  (1회차의 404 BOUNDARY_VINTAGE_NOT_FOUND 재현 안 됨 — A 가 실제로 발행한 빈티지는 전부 200)

  C 가 광고하는 sido/2026-01-01, sido/2026-07-01 -> A 에 있는가? 둘 다 True (2회차의 거짓 광고 없음)

  zoom, sido: A minzoom=0 maxzoom=10 / C minzoom=0 maxzoom=10  (일치)
  ```
  `sigungu` 의 `'fixture'` 항목은 지어낸 값이 아니다 — `basemap_registry.py:24-25,46` 이
  `data-platform/fixtures/manifest-fixture.json`(A 의 D-12 sigungu 픽스처)을 코드로 직접
  가리켜 읽는다. `glob.glob` 으로 산출물 디렉터리를 스캔하는 경로와 별도로 하드코딩된
  한 개 파일 경로라 검증자가 직접 열어 대조: 값 일치.
- `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` → **32 passed** (2회차 28,
  C-7/C-8 관련 신규 테스트 포함).
- 근거: `ADR-002-artifact-publishing.md`, `DECISIONS.md` D-08·D-13·D-14
- 담당: C, 커밋: `a760b31`
- **나이: 1회차부터 2회차까지 1일, 3회차에 종결.**

### 요약 정정 (2회차 표 대체)

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 2 | **2** | 0 | 9 | 2 |

**DISPATCH.md 1차 지시분에 걸린 findings 는 이제 전부 닫혔다.** 열려 있는 것은 1차 범위
밖이었던 VF-010(변경 없음)·VF-012(문서화된 미구현, B-4 후속 Step 범위) 둘뿐이다.

### 절차 메모 (재발 방지)

검증 결과를 파일에 쓰고 커밋하기 **직전에** `git log --oneline -3` 으로 그사이 새 커밋이
들어오지 않았는지 다시 본다 — 특히 여러 에이전트 세션이 동시에 커밋하는 상황에서는
"관측"과 "기록"사이의 간극이 findings 를 낡게 만들 수 있다. 이번엔 그 낡음을 C 가 먼저
잡아 지적했고, 검증자는 그 지적을 근거로 삼지 않고 동일한 재현 경로를 처음부터 다시 돌려
직접 확인했다.

---


## 회차: 2회차 · 2026-08-16 · HEAD `d942dd4`

검증 범위: `orchestrator/DISPATCH.md` 1차 지시 이행 여부. 대상 커밋 —
A `a0a5eb2` · B `158c4d3` `4436bde` `d7421f9` `775be91` · C `a8f1e34` `61c4eaf` ·
D `1b4296e` `d942dd4` · 총괄자 게이트 정정 `648669c`.
(`4707fc5` data-platform 은 DISPATCH 1차 범위 밖의 후속 커밋이라 이번 판정 대상이 아니다.
`backend/app/services/basemap_registry.py` 등 C 의 후속 작업은 **커밋되지 않은 워킹트리 상태**라
이번 회차에서 판정하지 않는다 — 다음 회차 대상.)

기준은 `DISPATCH.md` §6 종료조건 4개다. **넷 다 이번 회차에 참으로 전환됐다.**
1회차 미해결 10건 전건을 재확인했고, 회차 중 신규 결함 1건(VF-011)을 발견해 같은 회차 안에서
해소까지 확인했다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 미해결 합계 | 추정 | 해결됨(누적) | 확인 불가 |
|---|---|---|---|---|---|---|---|
| 0 | 1 | 0 | 2 | **3** | 0 | 8 | 2 |

이번 회차 신규: VF-011(발견 즉시 해소) · VF-012(신규, S4, 문서화된 미구현).
이번 회차 해소: VF-001 · VF-002 · VF-003 · VF-005 · VF-006 · VF-007 · VF-008 · VF-009 · VF-011.
이번 회차도 열림: VF-004(S2, **3회차에서 해소 — 관측 시점 오류였음**) · VF-010(S4, 변경 없음) · VF-012(S4, 신규).

---

## DISPATCH §6 종료조건 4개 — 판정

| # | 조건 | 재현 | 결과 |
|---|---|---|---|
| 1 | `vf_56_join.mjs` 전건 매칭 | 아래 VF-003 참조 | **PASS** |
| 2 | `vf_t0_api.py` above ceiling 0건 | `backend/.venv/Scripts/python.exe verification/fixtures/vf_t0_api.py` | **PASS** — `/regions`·`/scores` 모두 0건 |
| 3 | `vf_52_tenant.py` 주입 경로 전부 400 | `backend/.venv/Scripts/python.exe verification/fixtures/vf_52_tenant.py` | **PASS** — 실제로는 6이 아니라 7경로(쿼리 5·헤더 2)가 있고 **7/7 전부 400** |
| 4 | `vf_51_mutation.py` M1·M2 잡힘 | `python verification/fixtures/vf_51_mutation.py M1` / `M2` | **PASS** — 둘 다 `failures>0`으로 잡힘 |

넷 다 참 — **1차 지시 사이클 종료 조건이 충족됐다.**

---

## 해결 확인됨 (2회차)

### VF-001 · 요인 분해 불변식 항등식 검사 문제 (B-1)
- 재현: `python verification/fixtures/vf_51_mutation.py M1` / `M2`
- 결과: M1 → `test_display_effect_agrees_with_exported_log_contribution`,
  `test_log_contribution_matches_each_factors_own_multiplier`,
  `test_value_over_benchmark_reconstructs_log_contribution` 3건이 잡음.
  M2 → 위 중 2건이 잡음. **1회차 SURVIVED → 2회차 CAUGHT.**
- 담당 B, 커밋: `158c4d3`

### VF-002 · `tenant_id` 주입 무시 (C-4)
- 재현: `verification/fixtures/vf_52_tenant.py`
- 결과: 쿼리(`tenant_id`·`tenantId`) 5건 + 헤더(`X-Tenant-Id`·`Tenant-Id`) 2건, **7/7 전부
  `400 TENANT_ID_NOT_ALLOWED`.** 1회차엔 전부 200 이었다.
- 담당 C, 커밋: `a8f1e34`

### VF-003 · 경계 타일 ↔ 점수 조인 키 불일치 (A-2, D-20)
- 재현: `data-platform/.venv/Scripts/python.exe verification/fixtures/vf_56_dump_features.py --source fixture`
  → `node verification/fixtures/vf_56_join.mjs`
- 결과: `region_id` 가 이제 properties 에 실제로 있다 (`'region_id' in properties -> True`,
  250/250 피처). `scores.json` 의 5개 region_id 전부 매칭, **미정의 promoted id 0/250.**
  245/250 "MISS" 는 결함이 아니다 — `scores.json` 은 250개 시군구 중 5개짜리 데모 표본이고,
  나머지는 애초에 점수가 없어 회색이 맞다.
- **독립 교차검증**: D 자신의 신규 테스트(`console/tests/join.test.mjs`, A 의 실제 커밋된
  `.pmtiles` 픽스처를 직접 디코드)도 동일 결론 — `node --test tests/join.test.mjs` → 3/3 통과,
  `join: A's real committed .pmtiles fixture matches C's real scores.json, end to end` 통과.
  검증자 하네스와 D 의 자체 테스트가 서로 다른 구현으로 같은 결론에 도달했다.
- **주의 — 근본 원인은 두 개였고 이번 회차에 둘 다 닫혔다.** 회차 도중에만 발견 순서가 갈렸다.
  1. **조인 키 자체 결함 (A-2, ADR-005/D-20)** — `region_id` 가 properties 에 없던 것. **A 의
     `a0a5eb2` 로 해소.**
  2. **표본 파일 간 레벨/빈티지 불일치 (신규, VF-011)** — `backend/samples/manifest.json` 이
     `adm_dong`/`2026-01-01` 을 광고하는데 `scores.json` 은 `sigungu`/`fixture`. 조인 키 필드
     (`source_layer`/`feature_id_property`) 값이 우연히 레벨 무관하게 같아서 이번 하네스는 실패로
     드러나진 않았지만, 실제로 D 가 `manifest.tile_url` 로 타일을 받아온다면 존재하지 않는
     `adm_dong` 아티팩트를 요청하게 됐을 결함이다. **아래 VF-011 참조, C 의 `61c4eaf` 로 해소.**
  **1번만 고치고 2번을 놓쳤다면 이 조인 테스트는 여전히 통과처럼 보였을 것이다** — `promoteId` 가
  쓰는 필드들이 레벨 표기와 별개였기 때문. 총괄자가 회차 시작 시점에 2번을 먼저 짚어줘서
  같은 회차 안에서 분리·확인할 수 있었다.
- 담당 A(원인 1) · C(원인 2), 커밋: `a0a5eb2`, `61c4eaf`

### VF-005 · T0 `confidence.level` 상한 미적용 (C-1)
- 재현: `backend/.venv/Scripts/python.exe verification/fixtures/vf_t0_api.py`
- 결과: `/regions`·`/scores` 모두 `above ceiling (=='high')` **0건** (1회차 2건).
  `['medium','medium','medium','medium','low']` — 상한 `medium` 정확히 적용됨.
- 담당 C, 커밋: `a8f1e34`

### VF-006 · 서명 URL + `Cache-Control: public` 공존 (C-5)
- 재현: `PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_52b_basemap.py`
- 결과: `level=adm_dong`(서명 필요) → `Cache-Control: private, max-age=3600`.
  서명 없는 `level=sido` 만 `public` 유지 — 의도대로 분기됨.
- 담당 C, 커밋: `a8f1e34`

### VF-007 · `tenant_scoped` 키 하드코딩 (B-2)
- 재현: `cd intelligence && python -m unittest tests.test_synthetic_generator.GeneratedDatasetTestCase.test_no_tenant_scoped_features_leaked_into_the_shared_store -v`
- 결과: `OK`. 테스트가 `contracts.load_tenant_scoped_feature_keys()` 로 계약 파일에서
  직접 키를 읽는다 (`intelligence/tests/test_synthetic_generator.py:38-40`) — 하드코딩 제거 확인.
- 담당 B, 커밋: `4436bde`

### VF-008 · 백엔드 T0 run 테스트 부재 (C-2)
- 재현: `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`
- 결과: **28 passed** (1회차 19). `backend/tests/test_predictions_t0.py` 신설, T0 분기가
  이제 스위트에서 실제로 실행된다.
- 담당 C, 커밋: `a8f1e34`

### VF-009 · console 실행 가능 테스트 0개 (D-2)
- 재현: `cd console && node --test tests/join.test.mjs`
- 결과: **3 passed / 0 failed.** 파서→setFeatureState 키→조인→fill expression 전 구간을
  D 자신의 실제 코드(`scoreScale.ts`)와 A 의 실제 커밋된 픽스처로 실행.
- 담당 D, 커밋: `1b4296e`, `d942dd4`

### VF-011 · `backend/samples/manifest.json` 이 `scores.json` 과 레벨·빈티지가 어긋남 (신규 → 해소, C)
- 발견 경위: 총괄자가 2회차 착수 지시에서 직접 지목. 검증자가 재현·확인만 수행.
- 위치: `backend/samples/manifest.json` (해소 전: `level:"adm_dong"`, `boundary_vintage:"2026-01-01"`,
  `tile_url` 이 존재하지 않는 CDN 서명 URL) vs `backend/samples/scores.json`
  (`region_level:"sigungu"`, `boundary_vintage:"fixture"`, D-15 로 이미 정정됨).
- 재현: `python tools/validate_contracts.py --check-manifest backend/samples/manifest.json` +
  `--check-scores backend/samples/scores.json` 를 나란히 놓고 `level`/`boundary_vintage` 대조.
- 결과: 해소 전 상태에서 두 파일의 `level`·`boundary_vintage` 가 서로 다름 확인.
  VF-003 과 같은 실패 모양(조인은 구조적으로 성립하는데 조용히 안 맞음)이었으나,
  이번 조인 하네스가 쓰는 필드(`source_layer`/`feature_id_property`)가 레벨 무관값이라
  **`vf_56_join.mjs` 자체는 이 결함을 못 잡았다** — 별도로 직접 대조해야 잡히는 종류였다.
- 해소: `61c4eaf` — `level:"sigungu"`, `boundary_vintage:"fixture"`,
  `tile_url:"http://localhost:8000/artifacts/regions-sigungu-fixture.pmtiles"`,
  `minzoom:4` 로 A 의 실제 `manifest-fixture.json` 값을 그대로 복사. 재검증:
  `--check-manifest`·`--check-scores` 둘 다 **오류 0 + 경고 0.**
- 근거: `ADR-002-artifact-publishing.md`, `DECISIONS.md` D-15
- 담당: **C**

---

## S2 — 심각 (2회차, 여전히 열림)

### VF-004 · C 가 광고하는 빈티지·줌이 A 의 실제 산출물과 다르다 (C) — ~~여전히 열림~~
> **3회차에서 정정됨 — 위 "정정: 2회차 VF-004 판정이 관측 시점 오류였다" 참조.**
> C-7(`a760b31`)은 사실 이 2회차 커밋(`0497f4f`)보다 먼저 마스터에 있었다. 아래는
> 관측 시점(커밋 직전 재확인 누락)의 기록으로 남겨둔다 — 삭제하지 않는다.
- 재현: `PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py`
- 결과 (1회차와 동일한 모양):
  ```
  A 가 실제 발행: sido vintages=['2026-01-01','2026-07-01'] latest=2026-07-01
  C 가 광고:      sido vintages=['2026-01-01','2025-01-01'] latest=2026-01-01
  C.get(level=sido, vintage=2026-07-01) -> 404 BOUNDARY_VINTAGE_NOT_FOUND   (실재하는데 없다고 답함)
  zoom, sido: A manifest minzoom=0 / C response minzoom=5
  ```
- **DISPATCH C-7 (하드코딩 3종 제거, A 매니페스트 값 전달)이 아직 커밋되지 않았다.**
  `backend/app/services/basemap_registry.py` 에 해당 리라이트가 **워킹트리에만 존재**
  (미커밋 — 이번 회차 판정 대상 아님, §CHARTER 절차상 커밋된 것만 판정한다).
  코드가 커밋되는 대로 다음 회차에 바로 재확인 가능하다.
- 근거: `ADR-002-artifact-publishing.md`, `DECISIONS.md` D-08·D-13·D-14
- 담당: **C** (진행 중으로 관측됨, 미완료)
- 나이: 1회차부터 — **1일**

---

## S4 — 낮음

### VF-010 · `suppressed` 원시값 차단이 생성기 단계에만 있다 (C, B) — 변경 없음
- 1회차와 동일. DISPATCH 1차 범위에 포함되지 않았다. API 응답·로그·내보내기 경로에
  suppressed 처리 자체가 아직 없음 (내보내기 라우트 미구현, 아래 확인 불가 참조).
- 근거: `05_scoring_spec.md` §8, `06_governance.md` §2.3
- 담당: **C, B**
- 나이: 1회차부터 — **1일**

### VF-012 · 백테스트 하네스에 wMAPE·예측구간 coverage 가 없다 (B) — 신규, 문서화된 결함
- 위치: `intelligence/backtest/harness.py` (B-4, 커밋 `775be91`)
- 내용: `05_scoring_spec.md` §5.2 는 Spearman ρ·wMAPE·예측구간 coverage 세 지표를 요구한다.
  이번 하네스는 **Spearman ρ 와 top-decile lift 만** 구현됐다 (`time_split`,
  `region_holdout_split`, `assert_no_leakage_before_cutoff` 는 구현·검증됨 — 아래 참고).
  wMAPE·coverage 는 p10/p50/p90 구간 추정치가 필요한데, 그건 모델의 Step 5(잔차 분포) 범위라고
  커밋 메시지가 스스로 밝히고 있다. **거짓 완료가 아니라 정직하게 선언된 미구현**이라 S4 로 낮춘다.
- 참고로 `assert_no_leakage_before_cutoff` 는 문서상 주장이 아니라 실제로 이가 있다 — 커밋
  메시지에 따르면 `as_of` 를 무시하는 스토어로 몽키패치해 실제로 `LeakageDetectedError` 가
  발생하는 것까지 증명했다고 적혀 있다(검증자가 직접 재실행은 하지 않음, 다음 회차 대상).
- 근거: `05_scoring_spec.md` §5.2
- 담당: **B**

---

## 확인 불가 (갱신)

- **RLS 가 DB 레벨에 걸렸는가** — 여전히 확인 불가. DB 자체가 없다 (`prediction_store.py` 인메모리,
  변경 없음).
- **내보내기(xlsx/csv)에 T0 금액·suppressed 원시값이 새는가** — 여전히 확인 불가.
  `backend/app/routers/` 에 export 라우트 0건 (변경 없음). VF-010 이 열려 있는 이유이기도 하다.

### 이번 회차에 확인 완료돼 목록에서 빠진 항목

- **개발 전용 토큰 엔드포인트가 운영에 노출되는가 (D-17 S1 조건)** — **확인 완료, 문제 없음.**
  `backend/app/routers/dev_auth.py` 신설(C-6, `a8f1e34`). `app/main.py:23-26` 가
  `settings.env == "development"` 일 때만 라우터를 등록한다. 직접 재현:
  ```
  SELLFINDER_ENV=production 로 create_app() 실행 후
  POST /v1/dev/token -> 404, '/v1/dev/token' in [r.path for r in app.routes] -> False
  ```
  핸들러가 조건부로 막는 게 아니라 **라우트 자체가 프로덕션 빌드에 존재하지 않는다** — D-17 이
  요구한 것과 일치.

---


## 회차: 1회차 · 2026-08-15 · HEAD `8133702`

검증 범위: A~D 전 폴더 (첫 회차라 미해결 항목이 없다).
A~D 의 마지막 커밋은 모두 08-15 18:01 이전이므로, 계약 `33fe4ac`(19:37) 과
ADR-002/003/004 는 아직 어느 폴더에도 반영돼 있지 않다. **아래 findings 는
ADR 반영 이전 상태에 대한 것이며, 일부는 이미 결정(D-nn)이 나 있고 이행만 남았다.**
그런 항목은 각 finding 에 해당 결정 번호를 적었다 — 재논의 대상이 아니라 이행 확인 대상이다.

실행 환경: 각 폴더의 자체 venv / node_modules. 픽스처는 `verification/fixtures/` 에 있고
전부 이번 회차에 직접 실행했다. 아래 "결과"는 전부 실제 출력이다.

## 요약

| S1 치명 | S2 심각 | S3 보통 | S4 낮음 | 해결됨 | 확인 불가 |
|---|---|---|---|---|---|
| 0 | 5 | 3 | 2 | 0 | 4 |

담당별: **C 6건** (VF-002·004·005·006·008·010) · **B 2건** (VF-001·007) ·
**D 1건** (VF-009) · **A·C·D 공동 1건** (VF-003, jin 결정 필요)

---

## S1 — 즉시 조치

(없음)

> 참고: `POST /v1/dev/token` (D-17 의 S1 조건) 은 아직 구현 자체가 없다. 아래 "확인 불가" 참조.

---

## S2 — 심각

### VF-001 · 요인 분해 불변식이 항등식으로만 검사돼 강제력이 없다 (B)

- 위치: `intelligence/tests/test_factor_model.py:49`
  (`test_log_contribution_sum_matches_log_of_total_multiplier`)
- 문제: `total_multiplier` 가 `log_contribution` 들로부터 계산되므로 이 단언은 **항상 참**이다.
  분해가 거짓이 돼도 테스트는 통과한다. D-04 가 막으려던 것("설명이 거짓이 되는 것")을 못 막는다.
- 재현 (런타임 변이 주입. 에이전트 파일은 수정하지 않는다):

  ```
  python verification/fixtures/vf_51_mutation.py M1   # log_contribution 을 소수 2자리로 반올림
  python verification/fixtures/vf_51_mutation.py M2   # price_acceptance 기여도만 x0.5
  python verification/fixtures/vf_51_mutation.py M3   # 마지막 요인을 출력에서 제거
  ```

- 결과:

  ```
  [M1] ran=12 failures=0 errors=0   *** MUTANT SURVIVED ***
  [M2] ran=12 failures=0 errors=0   *** MUTANT SURVIVED ***
  [M3] ran=12 failures=1 errors=1   CAUGHT BY: test_exactly_eight_factor_keys_in_contract_order
  ```

  분해를 **거짓으로 만드는** 두 변이(M1·M2)가 B 의 12개 테스트를 전부 통과한다.
  요인 개수를 바꾸는 M3 만 잡힌다.
- 모델 자체는 정상이다 (오해 방지):

  ```
  python verification/fixtures/vf_51_factor_sum.py
  → predictions checked: 2863 / worst |sum - ln(total_multiplier)| = 1.110e-16 / violations: 0
  ```

  **깨진 것은 코드가 아니라 안전망이다.**
- 닫는 방법 (이미 증명됨): 합이 아닌 **외부 증인**과 대조하면 M2 가 잡힌다.

  ```
  python verification/fixtures/vf_51_independent_catch.py M2
  → tautological check: pass  /  independent check: worst dev = 3.674e-01 -> FAIL
  ```

  `display_effect` 처럼 실제 배수에서 파생된 값, 또는 `value/benchmark` 비율과 대조하는
  단언을 추가하면 된다.
- 근거: `05_scoring_spec.md` §1·§8-1, `DECISIONS.md` D-04
- 담당: **B**

### VF-002 · `tenant_id` 주입이 400 이 아니라 조용히 무시된다 (C)

- 위치: `backend/app/security.py:14` (`get_tenant_id` 가 헤더만 읽고 다른 경로를 거부하지 않는다).
  라우터 어디에도 주입 거부가 없다 — `app/routers/predictions.py:40`, `:101`, `app/routers/basemap.py:11`
- 재현:

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_52_tenant.py
  ```

- 결과 (계약은 전부 `400 TENANT_ID_NOT_ALLOWED` 를 요구):

  ```
  A + ?tenant_id=tnt_other    /regions -> 200
  A + ?tenant_id=tnt_demo     /regions -> 200
  A + ?tenant_id=tnt_other    /scores  -> 200
  A + ?tenantId=tnt_other     /scores  -> 200
  A + X-Tenant-Id: tnt_other  /regions -> 200
  A + Tenant-Id:   tnt_other  /scores  -> 200
  ```

- **지금 데이터가 새지는 않는다**: 교차 테넌트 조회는 `404 PREDICTION_RUN_NOT_FOUND` 로 막힌다
  (`prediction_store.py:99`). 그래서 S1 이 아니라 S2 다.
  위험은 "무시"가 코드에 남아 있다는 것 자체다 — 언젠가 누가 그 값을 읽는다.
  `security.py` 독스트링은 *"tenant_id 는 어디서도 쿼리/바디로 읽지 않는다"* 라고 적고 있는데,
  계약이 요구하는 것은 **읽지 않는 것이 아니라 거부하는 것**이다.
- 근거: `06_governance.md` §1.1, `ADR-003-auth.md`, `DECISIONS.md` D-17 ("조용히 무시 금지")
- 담당: **C**

### VF-003 · 경계 타일 ↔ 점수 조인 키가 실제로 안 맞는다 — 지도가 통째로 회색 (A·C·D, jin 결정 필요)

- 위치:
  - A: `data-platform/src/boundary_tiles/tiler.py:56-63` — `region_id` 를 properties 에서 **제거**하고
    숫자 feature id 로만 싣는다 (`feature_id.py` 의 변환, 역매핑은 `*.id_map.json`)
  - A 매니페스트: `data-platform/output/tiles/manifest.json` — 그런데 `feature_id_property: "region_id"`
    라고 적혀 있다 (**자기 산출물과 모순**)
  - C: `backend/app/services/basemap_registry.py:29` — `FEATURE_ID_PROPERTY = "region_id"`
  - D: `console/src/components/PredictionMap.tsx:105` — `promoteId: { [source_layer]: feature_id_property }`
- 재현 (A 의 실제 `.pmtiles` + C 의 실제 샘플 + D 의 실제 조인 로직. MapLibre 의 `getId()` 와
  `String(featureId)` 강제 변환을 원본에서 그대로 옮겨 썼다):

  ```
  data-platform/.venv/Scripts/python.exe verification/fixtures/vf_56_dump_features.py
  node verification/fixtures/vf_56_join.mjs
  ```

- 결과:

  ```
  manifest.feature_id_property = "region_id"
  tile feature ids (A, real)   = 11, 26, 28, 41, 50
  tile feature properties keys = ["name","level","is_synthetic_placeholder"]   ← region_id 가 없다
  features whose promoted id is undefined : 5/5
  features that received a score          : 0/5
  RESULT: every region paints NO_DATA grey. No error thrown, no console warning - silent blank map.
  ```

  `promoteId` 를 빼고 네이티브 MVT id 로 붙여보는 반사실 검사도 **0/5** 다 —
  C 의 점수는 `region_level="adm_dong"` 인데 5자리 시군구 코드(41135…)를 담고 있고,
  A 는 시도(11, 26…)만 발행하기 때문이다 (이쪽은 VF-004·D-15).
- **에러도 경고도 없다.** 세 폴더의 테스트와 `validate_contracts.py` 가 전부 통과하는 상태에서
  화면만 조용히 비어 있다. 헌장 §1 의 "통합 불일치" 유형 그대로다.
- **jin 결정이 필요한 지점**: A 는 브리프 지시("region_id 를 속성이 아니라 feature id 로 실어라",
  `feature_id.py` 독스트링)를 따랐고, D 는 계약(`feature_id_property`)을 따랐다. **둘 다 자기 문서를
  지켰는데 안 맞는다.** 계약이 두 방식을 동시에 말하고 있는 것이 원인이다. 선택지는 둘 중 하나다:
  1. A 가 `region_id` 를 properties 에도 싣는다 (계약 문구 유지, 타일 크기 소폭 증가)
  2. 계약이 "네이티브 feature id 사용"을 명시하고 `feature_id_property` 를 null 로 두는 규약을 만든다
     (D 는 `promoteId` 를 쓰지 않고 숫자 id 를 문자열로 비교. `id_map.json` 의 위치도 계약에 올려야 한다)

  A 의 매니페스트가 이미 `id_map_path` 를 내보내고 있다는 사실은 2번 쪽 설계가 실재한다는 뜻이다.
- 근거: `04_api_contract.yaml` v0.2.1 (`feature_id_property`), `ADR-001-map-tiles.md`, `DECISIONS.md` D-05
- 담당: **jin(결정) → A·C·D(이행)**

### VF-004 · C 가 광고하는 빈티지·줌이 A 의 실제 산출물과 다르다 (C)

- 위치: `backend/app/services/basemap_registry.py:32` (`_ZOOM_BY_LEVEL`), `:64-68` (`_VINTAGES` 하드코딩)
- 재현:

  ```
  PYTHONIOENCODING=utf-8 backend/.venv/Scripts/python.exe verification/fixtures/vf_56_vintage.py
  ```

- 결과:

  ```
  A 가 실제 발행:  sido  vintages=['2026-01-01','2026-07-01']  latest=2026-07-01
  C 가 광고:       sido  vintages=['2026-01-01','2025-01-01']  latest=2026-01-01
                   sigungu / adm_dong 도 광고하지만 A 는 아직 만들지 않았다

  C.get(level=sido, vintage=2026-07-01) -> 404 BOUNDARY_VINTAGE_NOT_FOUND   ← 실재하는데 없다고 답한다
  C 가 광고한 sido/2025-01-01 -> A 에 있는가? False                          ← 없는데 있다고 답한다

  zoom, sido:  A manifest minzoom=0 maxzoom=8  /  C response minzoom=5 maxzoom=8
  ```

- 양방향으로 틀렸다. 존재하는 빈티지를 404 로 막고, 없는 빈티지를 목록에 넣는다.
  줌은 D-14(sido minzoom=0)와도 다르다.
- **이미 결정돼 있다**: D-13(C 는 A 의 매니페스트를 읽는다, 없으면 빈 배열이 아니라 503),
  D-14(레벨별 줌은 A 매니페스트가 정하고 C 는 그대로 전달). 재논의 대상이 아니라 **미이행**이다.
  이 finding 은 이행 여부를 다음 회차에 확인하기 위한 것이다.
- 근거: `ADR-002-artifact-publishing.md`, `DECISIONS.md` D-08·D-13·D-14
- 담당: **C**

### VF-005 · T0 인데 `confidence.level = "high"` 가 반환된다 (C)

- 위치: `backend/app/routers/predictions.py:89` (`/regions`), `:129` (`/scores`) —
  저장된 `confidence_level` 을 그대로 내보내며 T0 상한을 적용하지 않는다.
  금액(`expected_revenue_krw`)은 같은 함수 `:82-88` 에서 T0 분기로 제대로 막고 있다. **한 겹만 있다.**
- 재현 (백엔드에 T0 run 을 만드는 테스트가 하나도 없어 검증자가 직접 만들었다 — VF-008):

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_t0_api.py
  ```

- 결과:

  ```
  GET /regions (T0) -> 200, 5 rows
    rows with non-null expected_revenue_krw : 0        ← 금액은 정상
    /regions (T0) confidence levels : ['high','high','medium','medium','low']
    above ceiling (=='high')        : 2               ← 계약: 0 이어야 한다
    /scores  (T0) confidence levels : ['high','high','medium','medium','low']
    above ceiling (=='high')        : 2
  ```

- 자사 판매 데이터가 없는 테넌트에게 "높은 신뢰도"라고 말하는 것은 D-03 이 막으려던 것과 같은 종류의
  거짓이다. 금액만 막고 신뢰도를 안 막으면 절반만 지킨 것이다.
- 근거: `05_scoring_spec.md` §2 ("T0 는 `confidence.level` 상한이 medium"), `DECISIONS.md` D-03
- 담당: **C**

---

## S3 — 보통

### VF-006 · 인증이 필요한 응답에 `Cache-Control: public` + 서명 URL 이 함께 나간다 (C)

- 위치: `backend/app/routers/basemap.py:31`
- 재현:

  ```
  backend/.venv/Scripts/python.exe verification/fixtures/vf_52b_basemap.py
  ```

- 결과:

  ```
  level=adm_dong  auth=yes -> 200  Cache-Control=public, max-age=3600  signed=True
      tile_url = https://cdn.sellfinder.kr/tiles/regions-adm_dong-2026-01-01.pmtiles?expires=…&sig=…
  level=adm_dong  auth=NO  -> 401
  ```

  `Authorization` 헤더가 있어야만 얻을 수 있는 **서명 URL** 이 공용 캐시 가능으로 표시된다.
  중간 프록시/CDN 이 이 응답을 캐시하면 토큰 없는 요청자에게 서명 URL 이 도달할 수 있다.
- 지금은 응답 본문이 테넌트별로 다르지 않아 유출 영향이 제한적이다. 그래서 S3 다.
  **매니페스트가 테넌트별로 갈라지는 순간 S1 로 승격된다** (D-17: 캐시 키에 `tenant_id` 포함).
  라우터 독스트링(`basemap.py:20-22`)은 *"tenant-independent 라서 캐시 가능"* 이라고 적고 있으나,
  서명 URL 은 테넌트 독립이어도 공개 대상이 아니다.
- 근거: `06_governance.md` §1.5, `ADR-003-auth.md`, `DECISIONS.md` D-17
- 담당: **C**

### VF-008 · 백엔드에 T0 run 을 만드는 테스트가 없어 T0 분기 전체가 한 번도 실행되지 않는다 (C)

- 위치: `backend/app/services/prediction_store.py:106` — 시드는 `run_demo01`(T1) **하나뿐**이다.
  `backend/tests/*` 어디에도 `data_tier="T0"` 인 run 이 없다.
- 결과: `routers/predictions.py:82-88` 의 T0 금액 차단 분기를 19개 테스트 중 **어느 것도 실행하지 않는다**.
  검증자가 직접 T0 run 을 만들어 실행한 결과 금액 차단은 정상 동작했으나(위 VF-005 출력),
  **회귀를 막는 것이 아무것도 없다.** 실제로 같은 공백 때문에 VF-005(신뢰도 상한)가 잡히지 않았다.
- 재현: `verification/fixtures/vf_t0_api.py` 가 하는 일이 곧 빠져 있는 테스트다.
- 근거: `05_scoring_spec.md` §2·§8-2, `DECISIONS.md` D-03
- 담당: **C**

### VF-009 · console 에 실행 가능한 테스트가 0개다 (D)

- 위치: `console/package.json` — 테스트 러너·테스트 파일 없음. `tsc --noEmit`(exit 0) 만 있다.
- 결과: 추적 매트릭스의 D 관련 조항이 **전부 구멍**이다 —
  조인 키 일치, `score_range` 로 색상 스케일 고정, `confidence='low'` 의 패턴 구분,
  T0 금액 자리 표기, T0 UI 문구. 코드를 읽으면 맞게 구현돼 있으나(예: `scoreScale.ts` 가
  `score_range` 를 받고 `PredictionMap.tsx:118` 이 전달), 누가 되돌려도 아무도 모른다.
  VF-003 이 세 폴더 모두 초록불인 채로 살아남은 것도 이 구멍 안에서다.
- 최소 제안 (검증자는 코드를 쓰지 않는다 — 어디가 비었는지만 적는다):
  `backend/samples/*.json` 을 입력으로 (1) 파서 → (2) `setFeatureState` 키 생성 →
  (3) fill expression 까지 가는 노드 단위 테스트 하나. `vf_56_join.mjs` 가 그 형태의 참고 구현이다.
- 근거: `verification/CHARTER.md` §5.6·§5.7, `05_scoring_spec.md` §2
- 담당: **D**

---

## S4 — 낮음

### VF-007 · `tenant_scoped` 키 목록이 테스트에 하드코딩돼 있다 (B)

- 위치: `intelligence/tests/test_synthetic_generator.py:38`
  (`{"own_store_count_2km", "own_distribution_points", "own_share_of_category"}`)
- 문제: 계약(`03_region_features.json` 의 `feature_registry.tenant_scoped`)에서 읽지 않고 복사했다.
  현재는 세 키가 일치하지만(검증자 대조 확인), 계약에 네 번째 키가 추가되면 테스트는 통과한 채
  그 키가 공용 피처스토어로 새 나간다. 헌장이 "가장 흔한 실수"로 지목한 지점이다.
- 재현: `03_region_features.json` 의 `tenant_scoped` 에 키를 하나 추가해도
  `python -m unittest discover -s tests` 는 28 passed 그대로다.
- 근거: `06_governance.md` §1.3, `03_region_features.json`
- 담당: **B**

### VF-010 · `suppressed` 원시값 차단이 생성기 단계에만 있다 (C, B)

- 위치: 차단은 `intelligence/tests/test_synthetic_generator.py:144` 가 생성기 출력에 대해서만 검사한다.
  `backend/app` 전체에 `suppressed` 문자열이 **한 번도 등장하지 않는다** (grep 0건).
- 문제: API 응답·로그·에러 메시지·내보내기 경로에 대한 방어가 없다. 지금은 내보내기 기능 자체가
  없어 실제 유출 경로가 없으므로 S4 다. **내보내기(xlsx/csv)나 상세 조회가 붙는 순간 S1 후보로 승격된다.**
- 근거: `06_governance.md` §2.3, `05_scoring_spec.md` §8-6
- 담당: **C** (B 는 `coverage_flag` 를 응답까지 전달하는 경로를 정의)

---

## 추정 (미확정)

> 확정 findings 와 절대 섞지 말 것. 확인 방법을 반드시 적는다.

(없음 — 이번 회차 항목은 전부 실행으로 확정했다.)

---

## 해결 확인됨

(첫 회차 — 없음)

참고로 아래 두 가지는 **결함이 아님을 실행으로 확인**했다. 다음 회차에 다시 올리지 말 것.

- **요인 로그 합 불변식 자체**: 2,863건 예측에서 최대 편차 `1.11e-16` (한계 1e-6). 모델은 정상이다.
  문제는 테스트의 강제력이고 그것이 VF-001 이다.
- **API 재현성**: `/scores`·`/regions`·`/basemap` 을 5회씩 호출해 본문 sha256 이 전부 동일했다
  (`vf_repro_api.py`). 서명 URL 이 있는 basemap 도 TTL 창 안에서는 동일하다.

---

## 확인 불가

> "아마 괜찮을 것"은 쓰지 않는다. 무엇을 왜 확인할 수 없었는지만 적는다.

- **RLS 가 DB 레벨에 걸렸는가** (`06_governance.md` §1.2) — DB 가 없다.
  `prediction_store.py` 는 인메모리 dict 다. DB 도입 전까지 확인 불가.
- **개발 전용 토큰 엔드포인트가 운영에 노출되는가** (D-17 의 S1 조건) —
  `POST /v1/dev/token` 도 `SELLFINDER_ENV` 분기도 아직 없다 (grep 0건). ADR-003 구현 후 첫 확인 대상.
- **내보내기(xlsx/csv)에 T0 금액·suppressed 원시값이 새는가** (CHARTER §5.1·§5.4) —
  내보내기 경로가 구현되지 않았다 (`backend/app` 에 export/csv/xlsx 라우트 0건).
- **학습 데이터 누수 / 백테스트 시간 분할** (`05_scoring_spec.md` §5.1) —
  B 가 Step 3 범위로 명시 선언했고 backtest 모듈이 없다. 누수 **함정 피처**가 생성기에 심겨 있고
  그 존재는 `test_synthetic_generator.py:74,84,87` 로 검증되지만, **그것을 잡아내는 하네스**가 없다.
