# BRIEF-B — intelligence (에이전트 B)

**개정 2** · 근거: `orchestrator/STATUS.md` (스윕 08-15 19:5x, HEAD `33fe4ac`)
읽는 순서: 이 파일 → **`shared/contracts/ADR-004-taxonomy-mapping.md`** →
`orchestrator/DECISIONS.md` → 네 `RECONCILIATION.md`

> **ADR-004 는 반드시 직접 읽어라.** `shared/contracts/README.md` 의 읽기 순서 표는 `00`~`06` 만
> 나열하고 ADR 을 포함하지 않는다. 표만 보고 넘어가면 네 모델 전제가 바뀐 걸 놓친다.

---

## 지금 상태 (저장소 기준)

| 항목 | 사실 |
|---|---|
| 마지막 커밋 | `ab92558` 08-15 18:00 — *Step 2 invariant tests + 8-factor model skeleton* |
| 폴더 커밋 수 | 3 · 테스트 **28 passed** (`python -m unittest`) |
| 계약 반영 | **경고 — 계약 최종 커밋 `33fe4ac`(19:37)보다 1.6h 이르다.** ADR-004 미반영 |
| CONTRACT_CHANGE_REQUEST | 없음 |

총괄자가 직접 실행해 확인한 것 (네 보고가 아니라):
`test_log_contribution_sum_matches_log_of_total_multiplier` 가 `delta=1e-6` 로 통과한다.
8개 factor key 고정 / competition ≤ 1 / 온라인 채널 유동인구 배제 / T0 금액 null 모두 테스트가 있고 통과.
**3단계(백테스트 하네스)는 실제로 미착수** — backtest 모듈도 모델 카드도 없다. 네 보고와 일치한다.

**보고서 불일치 (아직 미갱신):** `intelligence/RECONCILIATION.md` 는
*"계획 수립만 했고 코드는 작성하지 않았다"* 로 끝나지만 그 뒤 커밋 2건에서 코드를 썼다.

---

## 해소된 것 — 더 신경 쓰지 마라

1. **3단계 진입은 승인되었다.** 아래 1번으로 진행해라.

2. **`/backend` ↔ `/intelligence` 내부 호출 (네 §6-3) — C 와 입장이 이미 같다.**
   C 는 *"잡 워커가 B 의 예측 함수를 초기엔 in-process 로 호출, B 착수 시점에 확정"* 을 제안했다.
   새 계약 질문으로 다시 올리지 말고, `predict_batch` 계열 진입점 시그니처를 README 에 고정해 공개해라.

3. **`price_tier` 산정 소유자 (네 §6-4)** — 택소노미 노드 배정과 결합되므로 네가 갖는 게 맞다.
   ADR-004 가 `sbiz` 를 1차 키로 확정하면서 노드 배정 경로가 하나로 정리됐다.

4. **`card_mcc` 라이선스 (네 §6-5) — 답이 나왔고, 네 모델 전제가 바뀐다.** 아래 2번. 중요하다.

5. **네 합성 픽스처는 이미 다른 에이전트가 쓸 수 있는 상태다.**
   `intelligence/synthetic/sample/regions.json` 은 저장소에서 코드 자릿수 규칙
   (`03_region_features.json`)을 지키는 유일한 지역 픽스처다. A·D 에게 안내가 나갔다.

---

## 다음 작업 (우선순위 순)

1. **3단계 — 백테스트 하네스 (`05_scoring_spec.md` §5). 승인됨, 지금 시작해라.**
   - 시간 분할 + 지역 홀드아웃, `as_of` 는 타깃 기간 시작일로 고정
     (`03_region_features.json` `point_in_time_rule` — 미래 피처 누수 금지)
   - Spearman ρ 1순위, wMAPE (MAPE 단독 금지), 예측구간 coverage
   - 합성 데이터에 심어둔 관계를 되찾는지 `ground_truth.json` 으로 확인
   A 의 실데이터를 기다리지 마라. 네 생성기만으로 완결된다.

2. **ADR-004 를 모델 전제에 반영해라 — 이건 3단계와 병행이 아니라 그 안에 들어간다.**
   `card_mcc` 가 라이선스 미확보로 파이프라인에서 빠졌다. 따라서:
   - **`demand_signal.spend_krw` 는 당분간 항상 null 이다.** 이 전제로
     `category_penetration` 을 다시 설계해라 — `store_count` 와 지역 소비력 프록시로
     `spend_index` 를 **유도**한다.
   - **합성 데이터 생성기에서 `spend_krw` 를 채워두지 마라.** 지금 채워두면 실데이터로 갈 때
     모델이 무너진다. 생성기가 실제 제약을 흉내내야 백테스트가 의미를 갖는다.
   - 택소노미 매핑이 없는 노드는 `confidence.level='low'` **강제 하향**이 실제로 동작하는지
     테스트로 강제해라 (`05_scoring_spec.md` §4, `DECISIONS.md` D-19). 0 으로 채우지 마라.

3. **모델 카드 (`05_scoring_spec.md` §5).**
   `known_limitations` / `do_not_use_for` 필수. **합성 데이터로만 검증했다는 사실**과
   **`spend_krw` 부재로 절대 금액 추정이 불가능하다는 점**을 명시해라.
   이 두 문장이 나중에 안전장치가 된다.

4. **피처 스토어 스텁 교체 지점 고정.** A 가 아직 §6-1 에 답하지 않았다(전달됨).
   `get_features(region_ids, feature_keys, as_of)` 시그니처를 README 에 계약처럼 박아둬라.

5. **`suppressed` 이중 처리 위험 (§6-2).** A 의 답이 오기 전까지 네 가정대로 진행하되,
   그 가정을 코드 주석과 모델 카드에 적어라. 답이 다르면 한 곳만 고치면 되게.

6. **SKU 자동 분류기.** C 가 `POST /products:classify` 를 mock 으로 먼저 만든다.
   네 실구현이 나오면 교체한다. `02_taxonomy.json` 에 실재하는 `node_id` 만 반환하도록 강제해라.

---

## 확인 방법 — 명령어와 통과 기준

```bash
# 테스트 (현재 기준선: 28 passed). 이 폴더엔 .venv 도 pytest 도 없다 — unittest 로 돌아간다.
cd intelligence && python -m unittest discover -s tests -t . -q

# 폴더 경계 위반 검사 (통과 = exit 0)
python tools/validate_contracts.py --base origin/master --agent B

# 예측 응답 검증
python tools/validate_contracts.py --check-response <응답.json>
```

통과 기준: 8개 factor key 외 사용 없음, 각 factor 에 evidence 존재,
`Σ log_contribution == total_log_multiplier`(오차 1e-6), T0 이면 `expected_revenue_krw` null,
온라인 채널 응답 evidence 에 유동인구 근거 없음.

추가로 이번 회차에 스스로 걸어야 할 테스트:
- 택소노미 매핑 없는 노드 → `confidence.level == 'low'` 강제 하향
- 합성 생성기 산출물에 `spend_krw` 가 채워진 셀이 **0건**

> 이 폴더에 `.venv` 가 없어 pytest 가 없다. unittest 를 유지하면 총괄자·검증자·CI 가
> 환경 구축 없이 계속 돌릴 수 있다. 옮기려면 `.gitignore` 와 requirements 를 함께 정리해라.

---

## 하지 말 것

- **8개 `factor_key` 를 추가·개명·재정의하지 마라.** (D-04)
- **Σ 로그 기여도 불변식을 완화하지 마라.** 깨지면 요인 분해가 거짓이 된다.
- **T0 에 금액을 채우지 마라.** (D-03)
- **합성 데이터에 `spend_krw` 를 채우지 마라.** (D-18) — 실데이터 전환 시 모델이 무너진다.
- **매핑 없는 노드를 0 으로 채우지 마라.** confidence 하향이 정답이다. (D-19)
- **"최신값" 피처 헬퍼를 만들지 마라.** 백테스트가 조용히 낙관 편향된다.
- **A 의 실데이터를 기다리며 멈추지 마라.**
- **`shared/contracts/`, `/data-platform`, `/backend`, `/console` 을 수정하지 마라.**
