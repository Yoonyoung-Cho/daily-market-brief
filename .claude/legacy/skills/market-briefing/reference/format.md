# 브리핑 JSON 형식 & 예시

`data/briefing_kr.json` — src/brief.py `BRIEFING_SCHEMA` 준수.

```json
{
  "market": "KR",
  "as_of_date": "2026-06-23",
  "market_tone": "코스피는 반도체 강세에 힘입어 ... (지수 데이터 근거)",
  "hot_sectors": [
    {"sector": "조선", "trend": "수주잔고 사상 최대, LNG선 발주 기대",
     "drivers": "미국 LNG 터미널 FID, 빅3 수주 호조",
     "tickers": ["HD현대중공업", "한화오션"],
     "tier": "ib_news", "source_url": "https://...", "source_name": "CNBC"}
  ],
  "notable_stocks": [
    {"name": "한화에어로스페이스", "ticker": "012450",
     "note": "중동 수출 기대로 주목(해석 1~2줄)",
     "report_summary": "CNBC — 방산주 급등 보도, Goldman 미국 재산업화 수혜로 지목",
     "tier": "ib_news", "source_url": "https://www.cnbc.com/...",
     "source_name": "CNBC"}
  ],
  "broker_views": [
    {"firm": "Goldman Sachs", "view": "한국 비중확대, KOSPI 12,000 목표",
     "date": "2026-06", "tier": "ib_news", "source_url": "https://..."}
  ]
}
```

## 작성 팁
- **notable_stocks = 오늘의 종목 픽(핵심)**: 5~6개. 반드시 `ticker`(6자리) +
  `note`(해석) + `report_summary`(증권사 코멘트 종합). 현재가·등락은 렌더가 자동 부착 →
  **가격을 직접 쓰지 말 것**(코드만 정확히).
- hot_sectors 는 3~6개. 컨센서스 리포트 쏠림 + IB 강조 테마 교차.
- broker_views 는 국내 1~2 + 글로벌 1~2. firm/date/url 명확히.
- 한국어. 모든 항목 출처(source_url) 필수. 수치는 출처/데이터값만.
