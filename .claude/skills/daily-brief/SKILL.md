---
name: daily-brief
description: 하루 한 번 실행하면 한국·미국 시장 데이터와 증권사 리포트를 새로 받아(놓친 날은 자동 백필) 초심자용 브리핑을 쓰고 검증한 뒤 대시보드와 날짜별 아카이브를 갱신한다. "오늘 브리핑", "데일리", 대시보드 갱신 요청 시 사용.
---
# 데일리 브리핑 (daily-brief)

한 번의 호출로 아래를 끝낸다. 중간에 사용자에게 묻지 않는다.

## 절차
1. **수집(기계적)**: Bash `bash scripts/collect.sh`
   → KR 지수·시총 기여(market_kr.json), 한경 컨센서스 최근 7일 백필(report_archive.json),
     US 애널리스트 액션·뉴스(us_archive.json, us_consensus.json).
   네트워크 실패 항목은 경고만 남기고 계속한다.
2. **작성(LLM)**: `brief-writer` 서브에이전트 → `data/briefing_kr.json`, `data/briefing_us.json`.
3. **검증(LLM)**: `fact-checker` 서브에이전트. 지적 항목은 렌더 전에 반드시 교정·제거.
4. **리포트 한 줄 요약(선택)**: `.venv/bin/python -m src.data.llm_summary prep` 가 0 보다 크면
   `data/summarize_input.json` 을 읽어 `scripts/summarize_prompt.txt` 규칙대로
   `data/summarize_output.json` 을 쓰고 `... llm_summary apply`.
5. **렌더 + 아카이브**: `.venv/bin/python -m src.dashboard_pipeline --render`
   → `data/dashboard.html`(최신) + `data/history/YYYY-MM-DD.html`(날짜별 보존).
6. 보고: 초심자 3줄 요약(KR·US) + 검증 결과 + 파일 경로.

## 원칙
- 출처 없는 항목은 대시보드에 넣지 않는다(렌더가 표시하지 않음).
- 잡주(시총 기준 미달·커버리지 없음)는 픽에 넣지 않는다.
- 모든 화면에 "투자 자문 아님" 디스클레이머(자동 포함).
- 하루 여러 번 돌려도 안전하다(증분·덮어쓰기).
