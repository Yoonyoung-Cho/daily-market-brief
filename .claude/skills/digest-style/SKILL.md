---
name: digest-style
description: 초심자용 데일리 마켓 브리핑의 글쓰기 규칙·JSON 형식·소스 신뢰도·도메인 지식. brief-writer 와 fact-checker 가 따르는 방법론. 브리핑을 쓰거나 검증할 때 사용.
---
# 브리핑 작성 방법론 (digest-style)

## 독자
주식을 잘 모르는 사람. 매일 5분 안에 "오늘 무슨 일이 있었고, 그게 왜 중요한지"를 알고 싶다.
용어는 처음 나올 때 괄호로 풀어 쓴다. 예: PER(주가가 1년 이익의 몇 배인지).

## 글쓰기 규칙
- 한 문장 20~40자. 한 문장에 숫자 2개 이상 금지.
- "~할 것이다" 단정 금지 → "리포트/보도에 따르면 ~로 본다".
- 매수·매도·비중확대 같은 지시어를 우리 말로 쓰지 않는다. 증권사 의견은 인용으로만.
- 좋은 소식과 우려를 함께 쓴다. 우려는 "⚠️" 로 시작.
- 잡주(소형·테마성) 취급 금지: `config.yaml` `digest.min_marcap_*` 기준 미달, 증권사 리포트 없는
  종목은 픽·핫섹터에서 제외. 뉴스에 등장했다면 뉴스 항목으로만.

## 출력 파일 & 형식
`data/briefing_kr.json`, `data/briefing_us.json` — `src/brief.py:BRIEFING_SCHEMA`.
예시와 각 섹션 작성 팁은 `reference/format.md`.

## 소스 신뢰도 티어 (`reference/sources.md`)
`consensus`(한경 컨센서스 리포트) · `market_data`(거래소 데이터) · `analyst_data`(yfinance 애널리스트)
· `ib_news`(IB 뷰의 뉴스 보도) · `news`(일반 뉴스 보도) · `llm`(종합·해석, 검증 대상).

## 철칙
- 모든 항목 `source_url` 필수. 수치는 출처·수집 데이터에 있는 값만.
- **지수 등락 '주도'는 시총 기여도(`index_drivers`) 기준.** % 등락 상위 소형주 ≠ 지수 주도.
- IB 원문은 유료 → 뉴스로 보도된 뷰만 사용, 그 뉴스 URL 이 출처.
- 도메인 체크리스트는 `reference/domain_knowledge.md` 6번을 매번 적용.
