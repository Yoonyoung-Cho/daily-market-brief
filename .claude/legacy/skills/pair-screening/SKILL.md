---
name: pair-screening
description: 유니버스에서 상관·공적분 기준으로 페어 후보를 선별한다. 종목 쌍 추천이 필요할 때 사용.
---
# 페어 스크리닝 (pair-screening)

## 목적
시드(구조적) 쌍을 통계 검증하고, 시드 외에서 동조화된 쌍을 추가 발굴한다.

## 절차
1. `data/prices.parquet` 로드 → 로그수익률 계산.
2. 시드 쌍: 데이터가 있는 것만 통계지표(상관/공적분/β)를 첨부해 항상 포함.
3. 통계 발굴: 로그수익률 Pearson 상관 ≥ `min_correlation` 인 쌍 →
   Engle-Granger 공적분(coint p) + 잔차 ADF p 가 모두 `coint_pvalue` 이하면 채택.
4. 시드와 매칭되는 발굴 쌍은 `relationship_type` 태그, 아니면 `statistical`.
5. 결과를 `data/candidate_pairs.json` 에 저장, 상위 요약만 반환.

## 핵심 규칙
- **공적분 미검증 쌍 추천 금지** — 단순 상관만으로 추천하면 추세장 가짜 신호.
- 연산량 제한: 상관 상위부터 `max_statistical_pairs` 까지만 공적분 검정.
- 공통 거래일이 `min_overlap_days` 미만이면 제외.

수식·엣지케이스는 reference/cointegration.md 참조.
