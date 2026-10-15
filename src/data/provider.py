"""DataProvider 추상화 — 시장(KR/US) 전환을 한 줄로 가능하게 한다.

데이터 소스별 구현(KR: FinanceDataReader/pykrx, US: yfinance)은 모두
`DataProvider` 인터페이스를 따른다. 외부 라이브러리 import 는 각 구현 내부에서
지연(lazy) 수행하여, 한쪽 시장만 쓰는 환경에서 불필요한 의존성을 강제하지 않는다.

사이드이펙트(네트워크 I/O)는 이 경계 계층에 격리된다.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Callable, TypeVar

import pandas as pd

from src.config import Config

T = TypeVar("T")


def _retry(fn: Callable[[], T], *, retries: int, backoff: float) -> T:
    """지수 백오프 재시도 래퍼 (레이트리밋 대응).

    Args:
        fn: 인자 없는 호출 가능 객체.
        retries: 최대 재시도 횟수.
        backoff: 초기 대기(초). 매 실패마다 2배.

    Returns:
        fn() 의 반환값.

    Raises:
        마지막 시도의 예외를 그대로 전파.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 소스별 예외가 다양
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    assert last_exc is not None
    raise last_exc


class DataProvider(ABC):
    """시장 데이터 접근 추상 인터페이스."""

    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    def list_universe(self) -> pd.DataFrame:
        """유니버스 구성 종목.

        Returns:
            컬럼 ['ticker', 'name'] 을 가진 DataFrame.
        """

    @abstractmethod
    def fetch_prices(
        self, tickers: list[str], start: str, end: str
    ) -> pd.DataFrame:
        """티커별 일별 수정종가.

        Args:
            tickers: 종목 코드 리스트.
            start: 'YYYY-MM-DD'.
            end: 'YYYY-MM-DD'.

        Returns:
            인덱스=거래일(DatetimeIndex), 컬럼=ticker, 값=수정종가 인 DataFrame.
        """

    @abstractmethod
    def fetch_market_cap(self, tickers: list[str], date: str) -> pd.Series:
        """특정일 시가총액(NAV 디스카운트 계산용).

        Args:
            tickers: 종목 코드 리스트.
            date: 'YYYY-MM-DD'.

        Returns:
            인덱스=ticker, 값=시가총액 인 Series. 미지원 시장은 NaN 으로 채움.
        """

    @abstractmethod
    def fetch_fundamentals(self, tickers: list[str]) -> pd.DataFrame:
        """종목별 펀더멘털 스냅샷.

        Args:
            tickers: 종목 코드 리스트.

        Returns:
            인덱스=ticker, 컬럼=[name, marcap, shares, close, per, pbr] DataFrame.
            미가용 항목은 NaN. (marcap=시가총액, shares=상장주식수)
        """


class KRDataProvider(DataProvider):
    """한국 시장 — FinanceDataReader 우선, 시가총액은 pykrx."""

    def list_universe(self) -> pd.DataFrame:
        import FinanceDataReader as fdr

        if self.config.universe.upper() == "KOSPI200":
            df = _retry(
                lambda: fdr.StockListing("KOSPI"),
                retries=self.config.cache.max_retries,
                backoff=self.config.cache.backoff_seconds,
            )
        else:
            df = _retry(
                lambda: fdr.StockListing(self.config.universe),
                retries=self.config.cache.max_retries,
                backoff=self.config.cache.backoff_seconds,
            )
        code_col = "Code" if "Code" in df.columns else "Symbol"
        name_col = "Name" if "Name" in df.columns else df.columns[1]
        out = df[[code_col, name_col]].rename(
            columns={code_col: "ticker", name_col: "name"}
        )
        return out.dropna().reset_index(drop=True)

    def fetch_prices(
        self, tickers: list[str], start: str, end: str
    ) -> pd.DataFrame:
        import FinanceDataReader as fdr

        series: dict[str, pd.Series] = {}
        for tk in tickers:
            try:
                df = _retry(
                    lambda tk=tk: fdr.DataReader(tk, start, end),
                    retries=self.config.cache.max_retries,
                    backoff=self.config.cache.backoff_seconds,
                )
            except Exception:  # noqa: BLE001 - 상폐/거래정지는 건너뜀
                continue
            if df is None or df.empty or "Close" not in df.columns:
                continue
            series[tk] = df["Close"].astype(float)
        if not series:
            return pd.DataFrame()
        prices = pd.DataFrame(series)
        prices.index = pd.to_datetime(prices.index)
        return prices.sort_index()

    def fetch_market_cap(self, tickers: list[str], date: str) -> pd.Series:
        try:
            from pykrx import stock
        except Exception:  # noqa: BLE001
            return pd.Series({tk: float("nan") for tk in tickers})
        ymd = date.replace("-", "")
        caps: dict[str, float] = {}
        for tk in tickers:
            try:
                cap_df = _retry(
                    lambda tk=tk: stock.get_market_cap_by_date(ymd, ymd, tk),
                    retries=self.config.cache.max_retries,
                    backoff=self.config.cache.backoff_seconds,
                )
                caps[tk] = float(cap_df["시가총액"].iloc[-1])
            except Exception:  # noqa: BLE001
                caps[tk] = float("nan")
        return pd.Series(caps)

    def fetch_fundamentals(self, tickers: list[str]) -> pd.DataFrame:
        import FinanceDataReader as fdr

        listing = _retry(
            lambda: fdr.StockListing("KRX"),
            retries=self.config.cache.max_retries,
            backoff=self.config.cache.backoff_seconds,
        )
        listing["Code"] = listing["Code"].astype(str)
        sub = listing[listing["Code"].isin([str(t) for t in tickers])].set_index("Code")
        rows: dict[str, dict[str, Any]] = {}
        for tk in tickers:
            if tk in sub.index:
                r = sub.loc[tk]
                rows[tk] = {
                    "name": r.get("Name", tk),
                    "marcap": float(r.get("Marcap", float("nan"))),
                    "shares": float(r.get("Stocks", float("nan"))),
                    "close": float(r.get("Close", float("nan"))),
                    "per": float("nan"),
                    "pbr": float("nan"),
                }
            else:
                rows[tk] = {"name": tk, "marcap": float("nan"), "shares": float("nan"),
                            "close": float("nan"), "per": float("nan"), "pbr": float("nan")}
        df = pd.DataFrame.from_dict(rows, orient="index")
        # PER/PBR 은 KRX 자격증명(KRX_ID/KRX_PW)이 있을 때만 pykrx 로 보강
        self._augment_krx_fundamentals(df, tickers)
        return df

    def _augment_krx_fundamentals(self, df: pd.DataFrame, tickers: list[str]) -> None:
        """KRX 로그인 가능 시 PER/PBR 을 채운다(실패해도 조용히 패스)."""
        import os

        if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
            return
        try:
            from pykrx import stock
        except Exception:  # noqa: BLE001
            return
        from datetime import datetime as _dt

        ymd = _dt.now().strftime("%Y%m%d")
        for tk in tickers:
            try:
                f = stock.get_market_fundamental_by_date(ymd, ymd, tk)
                if f is not None and not f.empty:
                    df.loc[tk, "per"] = float(f["PER"].iloc[-1])
                    df.loc[tk, "pbr"] = float(f["PBR"].iloc[-1])
            except Exception:  # noqa: BLE001
                continue


class USDataProvider(DataProvider):
    """미국 시장 — yfinance."""

    def list_universe(self) -> pd.DataFrame:
        # S&P500 구성종목은 위키피디아 테이블로 받는다(yfinance 외부).
        try:
            tables = _retry(
                lambda: pd.read_html(
                    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
                ),
                retries=self.config.cache.max_retries,
                backoff=self.config.cache.backoff_seconds,
            )
            df = tables[0]
            out = df[["Symbol", "Security"]].rename(
                columns={"Symbol": "ticker", "Security": "name"}
            )
            return out.dropna().reset_index(drop=True)
        except Exception:  # noqa: BLE001
            return pd.DataFrame(columns=["ticker", "name"])

    def fetch_prices(
        self, tickers: list[str], start: str, end: str
    ) -> pd.DataFrame:
        import yfinance as yf

        df = _retry(
            lambda: yf.download(
                tickers,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                group_by="column",
            ),
            retries=self.config.cache.max_retries,
            backoff=self.config.cache.backoff_seconds,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        # 단일/복수 티커 모두에서 Close 추출
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"] if "Close" in df.columns.levels[0] else df
        else:
            close = df[["Close"]].rename(columns={"Close": tickers[0]})
        close.index = pd.to_datetime(close.index)
        return close.sort_index()

    def fetch_market_cap(self, tickers: list[str], date: str) -> pd.Series:
        import yfinance as yf

        caps: dict[str, float] = {}
        for tk in tickers:
            try:
                info = yf.Ticker(tk).fast_info
                caps[tk] = float(getattr(info, "market_cap", float("nan")))
            except Exception:  # noqa: BLE001
                caps[tk] = float("nan")
        return pd.Series(caps)

    def fetch_fundamentals(self, tickers: list[str]) -> pd.DataFrame:
        import yfinance as yf

        rows: dict[str, dict[str, Any]] = {}
        for tk in tickers:
            row = {"name": tk, "marcap": float("nan"), "shares": float("nan"),
                   "close": float("nan"), "per": float("nan"), "pbr": float("nan")}
            try:
                info = yf.Ticker(tk).info
                row["name"] = info.get("shortName", tk)
                row["marcap"] = float(info.get("marketCap", float("nan")))
                row["shares"] = float(info.get("sharesOutstanding", float("nan")))
                row["close"] = float(info.get("currentPrice", float("nan")))
                row["per"] = float(info.get("trailingPE", float("nan")))
                row["pbr"] = float(info.get("priceToBook", float("nan")))
            except Exception:  # noqa: BLE001
                pass
            rows[tk] = row
        return pd.DataFrame.from_dict(rows, orient="index")


def get_provider(config: Config) -> DataProvider:
    """설정의 MARKET 에 맞는 DataProvider 를 반환한다.

    Args:
        config: 로딩된 Config.

    Returns:
        KRDataProvider 또는 USDataProvider.

    Raises:
        ValueError: 알 수 없는 MARKET.
    """
    market = config.market.upper()
    if market == "KR":
        return KRDataProvider(config)
    if market == "US":
        return USDataProvider(config)
    raise ValueError(f"지원하지 않는 MARKET: {config.market!r} (KR 또는 US)")


def default_date_range(config: Config, today: datetime | None = None) -> tuple[str, str]:
    """LOOKBACK_DAYS 기반 (start, end) 문자열을 만든다.

    거래일이 아닌 달력일 기준이라 여유분(1.5배)을 둔다.

    Args:
        config: Config.
        today: 기준일(테스트 주입용). None 이면 datetime.now().

    Returns:
        ('YYYY-MM-DD', 'YYYY-MM-DD').
    """
    end = today or datetime.now()
    start = end - timedelta(days=int(config.lookback_days * 1.5))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
