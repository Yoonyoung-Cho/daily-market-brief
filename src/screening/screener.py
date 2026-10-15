"""페어 스크리닝 — 로그수익률 상관 + Engle-Granger 공적분 검정.

방법론은 .claude/skills/pair-screening/reference/cointegration.md 를 따른다.

핵심 원칙:
- 공적분 미검증 쌍은 추천하지 않는다(추세장 가짜 신호 방지).
- 시드 쌍은 검증을 거쳐 통과 여부와 무관하게 'seed' 출신임을 표기하되,
  통계 지표(상관/공적분/베타)는 동일하게 계산해 함께 제공한다.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, coint

from src.config import Config
from src.screening.seeds import seed_lookup


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """일별 로그수익률 (순수 함수).

    Args:
        prices: 가격 패널.

    Returns:
        로그수익률 패널 (첫 행 제거).
    """
    return np.log(prices).diff().dropna(how="all")


def pearson_corr_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """로그수익률 Pearson 상관행렬.

    Args:
        prices: 가격 패널.

    Returns:
        상관행렬 DataFrame.
    """
    return log_returns(prices).corr()


def engle_granger(
    series_a: pd.Series, series_b: pd.Series
) -> dict[str, float]:
    """Engle-Granger 2단계 공적분 검정 + 잔차 ADF.

    1) coint(a, b) 의 p-value
    2) logA = α + β·logB + ε 회귀 후 잔차 ε 의 ADF p-value

    Args:
        series_a: 종목 A 가격 시계열.
        series_b: 종목 B 가격 시계열.

    Returns:
        {'coint_pvalue', 'adf_pvalue', 'beta', 'alpha', 'n'} dict.
        데이터 부족 시 p-value 들은 1.0.
    """
    df = pd.concat([series_a, series_b], axis=1, keys=["a", "b"]).dropna()
    n = len(df)
    if n < 30:
        return {"coint_pvalue": 1.0, "adf_pvalue": 1.0, "beta": np.nan,
                "alpha": np.nan, "n": float(n)}

    log_a = np.log(df["a"].to_numpy())
    log_b = np.log(df["b"].to_numpy())

    # Engle-Granger coint p-value
    try:
        _, coint_p, _ = coint(log_a, log_b)
    except Exception:  # noqa: BLE001
        coint_p = 1.0

    # 2단계: OLS 베타/알파 + 잔차 ADF
    beta, alpha = np.polyfit(log_b, log_a, 1)
    resid = log_a - (alpha + beta * log_b)
    try:
        adf_p = adfuller(resid, autolag="AIC")[1]
    except Exception:  # noqa: BLE001
        adf_p = 1.0

    return {
        "coint_pvalue": float(coint_p),
        "adf_pvalue": float(adf_p),
        "beta": float(beta),
        "alpha": float(alpha),
        "n": float(n),
    }


def _pair_record(
    ticker_a: str,
    ticker_b: str,
    prices: pd.DataFrame,
    corr: float,
    seed_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    """단일 쌍에 대한 통계 레코드 생성."""
    eg = engle_granger(prices[ticker_a], prices[ticker_b])
    rel = seed_meta["relationship_type"] if seed_meta else "statistical"
    rec: dict[str, Any] = {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "relationship_type": rel,
        "source": "seed" if seed_meta else "statistical",
        "correlation": float(corr),
        "coint_pvalue": eg["coint_pvalue"],
        "adf_pvalue": eg["adf_pvalue"],
        "beta": eg["beta"],
        "alpha": eg["alpha"],
        "n_obs": int(eg["n"]),
    }
    if seed_meta:
        rec["mechanism"] = seed_meta.get("mechanism", "")
        rec["rationale"] = seed_meta.get("rationale", "")
        rec["theme"] = seed_meta.get("theme", "")
        rec["pinned"] = bool(seed_meta.get("pinned", False))
        rec["stake_pct"] = seed_meta.get("stake_pct")
        rec["net_debt"] = seed_meta.get("net_debt")
        rec["name_a"] = seed_meta.get("name_a", ticker_a)
        rec["name_b"] = seed_meta.get("name_b", ticker_b)
    return rec


def screen_pairs(
    prices: pd.DataFrame,
    seeds: list[dict[str, Any]],
    config: Config,
) -> list[dict[str, Any]]:
    """시드 검증 + 통계 발굴을 합쳐 후보 페어 리스트를 만든다.

    Args:
        prices: 정제된 가격 패널.
        seeds: 검증된 시드 페어 리스트.
        config: Config (임계값 포함).

    Returns:
        후보 페어 레코드 리스트. 시드는 항상 포함(통계지표 첨부),
        통계 발굴은 상관·공적분 임계 통과분만 포함.
    """
    sc = config.screening
    available = set(prices.columns)
    lookup = seed_lookup(seeds)
    records: list[dict[str, Any]] = []
    used_pairs: set[frozenset[str]] = set()

    # 1) 시드 쌍 — 데이터가 있는 것만, 통계지표 계산해 첨부
    for s in seeds:
        a, b = s["ticker_a"], s["ticker_b"]
        if a not in available or b not in available:
            continue
        corr = log_returns(prices[[a, b]]).corr().iloc[0, 1]
        records.append(_pair_record(a, b, prices, corr, s))
        used_pairs.add(frozenset({a, b}))

    # 2) 통계 발굴 — 상관 임계 통과 쌍 중 공적분 통과만
    corr_mat = pearson_corr_matrix(prices)
    cols = list(prices.columns)
    candidates: list[tuple[str, str, float]] = []
    for a, b in combinations(cols, 2):
        key = frozenset({a, b})
        if key in used_pairs:
            continue
        c = corr_mat.loc[a, b]
        if pd.notna(c) and c >= sc.min_correlation:
            candidates.append((a, b, float(c)))

    # 상관 높은 순으로 정렬 후 상한까지만 공적분 검정(연산량 제한)
    candidates.sort(key=lambda x: x[2], reverse=True)
    discovered = 0
    for a, b, c in candidates:
        if discovered >= sc.max_statistical_pairs:
            break
        rec = _pair_record(a, b, prices, c, lookup.get(frozenset({a, b})))
        if rec["coint_pvalue"] <= sc.coint_pvalue and rec["adf_pvalue"] <= sc.coint_pvalue:
            records.append(rec)
            discovered += 1

    return records
