---
name: data-fetch
description: 유니버스 종목의 일별 수정주가를 수집·캐싱한다. 시장(KR/US) 데이터가 필요할 때 사용.
---
# 데이터 수집 (data-fetch)

## 목적
유니버스 전 종목의 일별 **수정주가**를 수집하고 parquet 으로 캐싱한다.
레이트리밋·재호출을 최소화하고, 결측·상폐·거래정지 종목을 정제한다.

## 절차
1. `config.yaml` 의 `MARKET` 으로 `DataProvider` 선택 (`get_provider`).
2. `list_universe()` 로 구성종목 → `fetch_prices()` 로 수정주가 수집.
3. `clean_prices()` 로 정제: 0/음수 → NaN, 관측치 부족 종목 제거, ffill.
4. `LOOKBACK_DAYS` 거래일만 보존 후 `data/prices.parquet` 저장.
5. 캐시가 TTL(`cache.ttl_hours`) 내면 재수집 생략.

## 규칙
- 수정주가 사용(배당·액면분할 보정). 잔여 점프는 `detect_price_jumps` 로 점검.
- 네트워크 실패는 지수 백오프 재시도(`cache.max_retries`, `backoff_seconds`).
- 사이드이펙트는 `src/data/` 경계 계층에만.

자세한 소스별 주의사항은 reference/sources.md 참조.
