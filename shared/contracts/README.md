# SellFinder — 공유 계약 (Shared Contracts)

이 폴더는 **모든 에이전트가 따라야 하는 단일 진실 공급원(Single Source of Truth)** 입니다.

## 절대 규칙

1. **이 폴더의 파일은 어떤 에이전트도 직접 수정하지 않는다.**
   변경이 필요하면 자신의 작업 폴더에 `CONTRACT_CHANGE_REQUEST.md` 를 작성해
   `{변경 대상 파일 / 현재 정의 / 제안 정의 / 변경 사유 / 영향받는 다른 에이전트}` 를 기록한다.
   승인·병합은 사람(jin)만 수행한다.
2. 계약과 자신의 기존 구현이 다르면 **계약이 이긴다.** 기존 코드를 계약에 맞춰 리팩터링한다.
3. 계약 파일의 `$version` 이 올라가면 모든 에이전트는 다음 커밋 전에 재확인한다.

## 읽는 순서

| # | 파일 | 내용 | 필독 대상 |
|---|------|------|-----------|
| 0 | `00_product_spec.md` | 무엇을 만드는가 / 누가 쓰는가 / 어떤 의사결정을 돕는가 | **전원** |
| 1 | `01_domain_model.json` | 엔티티·필드·관계 (멀티테넌트 데이터 모델) | 전원 |
| 2 | `02_taxonomy.json` | 상품 카테고리 · 유통 채널 분류 + 공개데이터 코드 매핑 | A, B, D |
| 3 | `03_region_features.json` | 지역 계층 · 피처 레지스트리 · 시점 정합성 규칙 | A, B |
| 4 | `04_api_contract.yaml` | REST API (OpenAPI 3.1) | B, C, D |
| 5 | `05_scoring_spec.md` | 점수 정의 · 요인 분해 · 신뢰구간 · 백테스트 | B, D |
| 6 | `06_governance.md` | 테넌트 격리 · 개인정보 · 리니지 · 감사 | A, C |

## 폴더 소유권

```
/data-platform     ← 에이전트 A 전용
/intelligence      ← 에이전트 B 전용
/backend           ← 에이전트 C 전용
/console           ← 에이전트 D 전용
/shared/contracts  ← 사람(jin) 전용, 나머지는 읽기만
/tools             ← 사람(jin) 전용 (검증 스크립트)
```

자기 폴더 밖의 파일을 수정한 커밋은 `tools/validate_contracts.py` 가 CI에서 거부합니다.

## 검증

```bash
python tools/validate_contracts.py --base origin/master --agent A
```
