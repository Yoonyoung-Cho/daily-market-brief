# 데이터 소스 레퍼런스

## KR (한국)
### FinanceDataReader (우선)
- `fdr.StockListing("KOSPI")` / `"KOSPI200"` — 구성종목(컬럼: Code, Name 등).
- `fdr.DataReader(code, start, end)` — 일별 OHLCV. `Close` 는 수정종가 기반.
- 종목코드는 6자리 문자열(예: `005930`). 우선주는 별도 코드(`005935`).

### pykrx (시가총액)
- `stock.get_market_cap_by_date(ymd, ymd, code)` — `시가총액` 컬럼.
- NAV 디스카운트(holdco_sub) 계산에 사용.
- 날짜는 `YYYYMMDD` 포맷.

### 주의
- 거래정지/관리종목: 가격이 멈추거나 결측 → ffill 후 관측치 비율로 제외.
- 우선주 유동성 낮음 → 호가 점프 가능. 수정주가로 대부분 해소.

## US (미국)
### yfinance
- `yf.download(tickers, start, end, auto_adjust=True)` — 복수 티커 일괄.
  `auto_adjust=True` 면 `Close` 가 수정종가.
- 시가총액: `yf.Ticker(t).fast_info.market_cap` (현재값, 시계열 아님).
- S&P500 구성종목은 위키피디아 테이블에서 로드.

### 공통
- 레이트리밋 대응: 재시도 + 백오프. 결과는 parquet 캐싱.
- 티커 형식이 시장마다 다르므로 `DataProvider` 가 흡수.
