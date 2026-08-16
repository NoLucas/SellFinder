# REPORT-B — intelligence (에이전트 B) 완료 보고

`orchestrator/BRIEF-B.md` 개정3 + `orchestrator/DISPATCH.md` §2(1차) + 총괄자 지시 2차(VF-012 + 모델 카드)
전부 완료. `intelligence/` 밖은 건드리지 않았고, 매 항목 `git add intelligence`로만 스테이징해
개별 커밋했다. 회신 원문과 재현 명령 전체는 `intelligence/RECONCILIATION.md` §7~8 참고.

---

## 커밋 이력

| 커밋 | 항목 | 완료 조건 실측 |
|---|---|---|
| `158c4d3` | B-1 (VF-001) | `vf_51_mutation.py M1/M2` 둘 다 `failures>0` (M1: 3건, M2: 2건) |
| `4436bde` | B-2 (VF-007) | 계약에 tenant_scoped 키 추가 시뮬레이션 → 테스트 실제로 깨짐 |
| `d7421f9` | B-3 (ADR-004) | `spend_krw`가 suppressed 여부와 무관하게 항상 `None` |
| `775be91` | B-4 (백테스트 하네스) | 누수 함정 피처가 정상 스토어에선 안 보이고, `as_of` 무시하는 깨진 접근자엔 `LeakageDetectedError`로 실제로 잡힘 |
| `7f2222a` | VF-012 + 모델 카드 | 백테스트 실행 시 rho·wMAPE·coverage 세 지표 동시 출력, 누수 함정 재확인 |

## DISPATCH §6 종료 조건 중 B 담당분

- **`vf_51_mutation.py` M1·M2 가 잡힘 (B-1)** — 충족. M1: 3건, M2: 2건 (모두 `test_display_effect_agrees_with_exported_log_contribution`,
  `test_log_contribution_matches_each_factors_own_multiplier`가 잡음; M2는 추가로
  `test_value_over_benchmark_reconstructs_log_contribution`도 잡음).

## 백테스트 실측 (VF-012, `TX-FOOD-BEV-COFFEE-RTD` × `cvs`, 검증구간 2026-01~06)

```
2026-01 n=44 rho=0.941 lift=2.698 wmape=0.482 coverage=0.818
2026-02 n=42 rho=0.919 lift=2.522 wmape=0.459 coverage=0.786
2026-03 n=43 rho=0.892 lift=2.669 wmape=0.494 coverage=0.837
2026-04 n=44 rho=0.947 lift=2.835 wmape=0.392 coverage=0.773
2026-05 n=43 rho=0.893 lift=2.789 wmape=0.385 coverage=0.814
2026-06 n=44 rho=0.941 lift=2.910 wmape=0.335 coverage=0.773
holdout 2026-04 n=10 rho=0.976 lift=1.705 wmape=0.564 coverage=0.900
mean: rho=0.922 lift=2.737 wmape=0.425 coverage=0.800
```

§5.2 T2 목표 대비: ρ 0.92(≥0.60 통과), lift 2.74(≥2.0 통과), coverage 0.80(0.75~0.85 목표
구간 내), **wMAPE 0.43(≤0.25 미달)** — `expected_demand_units`가 원화 캘리브레이션 값이
아니라 상대 단위이기 때문(모델 카드 §3에 설명). 지역유형별로는 metro/major_city/mid_city는
양호하나 **rural은 뚜렷하게 약함**(ρ=0.45, coverage=0.20, n=20).

## 신규 산출물

- `intelligence/backtest/harness.py` — 시간분할·지역홀드아웃·Spearman ρ·top-decile lift·wMAPE·
  PI coverage·경험적 PI 보정·누수 가드
- `intelligence/tests/test_backtest.py` — 60개 중 이번 스위트분
- `intelligence/scoring/MODEL_CARD.md` — 합성 데이터 전용 명시, ADR-004(`spend_krw` 항상 null)·
  D-03(T0 금액 항상 null) 전제, 지역유형별 분해, known_limitations 9개·do_not_use_for 5개.
  모든 수치에 재현 명령 포함, 지어낸 값 없음.

## 테스트

`cd intelligence && python -m unittest discover -s tests -v` → **60 passed** (누적, B-1~VF-012 전부 포함).

## 못 한 것

- 모델 카드 §5.3의 "Tier 별 성적 분해"는 T0만 존재 — T1/T2는 `tenant_calibration`이 전
  tier 중립(1.0) 고정이라 검증 대상 자체가 없다(Step 5 미착수, 결함 아님).
- `category_penetration`의 `spend_index` 유도 재설계(store_count·소비력 프록시)는
  BRIEF-B §2가 명시한 대로 아직 미착수 — 다음 백테스트 확장 작업에서 다룰 항목으로 남겨둔다.
- evidence 문장의 인과 금지/근거 없는 수사 금지 규칙(§6)에 대한 자동 강제 테스트는 없음
  (구조적으로만 방지 중, `verification/CHARTER.md` §5.1 다음 회차 대상으로 이미 문서화돼 있음).
