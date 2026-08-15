# BRIEF-B — intelligence (에이전트 B)

생성: 총괄자 · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:1x, HEAD `849354d`)
읽는 순서: 이 파일 → `orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md`

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `ab92558` 08-15 18:00 — *Step 2 invariant tests + 8-factor model skeleton* |
| 폴더 커밋 수 | 3 |
| 테스트 | `python -m unittest` **28 passed** (Σlog 불변식 테스트 포함) |
| 계약 반영 | 계약 최종 커밋 `af25b37`(17:01) **이후**에 커밋함 — OK |
| CONTRACT_CHANGE_REQUEST | 없음 |

검증한 것 (네 주장이 아니라 총괄자가 직접 실행한 결과):
- `intelligence/tests/test_factor_model.py` 에
  `test_log_contribution_sum_matches_log_of_total_multiplier` 가 `delta=1e-6` 로 존재하고 **통과한다.**
  `DECISIONS.md` D-04 불변식이 실제로 강제되고 있다.
- 8개 factor key 고정, competition ≤ 1, 온라인 채널의 유동인구 배제, T0 금액 null —
  각각 테스트가 있고 통과한다.
- **3단계(백테스트 하네스)는 시작되지 않았다.** `intelligence/` 아래에 backtest 모듈도
  모델 카드 산출물도 없다. 네 보고서와 저장소가 일치한다.

**불일치 1건:** `intelligence/RECONCILIATION.md` 는 *"지금까지 계획 수립만 했고 코드는 작성하지
않았다"* 로 끝난다. 그 뒤 커밋 2건(`8f00729`, `ab92558`)에서 실제로 코드를 썼다. **보고서가 낡았다.**

---

## 해소된 것 — 더 신경 쓰지 마라

1. **3단계 진입은 승인되었다.** 백테스트 하네스로 진행해라. 아래 "다음 작업" 1번.

2. **`/backend` ↔ `/intelligence` 내부 호출 계약 (네 §6-3 질문) — C 가 같은 질문을 하며 제안을 냈다.**
   C 의 `backend/RECONCILIATION.md` §6: *"비동기 잡 인프라를 `/backend` 가 소유하므로, 잡 워커가
   B 의 예측 함수를 (초기엔 in-process, 이후 필요시 내부 API 로) 호출하는 방식"* 을 제안하고,
   **B 가 구현을 시작하는 시점에 인터페이스를 확정하고 싶다**고 적었다.
   → 너와 C 의 입장이 이미 같다. 새 질문으로 다시 올리지 말고, `predict_batch` 계열 진입점의
   시그니처를 네 README 에 고정해 공개해라. C 가 그걸 호출한다.

3. **네 합성 픽스처는 이미 다른 에이전트가 쓸 수 있는 상태다.**
   `intelligence/synthetic/sample/*` 8개 파일이 커밋되어 있다(`8f00729`). 총괄자가 확인한 결과
   `regions.json` 은 `03_region_features.json` 의 코드 자릿수 규칙을 지키는 **저장소 내 유일한**
   지역 픽스처다(sido 2자리 `91` / sigungu 5자리 `91001` / adm_dong 8자리 `91001001`,
   실제 행정코드와 충돌하지 않는 가상 접두사). A 와 D 에게 이걸 쓰라고 안내가 나갈 예정이다.

---

## 다음 작업 (우선순위 순)

1. **3단계 — 백테스트 하네스 (`05_scoring_spec.md` §5). 승인됨, 지금 시작해라.**
   네 보고서 §5-10 에 적은 대로:
   - 시간 분할 + 지역 홀드아웃, `as_of` 는 타깃 기간 시작일로 고정
     (`03_region_features.json` 의 `point_in_time_rule` — 미래 피처 누수 금지)
   - Spearman ρ 1순위, wMAPE (MAPE 단독 금지), 예측구간 coverage
   - 합성 데이터의 심어둔 관계를 실제로 되찾는지 확인 (`ground_truth.json` 활용)
   지금 이걸 할 수 있는 이유: A 의 실데이터가 없어도 네 합성 생성기 + ground truth 로 완결된다.
   **A 를 기다리지 마라.**

2. **모델 카드 (`05_scoring_spec.md` §5).**
   `known_limitations` / `do_not_use_for` 필수. 합성 데이터로만 검증했다는 사실을
   카드에 명시해라 — 나중에 실데이터로 바뀔 때 이 문장이 안전장치가 된다.

3. **피처 스토어 스텁의 교체 지점을 고정해라.**
   네 §6-1 질문(호출 방식)에 A 가 아직 답하지 않았다. 총괄자가 A 에게 전달했다.
   그동안은 지금 스텁을 유지하되, `get_features(region_ids, feature_keys, as_of)` 시그니처를
   README 에 계약처럼 박아둬라. A 가 같은 모양으로 내면 코드 변경이 0 이 된다.

4. **`suppressed` 셀 처리 (§6-2) — 이중 처리 위험이 남아 있다.**
   너는 "B 가 모델 입력 단계에서 처리"로 가정 중이다. A 가 이미 대체해서 주면 두 번 처리된다.
   A 에게 질문이 전달됐다. **답이 오기 전까지는 네 가정대로 진행하되, 그 가정을 코드 주석과
   모델 카드에 적어라.** 나중에 A 의 답이 다르면 한 곳만 고치면 되게.

5. **SKU 자동 분류기 (`02_taxonomy.json` `classification_contract`).**
   C 가 `POST /products:classify` 를 mock 으로 먼저 만들 계획이다(C 보고서 §5-3).
   네 실구현이 나오면 C 가 교체한다 — 실제 `node_id` 만 반환하도록 강제하는 검증을 잊지 마라.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# 테스트 (현재 기준선: 28 passed). 이 폴더엔 .venv 도 pytest 도 없다 — unittest 로 돌아간다.
cd intelligence && python -m unittest discover -s tests -t . -q

# 폴더 경계 위반 검사 (통과 = exit 0)
python tools/validate_contracts.py --base origin/master --agent B

# 네 예측 응답이 계약을 지키는지 (요인 합·T0 금액·competition 부호까지 검사)
python tools/validate_contracts.py --check-response <응답.json>
```

`--check-response` 통과 기준: 8개 factor key 외 사용 없음, 각 factor 에 evidence 존재,
`Σ log_contribution == total_log_multiplier` (오차 1e-6), T0 이면 `expected_revenue_krw` 가 null,
온라인 채널 응답의 evidence 에 유동인구 근거 없음.

> 참고: 이 폴더에 `.venv` 가 없어서 pytest 가 없다. 테스트를 unittest 로 유지하면
> 총괄자와 CI 가 별도 환경 구축 없이 계속 돌릴 수 있다. pytest 로 옮기고 싶으면
> `intelligence/.gitignore` 와 requirements 를 함께 정리해라.

---

## 하지 말 것

- **8개 `factor_key` 를 추가·개명·재정의하지 마라.** 고정이다. (`DECISIONS.md` D-04)
- **Σ 로그 기여도 불변식을 완화하지 마라.** 깨지면 화면의 요인 분해가 거짓이 된다.
- **T0 에 금액을 채우지 마라.** (`DECISIONS.md` D-03)
- **"최신값" 피처 헬퍼를 만들지 마라.** `point_in_time_rule` 위반이고 백테스트가 조용히 낙관 편향된다.
- **A 의 실데이터를 기다리며 멈추지 마라.** 3단계는 합성 데이터만으로 완결된다.
- **`/data-platform`, `/backend`, `/console`, `shared/contracts/` 를 수정하지 마라.**
