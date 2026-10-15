---
name: market-structure
description: 한국시장 구조적 페어(보통주-우선주, 지주사-자회사, 그룹 밸류체인)를 큐레이션하고 관계유형·괴리 메커니즘을 정의한다. 경제적 근거 있는 쌍 추천·해석이 필요할 때 사용.
---
# 한국시장 구조적 페어 도메인 지식 (market-structure)

## 관계 유형과 괴리 측정 방식
- `pref_common`  : 보통주-우선주. 괴리 = **우선주 할인율** `1 − (P_pref/P_common)`.
  → reference/pref_common.md
- `holdco_sub`   : 지주사-자회사. 괴리 = **NAV 디스카운트** `1 − (지주사시총/(지분가치−순부채))`.
  → reference/holdco_discount.md
- `group_chain`  : 동일 그룹 밸류체인. 괴리 = **스프레드 z-score**.
- `industry_peer`: 동일 산업 경쟁사. 괴리 = **스프레드 z-score**.

## 시드 페어 관리
- 큐레이션 목록은 reference/seed_pairs.md 에서 관리하고 `data/seed_pairs.json` 으로 출력.
- 스키마: `ticker_a, name_a, ticker_b, name_b, relationship_type, mechanism,
  stake_pct?, net_debt?, notes`.
- `pref_common` 은 `ticker_a`=보통주, `ticker_b`=우선주 순서를 지킨다.
- `holdco_sub` 은 `ticker_a`=지주사, `ticker_b`=자회사 순서를 지키고
  `stake_pct`(지분율)·`net_debt`(순부채)를 최신 공시로 채운다.

## 유지보수 규칙 (구조적 관계는 변한다)
- 합병·지주사 전환·지분 매각 등으로 관계가 끊기면 시드에서 제거하거나
  `statistical` 로 강등.
- 검증되지 않은 placeholder 항목은 로더가 자동 배제한다.
- NAV 입력값(지분율·순부채)은 분기보고서/공시 기준으로 주기적 갱신.
