---
name: market-briefing
description: 한경 컨센서스 + 글로벌 IB 뉴스로 '오늘 어떤 산업·종목이 뜨고 경향이 어떤지'를 출처와 함께 요약하는 방법론. 마켓 브리핑 작성 시 사용.
---
# 마켓 브리핑 방법론 (market-briefing)

## 목표
매일 아침 "오늘 시장에서 무엇이 핫하고 굳건한가"를 **출처 있는** 요약으로.
src/brief.py 의 `BRIEFING_SCHEMA` 형식으로 `data/briefing_kr.json` 작성.

## 절차
1. 수집된 `data/consensus_kr.json`(리포트 쏠림·종목)·`data/market_kr.json`(지수·등락) 읽기.
2. 웹 리서치: 한경 컨센서스 산업/시장 리포트, 글로벌 IB(Goldman·JPMorgan 등) **뉴스 보도**.
3. 4개 섹션 작성: market_tone / hot_sectors / notable_stocks / broker_views.
4. 각 항목에 source_url·source_name·tier 부여 → 저장 → research-verifier 검증.

## 소스 신뢰도 티어 (reference/sources.md)
- `consensus` 한경 컨센서스(공개 1차 메타) · `ib_news` IB 뉴스 보도(2차) ·
  `market_data` 시장 데이터 · `llm` LLM 종합(검증 대상).

## 철칙
- 출처 없는 항목 금지. 수치는 출처/데이터에 있는 값만(환각 금지).
- **지수 등락 '주도'는 시총 기여도(`index_drivers`) 기준.** % 낙폭 상위(초소형주)를
  지수 주도로 쓰지 말 것 — 코스피는 시총가중이라 대형주(삼성전자·SK하이닉스 등)가 지수를 움직인다.
- IB 원문은 유료 → 뉴스 보도된 뷰만, 그 뉴스 URL 을 출처로.
- 최근 자료 우선. 투자 권유·예측 단정 금지. 형식·예시는 reference/format.md.
