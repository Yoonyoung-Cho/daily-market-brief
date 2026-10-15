# 브리핑 JSON 형식 & 예시

`data/briefing_{kr,us}.json` — `src/brief.py:BRIEFING_SCHEMA` 준수. 아래는 KR 예시.

```json
{
  "market": "KR",
  "as_of_date": "2026-09-22",
  "plain_summary": [
    "코스피가 1.2% 내렸습니다. 반도체 대형주가 함께 빠진 영향입니다.",
    "증권사 리포트는 조선과 방산에 몰렸습니다. 수주(주문) 소식이 이어지기 때문입니다.",
    "⚠️ 미국 금리 결정이 이번 주에 있어 시장이 조심스러운 분위기입니다."
  ],
  "market_tone": "코스피 3,250(-1.2%)… 하락을 이끈 것은 시총 1·2위 삼성전자·SK하이닉스 (index_drivers 근거)",
  "news": [
    {"title": "삼성전자, 3분기 잠정실적 발표",
     "summary_plain": "삼성전자가 3분기에 얼마를 벌었는지 미리 알렸습니다.",
     "why_it_matters": "코스피에서 가장 큰 회사라, 이 회사 실적이 시장 전체 분위기를 좌우합니다.",
     "tickers": ["005930"], "date": "2026-09-22",
     "tier": "news", "source_url": "https://...", "source_name": "연합뉴스"}
  ],
  "hot_sectors": [
    {"sector": "조선", "trend": "LNG선 발주 기대로 리포트가 몰림",
     "drivers": "미국 LNG 터미널 투자 확정", "tickers": ["HD현대중공업", "한화오션"],
     "tier": "consensus", "source_url": "https://consensus.hankyung.com/...", "source_name": "한경 컨센서스"}
  ],
  "notable_stocks": [
    {"name": "한화에어로스페이스", "ticker": "012450",
     "note": "방산 수출 계약 소식으로 증권사 3곳이 같은 날 리포트를 냈습니다.",
     "report_summary": "A증권 목표가 상향, B증권 '수주 잔고 사상 최대'",
     "tier": "consensus", "source_url": "https://...", "source_name": "한경 컨센서스"}
  ],
  "key_reports": [
    {"title": "…", "broker": "대신증권", "ticker": "005940", "opinion": "Buy", "target_price": "45,000원",
     "summary": "본문 1~2줄", "tier": "consensus", "source_url": "https://consensus.hankyung.com/analysis/downpdf?report_idx=…"}
  ],
  "broker_views": [
    {"firm": "Goldman Sachs", "view": "한국 비중확대 유지", "date": "2026-09",
     "tier": "ib_news", "source_url": "https://..."}
  ],
  "glossary": [
    {"term": "시총(시가총액)", "meaning": "주가 × 주식 수. 회사의 '시장 가격표'."},
    {"term": "목표주가", "meaning": "증권사가 1년 안에 도달할 수 있다고 보는 주가. 예측이지 약속이 아님."}
  ]
}
```

## 섹션별 팁
- `plain_summary`: 정확히 3문장. 첫 문장은 지수, 둘째는 리포트/섹터, 셋째는 주의점(⚠️).
- `news`: 3~6개. "무슨 일" 과 "왜 중요" 를 분리. 종목 뉴스면 `tickers`(KR 6자리 / US 심볼).
- `notable_stocks`: 4~6개. `ticker` 필수(렌더가 현재가·등락·시총 자동 부착). 가격 직접 쓰지 말 것.
- `hot_sectors`: 3~5개. 리포트 쏠림(consensus) + 뉴스 교차.
- `glossary`: 3~5개. 본문에 실제로 등장한 용어만.
- US 는 통화 $ 표기, `tickers` 는 심볼. 애널리스트 액션 출처는 `analyst_data` 티어.
