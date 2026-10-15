# 소스 & 신뢰도 티어

## 수집되는 소스 (파이썬, `scripts/collect.sh`)
| 파일 | 내용 | 시장 |
|---|---|---|
| `data/market_kr.json` | 코스피·코스닥 지수, 시총 기여 상위(index_drivers), 등락·시총 상위 | KR |
| `data/consensus_kr.json` | 한경 컨센서스 당일 리포트 메타 | KR |
| `data/report_archive.json` | 리포트 누적 아카이브(본문 발췌·의견·목표가). 최근 7일 자동 백필 | KR |
| `data/us_archive.json` | yfinance 애널리스트 등급변경·목표가 + 종목 뉴스(최근 31일) | US |
| `data/us_consensus.json` | 종목별 매수/보유/매도 분포·평균 목표가·현재가 | US |

## 웹 리서치(보조)
- 글로벌 IB(Goldman·JPMorgan·Morgan Stanley) 뷰 → 원문 유료. **뉴스 보도**만 사용.
- 시장 뉴스 → 연합뉴스·한경·매경·CNBC·Reuters·Bloomberg 등. 기사 URL 이 출처.

## 티어 (대시보드 배지)
| tier | 의미 | 신뢰도 |
|---|---|---|
| `consensus` | 한경 컨센서스 리포트(본문·메타) | 높음 |
| `market_data` | 거래소 시장 데이터 | 높음 |
| `analyst_data` | yfinance 애널리스트 액션·컨센서스 | 높음 |
| `ib_news` | IB 뷰의 뉴스 보도(원문 아님) | 중간 |
| `news` | 일반 뉴스 보도 | 중간 |
| `llm` | LLM 종합·해석 | 낮음(검증 필요) |
