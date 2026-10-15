"""가격 수집 + parquet 캐싱 + 정제(결측/이상치 처리).

data-collector 서브에이전트의 구현체. 사이드이펙트(파일 I/O, 네트워크)는
여기에 격리하고, 정제 로직은 순수 함수로 분리한다.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import Config
from src.data.provider import DataProvider, default_date_range, get_provider


def load_watchlist(config: Config) -> dict[str, Any]:
    """포커스 유니버스(워치리스트) 정의를 로드한다.

    Args:
        config: Config.

    Returns:
        watchlist.json 내용. 없으면 빈 dict.
    """
    path = config.watchlist_path
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def watchlist_tickers(config: Config) -> list[str]:
    """워치리스트의 종목코드 리스트."""
    wl = load_watchlist(config)
    return [str(t["ticker"]) for t in wl.get("tickers", [])]


def watchlist_names(config: Config) -> dict[str, str]:
    """워치리스트의 {ticker: name} 매핑."""
    wl = load_watchlist(config)
    return {str(t["ticker"]): t["name"] for t in wl.get("tickers", [])}


def collect_fundamentals(
    config: Config,
    tickers: list[str],
    *,
    provider: DataProvider | None = None,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """종목 펀더멘털(시총·상장주식수·PER·PBR)을 수집·캐싱한다.

    Args:
        config: Config.
        tickers: 대상 종목코드.
        provider: 주입용 DataProvider.
        force: 캐시 무시 재수집.

    Returns:
        {ticker: {name, marcap, shares, close, per, pbr, is_bluechip}} dict.
    """
    path = config.cache_dir / "fundamentals.json"
    if not force and _is_cache_fresh(path, config.cache.ttl_hours) and path.exists():
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    prov = provider or get_provider(config)
    df = prov.fetch_fundamentals(tickers)
    out: dict[str, dict[str, Any]] = {}
    threshold = config.analysis.bluechip_marcap
    for tk in df.index:
        rec = {k: (None if pd.isna(v) else v) for k, v in df.loc[tk].to_dict().items()}
        mc = rec.get("marcap")
        rec["is_bluechip"] = bool(mc is not None and mc >= threshold)
        out[str(tk)] = rec

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


def market_cap_panel(
    prices: pd.DataFrame, fundamentals: dict[str, dict[str, Any]]
) -> pd.DataFrame:
    """시가총액 시계열 패널 = 가격 × 상장주식수(현재) 근사.

    상장주식수가 기간 내 대체로 일정하다는 가정. NAV 디스카운트(holdco_sub)
    계산에 사용한다.

    Args:
        prices: 가격 패널.
        fundamentals: collect_fundamentals 결과.

    Returns:
        시총 패널 (가격과 동일 인덱스/컬럼, shares 없는 종목은 제외).
    """
    cols = {}
    for tk in prices.columns:
        shares = fundamentals.get(str(tk), {}).get("shares")
        if shares:
            cols[tk] = prices[tk] * float(shares)
    return pd.DataFrame(cols, index=prices.index)


def clean_prices(prices: pd.DataFrame, min_obs_ratio: float = 0.6) -> pd.DataFrame:
    """가격 패널을 정제한다 (순수 함수).

    - 관측치가 너무 적은(상폐/신규상장) 종목 제거
    - 전 구간 NaN/0 종목 제거
    - 0 또는 음수 가격을 NaN 처리 후 전방채움(거래정지 구간 대응)

    Args:
        prices: 인덱스=날짜, 컬럼=ticker 가격 패널.
        min_obs_ratio: 유효 관측치 비율 하한.

    Returns:
        정제된 가격 패널.
    """
    if prices.empty:
        return prices
    df = prices.copy()
    df = df.mask(df <= 0)  # 0/음수 -> NaN
    n = len(df)
    keep = df.columns[df.notna().sum() >= n * min_obs_ratio]
    df = df[keep]
    df = df.ffill().dropna(how="all")
    # 시작 구간 결측이 남은 종목은 공통 시작점 이후만 사용하도록 컬럼별 ffill 유지
    return df


def detect_price_jumps(prices: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """일간 로그수익률이 임계 절대값을 넘는 점프(액면분할/오류 의심)를 표시한다.

    수정주가를 쓰면 대부분 보정되지만, 잔여 이상치 점검용 진단 함수.

    Args:
        prices: 가격 패널.
        threshold: |log return| 임계값(기본 0.5 ≈ ±65%).

    Returns:
        점프 위치 boolean DataFrame.
    """
    log_ret = np.log(prices).diff()
    return log_ret.abs() > threshold


def _is_cache_fresh(path: Path, ttl_hours: float) -> bool:
    """parquet 캐시가 TTL 내에 갱신되었는지 확인."""
    if not path.exists():
        return False
    age_h = (time.time() - path.stat().st_mtime) / 3600.0
    return age_h <= ttl_hours


def collect_prices(
    config: Config,
    *,
    provider: DataProvider | None = None,
    universe_limit: int | None = None,
    tickers: list[str] | None = None,
    force: bool = False,
    today: datetime | None = None,
) -> pd.DataFrame:
    """유니버스(또는 포커스 워치리스트) 수정주가를 수집·정제하고 parquet 캐싱한다.

    티커 결정 우선순위:
      1) 명시적 `tickers` 인자
      2) UNIVERSE 가 워치리스트(예: AI_SEMI_KR)이고 watchlist.json 이 있으면 그 종목
      3) provider.list_universe() 전체

    Args:
        config: Config.
        provider: 주입용 DataProvider. None 이면 get_provider(config).
        universe_limit: 유니버스 상위 N 종목으로 제한(개발/속도).
        tickers: 명시적 수집 대상 종목코드.
        force: True 면 캐시 무시하고 재수집.
        today: 기준일(테스트 주입용).

    Returns:
        정제된 가격 패널 (인덱스=날짜, 컬럼=ticker).
    """
    path = config.prices_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if not force and _is_cache_fresh(path, config.cache.ttl_hours):
        return pd.read_parquet(path)

    prov = provider or get_provider(config)
    if tickers is None:
        wl = watchlist_tickers(config)
        if wl:
            tickers = wl
        else:
            universe = prov.list_universe()
            tickers = universe["ticker"].astype(str).tolist()
    if universe_limit:
        tickers = tickers[:universe_limit]

    start, end = default_date_range(config, today=today)
    raw = prov.fetch_prices(tickers, start, end)
    clean = clean_prices(raw)
    # LOOKBACK_DAYS 거래일만 보존
    clean = clean.tail(config.lookback_days)
    clean.to_parquet(path)
    return clean


def load_universe_names(
    config: Config, provider: DataProvider | None = None
) -> dict[str, str]:
    """ticker -> name 매핑 (표시용).

    Args:
        config: Config.
        provider: 주입용 DataProvider.

    Returns:
        {ticker: name} dict. 실패 시 빈 dict.
    """
    prov = provider or get_provider(config)
    try:
        uni = prov.list_universe()
        return dict(zip(uni["ticker"].astype(str), uni["name"].astype(str)))
    except Exception:  # noqa: BLE001
        return {}
