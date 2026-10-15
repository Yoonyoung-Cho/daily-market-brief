"""시장 스냅샷 수집 — 지수·등락 상위·시총 상위 (data-collector 확장).

FinanceDataReader 로 KOSPI/KOSDAQ 지수와 당일 등락·시총 상위를 수집한다.
집계 로직(`build_snapshot`)은 순수 함수로 분리해 네트워크 없이 테스트한다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Config

_INDICES = {"KS11": "KOSPI", "KQ11": "KOSDAQ"}


def build_snapshot(
    listing: pd.DataFrame,
    indices: dict[str, dict[str, float]],
    *,
    top_n: int = 10,
    min_marcap: float = 5.0e11,
) -> dict[str, Any]:
    """시장 스냅샷 집계 (순수 함수).

    Args:
        listing: KRX 전종목 스냅샷(Code, Name, Close, ChagesRatio, Marcap 등).
        indices: {지수명: {close, change_pct}}.
        top_n: 상위 개수.
        min_marcap: 등락 상위 집계 시 최소 시총(잡주 제외).

    Returns:
        {indices, top_gainers, top_losers, top_marcap} dict.
    """
    df = listing.copy()
    df["Code"] = df["Code"].astype(str)
    # 장 시작 전 KRX 목록은 Close/ChagesRatio 가 '-' 문자열로 온다 → NaN 으로 강제
    for col in ("Close", "ChagesRatio", "Marcap"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if df["Close"].isna().all():
        raise ValueError("KRX 목록에 종가가 없음(장 시작 전·휴장). 장 마감 후 다시 수집하세요.")
    liquid = df[df["Marcap"].fillna(0) >= min_marcap]

    def _rows(frame: pd.DataFrame, cols: dict[str, str]) -> list[dict[str, Any]]:
        out = []
        for _, r in frame.iterrows():
            out.append({
                "ticker": str(r["Code"]),
                "name": r.get("Name", ""),
                "close": float(r.get("Close", float("nan"))),
                "change_pct": float(r.get("ChagesRatio", float("nan"))),
                "marcap": float(r.get("Marcap", float("nan"))),
            })
        return out

    gainers = liquid.sort_values("ChagesRatio", ascending=False).head(top_n)
    losers = liquid.sort_values("ChagesRatio", ascending=True).head(top_n)
    big = df.sort_values("Marcap", ascending=False).head(top_n)

    # 지수 기여도(시총가중) = 등락% × 시총. 코스피 지수를 실제로 움직인 종목.
    # %낙폭 상위(초소형주)와 달리, 지수를 끌어내린/올린 '진짜 드라이버'를 식별한다.
    drv = df.copy()
    if "Market" in drv.columns:
        drv = drv[drv["Market"] == "KOSPI"]
    drv = drv.dropna(subset=["ChagesRatio", "Marcap"])
    drv["_contrib"] = drv["ChagesRatio"] * drv["Marcap"]
    # 끌어내린=음(-) 기여만, 끌어올린=양(+) 기여만
    drivers_down = _rows(drv[drv["_contrib"] < 0].nsmallest(top_n, "_contrib"), {})
    drivers_up = _rows(drv[drv["_contrib"] > 0].nlargest(top_n, "_contrib"), {})

    return {
        "indices": indices,
        "index_drivers": {"down": drivers_down, "up": drivers_up},
        "top_gainers": _rows(gainers, {}),
        "top_losers": _rows(losers, {}),
        "top_marcap": _rows(big, {}),
    }


def build_quotes(
    listing: pd.DataFrame, tickers: list[str]
) -> dict[str, dict[str, Any]]:
    """지정 종목의 시세 dict 를 만든다 (순수 함수).

    Args:
        listing: KRX 전종목 스냅샷(Code, Name, Close, ChagesRatio, Marcap).
        tickers: 시세를 붙일 종목코드.

    Returns:
        {ticker: {name, close, change_pct, marcap}}.
    """
    df = listing.copy()
    df["Code"] = df["Code"].astype(str)
    for col in ("Close", "ChagesRatio", "Marcap"):  # 장 전 '-' 문자열 → NaN
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    idx = df.set_index("Code")
    out: dict[str, dict[str, Any]] = {}
    for tk in tickers:
        tk = str(tk)
        if tk in idx.index:
            r = idx.loc[tk]
            out[tk] = {
                "name": r.get("Name", tk),
                "close": float(r.get("Close", float("nan"))),
                "change_pct": float(r.get("ChagesRatio", float("nan"))),
                "marcap": float(r.get("Marcap", float("nan"))),
            }
    return out


def fetch_quotes(
    config: Config,
    tickers: list[str],
    *,
    listing: pd.DataFrame | None = None,
) -> dict[str, dict[str, Any]]:
    """지정 종목의 현재 시세를 가져온다(브리핑 종목 픽에 주가 부착용).

    Args:
        config: Config.
        tickers: 종목코드 리스트.
        listing: 주입용 전종목 스냅샷(테스트). 없으면 FDR StockListing('KRX').

    Returns:
        {ticker: {name, close, change_pct, marcap}}.
    """
    if not tickers:
        return {}
    if listing is None:
        import FinanceDataReader as fdr
        listing = fdr.StockListing("KRX")
    return build_quotes(listing, tickers)


def _index_change(fdr_module, code: str) -> dict[str, float]:
    """지수 최근 종가·등락률."""
    df = fdr_module.DataReader(code).tail(2)
    if df is None or df.empty or "Close" not in df:
        return {"close": float("nan"), "change_pct": float("nan")}
    close = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
    chg = (close / prev - 1.0) * 100.0 if prev else float("nan")
    return {"close": close, "change_pct": chg}


def fetch_market_snapshot(
    config: Config,
    *,
    listing: pd.DataFrame | None = None,
    indices: dict[str, dict[str, float]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """시장 스냅샷을 수집·캐싱한다.

    Args:
        config: Config.
        listing: 주입용 전종목 스냅샷(테스트). 없으면 FDR StockListing('KRX').
        indices: 주입용 지수(테스트). 없으면 FDR 로 수집.
        force: 캐시 무시.

    Returns:
        build_snapshot 결과 + source/generated 메타.
    """
    path = config.cache_dir / "market_kr.json"
    if listing is None and not force and path.exists():
        from src.data.collector import _is_cache_fresh

        if _is_cache_fresh(path, config.cache.ttl_hours):
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    if listing is None or indices is None:
        import FinanceDataReader as fdr

        if listing is None:
            listing = fdr.StockListing("KRX")
        if indices is None:
            indices = {}
            for code, name in _INDICES.items():
                try:
                    indices[name] = _index_change(fdr, code)
                except Exception:  # noqa: BLE001
                    indices[name] = {"close": float("nan"), "change_pct": float("nan")}

    snap = build_snapshot(listing, indices)
    snap["source"] = "FinanceDataReader (KRX)"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=2)
    return snap
