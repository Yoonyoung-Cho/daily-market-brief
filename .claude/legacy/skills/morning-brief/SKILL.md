---
name: morning-brief
description: 아침에 한 번 실행하면 시장 데이터·증권사 리포트를 새로 받아 마켓 브리핑 대시보드를 갱신한다. "아침 브리핑", "오늘 시장", 대시보드 갱신이 필요할 때 사용.
---
# 아침 마켓 브리핑 (morning-brief)

사용자가 아침에 이 스킬을 부르면, 아래를 순서대로 수행해 `data/dashboard.html` 을 갱신한다.

## 절차
1. **데이터 수집(기계적)**: Bash 로
   `bash scripts/morning.sh`
   → 가격(prices.parquet)·시장 스냅샷(market_kr.json)·한경 컨센서스(consensus_kr.json) 갱신.
2. **리서치 요약(LLM)**: `market-research-analyst` 서브에이전트를 호출해
   `market-briefing` 스킬대로 `data/briefing_kr.json` 작성(모든 항목 출처 필수).
3. **검증**: `research-verifier` 서브에이전트로 출처·수치·날짜 + **도메인 논리**(지수 주도=시총
   기여 등) 검증. 지적된 항목(환각 수치·오류 해석·출처 약한 종목)은 **렌더 전에 반드시 교정/제거**.
3b. **리포트 LLM 요약(강점/기대/우려)**: 기간 동향 카드에 노출되는 상위 리포트(본문 추출된 것)에
   대해, `data/report_archive.json` 의 `text_excerpt` 를 읽고 각 리포트에 **`llm_summary`**(핵심+강점+
   우려를 1~2줄, 우려는 있을 때만 ⚠️ 로) 를 작성해 저장한다. 제목 반복 금지 — 본문 내용으로.
   ■ 불릿이 있는 리포트는 휴리스틱 요약으로 충분하니 비-■(지표테이블형) 위주로 채운다.
4. **페어 분석 갱신(선택)**: 필요하면 `python -m src.pipeline` 로 페어 탭 데이터 갱신.
5. **대시보드 렌더**: `python -m src.dashboard_pipeline --render`
   → `data/dashboard.html` 생성.
6. 사용자에게 핵심 요약(오늘 한눈에 + 핫 섹터 3개 + 검증 결과)과 파일 경로를 보고.

## 원칙
- 한 번의 호출로 위 흐름을 끝낸다(아침 1줄).
- 출처 없는 리서치 항목은 대시보드에 넣지 않는다.
- 네트워크 실패 시: 수집 가능한 데이터만으로 대시보드를 만들고 무엇이 비었는지 알린다.
- 모든 화면에 투자 자문 아님 디스클레이머(자동 포함됨).
