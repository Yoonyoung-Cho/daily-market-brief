# 브리핑 소스 & 신뢰도 티어

## 소스
- **한경 컨센서스** `https://consensus.hankyung.com/` — 국내 전 증권사 리포트 메타
  (제목·증권사·분류·날짜·목표가 상향 top). 공개. 파이썬으로 수집됨(`consensus_kr.json`).
- **글로벌 IB 뷰** — Goldman Sachs·J.P.Morgan·Morgan Stanley 등. 원문 리포트는 유료라
  접근 불가 → **뉴스 보도**(CNBC·Bloomberg·한경·연합 등)로 보도된 코멘트만 사용.
- **시장 데이터** — FinanceDataReader(KRX): 지수·등락·시총(`market_kr.json`).

## 신뢰도 티어 (대시보드 배지로 표시)
| tier | 의미 | 신뢰도 |
|---|---|---|
| `consensus` | 한경 컨센서스 공개 메타 | 높음(1차) |
| `market_data` | 거래소 시장 데이터 | 높음(1차) |
| `ib_news` | IB 뷰의 뉴스 보도 | 중간(2차, 원문 아님) |
| `llm` | LLM 이 종합·해석 | 낮음(검증 필요) |

## 검증 원칙 (research-verifier)
- 모든 항목 source_url 필수. 수치는 출처에 실제 존재해야 함.
- 날짜 recency 확인. IB 뷰는 '뉴스 보도'임을 명시(원문 둔갑 금지).
- 애매하면 강등/제외. 투자 자문 아님.
