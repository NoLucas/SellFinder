"""05_scoring_spec.md §6 - evidence 작성 규칙, 4개 조항 강제.

`factors[].evidence` 는 사용자가 그대로 보고서에 붙여넣는 문장이다. 검증 4회차까지
이 4개 조항을 강제하는 테스트가 하나도 없었다(전부 구멍). 이 파일이 그 구멍을 닫는다.

  1. evidence 가 실제 피처값을 인용한다 (§6.1-1)
  2. 비교 기준을 함께 준다 (§6.1-2)
  3. 모델이 실제로 쓰지 않은 근거를 지어내지 않는다 - 특히 값이 null 인 피처를 인용하지
     않는다 (§6.2, `verification/CHARTER.md` 는 이 위반을 S2 로 분류한다)
  4. 인과 주장을 하지 않는다 - 상관을 인과로 쓰지 않는다 (§6.3)

전부 실제 `model.predict_batch()` 호출 결과(진짜 예측 파이프라인)로 검증한다 - 요인
함수를 직접 부르는 단위 테스트가 아니라, C 가 실제로 받게 될 evidence 문자열을 그대로 본다.

Run from /intelligence:
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import re
import unittest

from scoring import model
from scoring.feature_store import SyntheticFeatureStore
from synthetic import generate

_RTD_NODE = "TX-FOOD-BEV-COFFEE-RTD"
_RTD_ATTRS = {"target_age": ["20s", "30s"], "premium_ingredient": True}
_RTD_SEASONALITY = [0.92, 0.90, 0.98, 1.02, 1.08, 1.14, 1.18, 1.16, 1.04, 0.96, 0.92, 0.90]

# 값이 없을 때 각 요인이 쓰는 정확한 문구 (factors.py 를 직접 읽고 그대로 옮김).
# 규칙 3 은 "value is None 인 요인의 evidence 는 이 집합의 원소여야 한다"로 강제한다 -
# 목록에 없는 문장이 나오면 그건 없는 데이터로 뭔가를 지어냈다는 뜻이다.
_KNOWN_NO_VALUE_EVIDENCE = {
    "인구 데이터 없음 - 중립(1.0)으로 처리",
    "해당 지역·채널의 소비 신호 데이터 없음(또는 suppressed) - 중립(1.0)으로 처리",
    "제품 속성과 연결할 수 있는 지역 프로파일 신호 없음 - 중립(1.0)으로 처리",
    "소득분위 데이터 없음 - 중립(1.0)으로 처리",
    "온라인 채널은 경쟁 강도(competitor_density)를 사용하지 않음 (02_taxonomy.json channel_rules)",
    "점포수 데이터 없음(또는 suppressed) - 경쟁 감쇄 없음(1.0)으로 처리",
    "이커머스 주문 밀도 데이터 없음 - 중립(1.0)으로 처리",
    "채널 점포수 데이터 없음(또는 suppressed) - 중립(1.0)으로 처리",
    "계절성 프로필 없음 - 중립(1.0)으로 처리",
    "T0 테넌트 - 자사 실적 데이터 없음, 보정 없음(1.0 고정)",
}
_NO_VALUE_EVIDENCE_PREFIXES = (
    " 테넌트 보정 모델 미구현 (5단계 예정) - 임시로 중립(1.0) 처리",  # f"{data_tier}{...}"
)


def _is_known_no_value_evidence(evidence: str) -> bool:
    if evidence in _KNOWN_NO_VALUE_EVIDENCE:
        return True
    return any(evidence.endswith(suffix) for suffix in _NO_VALUE_EVIDENCE_PREFIXES)


def _extract_numbers(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"-?\d+\.?\d*", text.replace(",", ""))]


def _cites_number_near(evidence: str, target: float, rel_tol: float = 0.03, abs_tol: float = 0.06) -> bool:
    """True if some number printed in `evidence` is target itself, or a
    common transform of it (rounded, or *100 for a percentage rendering),
    within rounding tolerance. Handles the handful of format conventions
    factors.py actually uses (%.0f/%.1f/%.2f/:.1% ) without hardcoding one
    specific factor's template."""
    numbers = _extract_numbers(evidence)
    if not numbers:
        return False
    candidates = {target, abs(target), target * 100, abs(target) * 100}
    for n in numbers:
        for c in candidates:
            if abs(n - c) <= max(abs_tol, abs(c) * rel_tol):
                return True
    return False


# product_affinity's `value`/`benchmark` fields carry the COMBINED geometric-mean
# ratio and a constant 1.0 respectively (factors.py:187) - neither is meant to be
# printed literally in evidence. Its evidence instead cites each SUB-ratio's own
# value+benchmark (age share %, income decile) directly in the text. It's covered
# by its own dedicated test below instead of the generic numeric-citation checks.
_COMPOSITE_VALUE_FACTOR_KEYS = frozenset({"product_affinity"})

_CAUSAL_MARKERS = (
    "때문에", "덕분에", "탓에", "영향으로", "원인으로", "그래서 잘", "따라서 잘",
    "이라서 잘", "여서 잘 팔", "아서 잘 팔",
)


class EvidenceRulesTestCase(unittest.TestCase):
    """규칙 1·2·4는 다양한 조건(채널·가격대·제품속성)으로 실제 predict_batch를 여러 번
    돌려 나온 evidence 전수를 대상으로 강제한다 - 특정 요인 하나만 보는 게 아니라 실제로
    C 에게 나갈 응답 표면 전체를 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate.generate_all(seed=42, start_period="2025-01", end_period="2026-06")
        cls.store = SyntheticFeatureStore.from_dataset(cls.dataset)
        cls.all_regions = cls.store.all_adm_dong_ids()

    def _collect_factors(self) -> list[dict]:
        """여러 채널·가격대·제품속성 조합으로 실제 배치를 돌려 factor dict 를 모은다."""
        runs = [
            dict(channel="cvs", price_tier="mid", product_attributes=_RTD_ATTRS,
                 seasonality_profile=_RTD_SEASONALITY),
            dict(channel="hypermarket", price_tier="premium", product_attributes=_RTD_ATTRS,
                 seasonality_profile=_RTD_SEASONALITY),
            dict(channel="online_marketplace", price_tier="value", product_attributes={},
                 seasonality_profile=_RTD_SEASONALITY),
        ]
        all_factors: list[dict] = []
        for run in runs:
            results = model.predict_batch(
                region_ids=self.all_regions[:30],
                taxonomy_node_id=_RTD_NODE,
                period="2025-06",
                as_of="2025-06-01",
                data_tier="T0",
                store=self.store,
                horizon_months=1,
                **run,
            )
            for r in results:
                all_factors.extend(r.factors)
        return all_factors

    # ------------------------------------------------------------------
    # 규칙 1: 실제 피처값을 인용한다
    # ------------------------------------------------------------------
    def test_evidence_cites_the_factors_own_value_when_value_is_not_none(self) -> None:
        all_factors = self._collect_factors()
        checked = 0
        for f in all_factors:
            if f["value"] is None:
                continue  # 규칙 3 이 이 경우를 다룬다
            if f["key"] in _COMPOSITE_VALUE_FACTOR_KEYS:
                continue  # 별도 테스트 (test_product_affinity_evidence_cites_its_sub_ratio_components)
            self.assertTrue(
                _cites_number_near(f["evidence"], f["value"]),
                f"{f['key']}: value={f['value']!r} 인데 evidence 에 그 값이 안 보인다: {f['evidence']!r}",
            )
            checked += 1
        self.assertGreater(checked, 0, "value가 있는 factor가 하나도 없다 - 이 배치가 뭔가 잘못됐다")

    # ------------------------------------------------------------------
    # 규칙 2: 비교 기준을 함께 준다
    # ------------------------------------------------------------------
    def test_evidence_cites_the_benchmark_when_benchmark_is_present(self) -> None:
        all_factors = self._collect_factors()
        checked = 0
        for f in all_factors:
            if f["value"] is None:
                # 이 지역 자체에 값이 없으면(=value None) 배치 전체 benchmark가
                # 있어도 "이 지역을 기준과 비교했다"고 말할 수 없다 - 비교 자체를
                # 안 하는 게 맞는 동작이다(규칙 3 영역). f["benchmark"]가 채워져
                # 있어도 여기서는 검증 대상이 아니다.
                continue
            if not f["benchmark"]:  # None 또는 0 이면 비교 기준 자체가 없는 케이스
                continue
            if f["key"] in _COMPOSITE_VALUE_FACTOR_KEYS:
                continue  # 별도 테스트
            self.assertTrue(
                _cites_number_near(f["evidence"], f["benchmark"]),
                f"{f['key']}: benchmark={f['benchmark']!r} 인데 evidence 에 비교 기준 숫자가 안 보인다: "
                f"{f['evidence']!r}",
            )
            checked += 1
        self.assertGreater(checked, 0, "benchmark가 있는 factor가 하나도 없다 - 이 배치가 뭔가 잘못됐다")

    def test_evidence_uses_a_comparison_word_when_benchmark_is_present(self) -> None:
        # 숫자 존재 여부와 별개로, "무엇과 비교했는지"를 말로도 밝히는지 확인.
        all_factors = self._collect_factors()
        comparison_markers = ("평균", "기준", "대비")
        checked = 0
        for f in all_factors:
            if f["value"] is None or not f["benchmark"]:
                continue
            self.assertTrue(
                any(m in f["evidence"] for m in comparison_markers),
                f"{f['key']}: benchmark 는 있는데 '평균/기준/대비' 같은 비교 표현이 evidence 에 없다: "
                f"{f['evidence']!r}",
            )
            checked += 1
        self.assertGreater(checked, 0)

    def test_product_affinity_evidence_cites_its_sub_ratio_components(self) -> None:
        """product_affinity(factors.py:187)는 결합된 비율(value/benchmark=1.0)을
        그대로 찍지 않고, 그걸 구성한 서브 비율(연령 비중 %, 소득분위)을 각자의
        비교 기준과 함께 직접 인용한다 - 그래서 일반 검사와 별도로 확인한다."""
        all_factors = self._collect_factors()
        affinity_factors = [f for f in all_factors if f["key"] == "product_affinity" and f["value"] is not None]
        self.assertGreater(len(affinity_factors), 0, "product_affinity가 값을 낸 사례가 없다")
        for f in affinity_factors:
            numbers = _extract_numbers(f["evidence"])
            self.assertGreaterEqual(
                len(numbers), 2,
                f"product_affinity: 서브 비율(값+기준) 숫자가 2개 미만이다: {f['evidence']!r}",
            )
            self.assertTrue(
                any(m in f["evidence"] for m in ("평균", "기준", "대비")),
                f"product_affinity: 비교 표현이 없다: {f['evidence']!r}",
            )

    # ------------------------------------------------------------------
    # 규칙 3 (§6.2, CHARTER S2): 모델이 쓰지 않은 근거를 지어내지 않는다.
    # 값이 null 인 피처는 evidence 문장에 등장하면 안 된다.
    # ------------------------------------------------------------------
    def test_evidence_is_a_known_placeholder_when_value_is_none(self) -> None:
        """value가 None인 모든 factor의 evidence가 미리 확인해둔 '데이터 없음' 문구
        집합의 원소인지 확인한다. 집합에 없는 문장이 나오면 없는 값으로 뭔가를
        지어냈다는 뜻이다 - 숫자를 파싱해서 걸러내는 것보다 강한 검사다."""
        all_factors = self._collect_factors()
        checked = 0
        for f in all_factors:
            if f["value"] is not None:
                continue
            self.assertTrue(
                _is_known_no_value_evidence(f["evidence"]),
                f"{f['key']}: value=None 인데 evidence 가 알려진 '데이터 없음' 문구가 아니다 - "
                f"없는 값으로 뭔가를 지어냈을 수 있다: {f['evidence']!r}",
            )
            checked += 1
        # 이 배치에서 value=None 인 경우가 실제로 있어야 테스트가 의미 있다
        # (online_marketplace 런의 competition=온라인 분기가 항상 이걸 만든다).
        self.assertGreater(checked, 0, "value=None인 factor가 하나도 없다 - 이 규칙을 검증할 대상이 없다")

    def test_null_feature_never_leaks_a_fabricated_number_into_evidence(self) -> None:
        """완료 판정의 핵심: null 피처를 '일부러' 만들어서 그 피처가 근거 문장에
        등장하지 않는지 직접 확인한다. income_decile 을 모든 지역에서 강제로
        None 으로 만드는 래퍼 스토어를 써서 price_acceptance/product_affinity 가
        지어낸 소득분위 숫자를 evidence 에 쓰지 않는지 본다."""

        class _IncomeBlindStore:
            """실제 스토어를 감싸되 income_decile 만 항상 None 으로 덮어쓴다."""

            def __init__(self, inner):
                self._inner = inner

            def get_features(self, region_ids, feature_keys, as_of):
                out = self._inner.get_features(region_ids, feature_keys, as_of)
                if "income_decile" in feature_keys:
                    for region_id in region_ids:
                        out[region_id]["income_decile"] = None
                return out

            def get_demand(self, *a, **k):
                return self._inner.get_demand(*a, **k)

        blind_store = _IncomeBlindStore(self.store)
        results = model.predict_batch(
            region_ids=self.all_regions[:15],
            taxonomy_node_id=_RTD_NODE,
            channel="cvs",
            period="2025-06",
            as_of="2025-06-01",
            data_tier="T0",
            store=blind_store,
            price_tier="premium",
            product_attributes=_RTD_ATTRS,  # premium_ingredient=True -> product_affinity도 income을 쓴다
            seasonality_profile=_RTD_SEASONALITY,
            horizon_months=1,
        )
        self.assertGreater(len(results), 0)
        checked_price = checked_affinity = 0
        for r in results:
            price = next(f for f in r.factors if f["key"] == "price_acceptance")
            self.assertIsNone(price["value"], "income_decile을 None으로 만들었는데 price_acceptance의 value가 채워졌다")
            self.assertEqual(
                price["evidence"], "소득분위 데이터 없음 - 중립(1.0)으로 처리",
                f"income_decile=None인데 price_acceptance evidence가 소득분위 숫자를 지어냈다: {price['evidence']!r}",
            )
            checked_price += 1

            affinity = next(f for f in r.factors if f["key"] == "product_affinity")
            # product_affinity는 income_decile 서브비율이 빠져도 target_age 서브비율은
            # 남아있을 수 있다 - 그래도 "소득"이라는 단어와 분위 숫자는 나오면 안 된다.
            self.assertNotIn("소득", affinity["evidence"], f"income 없는데 product_affinity가 소득을 언급: {affinity['evidence']!r}")
            checked_affinity += 1
        self.assertGreater(checked_price, 0)
        self.assertGreater(checked_affinity, 0)

    # ------------------------------------------------------------------
    # 규칙 4 (§6.3): 인과 주장 금지
    # ------------------------------------------------------------------
    def test_evidence_never_uses_causal_language(self) -> None:
        all_factors = self._collect_factors()
        self.assertGreater(len(all_factors), 0)
        offenders = [
            (f["key"], f["evidence"], marker)
            for f in all_factors
            for marker in _CAUSAL_MARKERS
            if marker in f["evidence"]
        ]
        self.assertEqual(
            offenders, [],
            f"인과 표현이 들어간 evidence가 있다 (상관을 인과로 쓰면 안 됨, §6.3): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
