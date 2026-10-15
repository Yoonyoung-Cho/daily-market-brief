"""괴리지표 계산 — relationship_type 별 분기 + z-score/반감기/백분위.

방법론: .claude/skills/spread-calc/reference/zscore_halflife.md

★ 룩어헤드 편향 금지 ★
  rolling 통계는 해당 시점 *이전* 데이터만 써야 한다. pandas rolling 은 현재
  관측치를 포함하므로, z-score 계산 시 평균/표준편차를 1일 shift 하여
  "어제까지의 통계로 오늘을 표준화"한다. 이는 단위테스트로 검증된다.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm


# ──────────────────────────────────────────────────────────────────
# relationship_type 별 괴리 '원지표' 계산 (모두 순수 함수)
# ──────────────────────────────────────────────────────────────────
def preferred_discount(common: pd.Series, pref: pd.Series) -> pd.Series:
    """우선주 할인율 = 1 − (우선주가 / 보통주가).

    Args:
        common: 보통주 가격.
        pref: 우선주 가격.

    Returns:
        할인율 시계열 (양수 = 우선주가 보통주보다 쌈).
    """
    df = pd.concat([common, pref], axis=1, keys=["c", "p"]).dropna()
    return 1.0 - (df["p"] / df["c"])


def nav_discount(
    holdco_cap: pd.Series,
    sub_cap: pd.Series,
    stake_pct: float,
    net_debt: float | None,
) -> pd.Series:
    """지주사 NAV 디스카운트 = 1 − (지주사 시총 / (보유지분가치 − 순부채)).

    보유지분가치 = 자회사 시총 × 지분율. 단순화를 위해 단일 자회사 기준.

    Args:
        holdco_cap: 지주사 시가총액 시계열.
        sub_cap: 자회사 시가총액 시계열.
        stake_pct: 지주사의 자회사 지분율(0~1).
        net_debt: 지주사 순부채(없으면 0 취급).

    Returns:
        NAV 디스카운트 시계열.
    """
    df = pd.concat([holdco_cap, sub_cap], axis=1, keys=["h", "s"]).dropna()
    nd = 0.0 if net_debt is None else float(net_debt)
    nav = df["s"] * float(stake_pct) - nd
    nav = nav.replace(0, np.nan)
    return 1.0 - (df["h"] / nav)


def ols_spread(price_a: pd.Series, price_b: pd.Series) -> tuple[pd.Series, float, float]:
    """logP_A = α + β·logP_B + ε 의 스프레드(잔차)와 β, α.

    Args:
        price_a: 종목 A 가격.
        price_b: 종목 B 가격.

    Returns:
        (spread 시계열, beta, alpha).
    """
    df = pd.concat([price_a, price_b], axis=1, keys=["a", "b"]).dropna()
    log_a = np.log(df["a"])
    log_b = np.log(df["b"])
    X = sm.add_constant(log_b.to_numpy())
    model = sm.OLS(log_a.to_numpy(), X).fit()
    alpha, beta = float(model.params[0]), float(model.params[1])
    spread = log_a - (alpha + beta * log_b)
    return spread, beta, alpha


# ──────────────────────────────────────────────────────────────────
# z-score / 반감기 / 백분위
# ──────────────────────────────────────────────────────────────────
def rolling_zscore(metric: pd.Series, window: int) -> pd.Series:
    """룩어헤드 없는 롤링 z-score.

    z_t = (x_t − mean(x_{t-window..t-1})) / std(x_{t-window..t-1})
    현재값을 통계에서 제외하기 위해 rolling 후 shift(1) 한다.

    Args:
        metric: 괴리 원지표 시계열.
        window: 롤링 윈도우(거래일).

    Returns:
        z-score 시계열 (앞쪽 window 구간은 NaN).
    """
    roll = metric.rolling(window=window, min_periods=window)
    mean = roll.mean().shift(1)
    std = roll.std(ddof=0).shift(1)
    z = (metric - mean) / std.replace(0, np.nan)
    return z


def half_life(metric: pd.Series) -> float:
    """OU(Ornstein-Uhlenbeck) 평균회귀 반감기 추정.

    Δx_t = λ·(x_{t-1}) + c + e_t 회귀에서 λ<0 이면
    half-life = −ln(2) / ln(1+λ) ≈ −ln(2)/λ.

    Args:
        metric: 괴리 원지표(또는 스프레드) 시계열.

    Returns:
        반감기(거래일). 평균회귀하지 않으면(λ>=0) np.inf.
    """
    s = metric.dropna()
    if len(s) < 10:
        return float("inf")
    lag = s.shift(1).dropna()
    delta = (s - s.shift(1)).dropna()
    lag, delta = lag.align(delta, join="inner")
    X = sm.add_constant(lag.to_numpy())
    model = sm.OLS(delta.to_numpy(), X).fit()
    lam = float(model.params[1])
    # 평균회귀 없음(λ>=0) 또는 오버슈팅/오실레이션(λ<=-1, log(1+λ) 정의 불가)은
    # 반감기를 산출하지 않는다(랭킹에서 불리하게 ∞ 처리).
    if lam >= 0 or lam <= -1:
        return float("inf")
    hl = -np.log(2) / np.log(1 + lam)
    return float(hl) if hl > 0 else float("inf")


def historical_percentile(metric: pd.Series, value: float) -> float:
    """현재 값의 역사적 백분위(0~100).

    Args:
        metric: 괴리 원지표 시계열.
        value: 현재 값.

    Returns:
        value 이하인 과거 관측치 비율 × 100.
    """
    s = metric.dropna()
    if s.empty:
        return float("nan")
    return float((s <= value).mean() * 100.0)


# ──────────────────────────────────────────────────────────────────
# 통합 분석
# ──────────────────────────────────────────────────────────────────
_LABELS = {
    "pref_common": "우선주 할인율",
    "holdco_sub": "NAV 디스카운트",
    "group_chain": "로그 스프레드",
    "industry_peer": "로그 스프레드",
    "statistical": "로그 스프레드",
}


def compute_divergence_metric(
    pair: dict[str, Any],
    prices: pd.DataFrame,
    *,
    market_cap: pd.DataFrame | None = None,
) -> pd.Series:
    """relationship_type 에 따라 괴리 '원지표' 시계열을 만든다.

    Args:
        pair: 후보 페어 레코드 (relationship_type, ticker_a/b, 메타 포함).
        prices: 가격 패널.
        market_cap: 시총 패널(holdco_sub 용). 없으면 가격 대용.

    Returns:
        괴리 원지표 시계열.
    """
    rel = pair["relationship_type"]
    a, b = pair["ticker_a"], pair["ticker_b"]

    if rel == "pref_common":
        # ticker_a=보통주, ticker_b=우선주 가정
        return preferred_discount(prices[a], prices[b])

    if rel == "holdco_sub":
        if market_cap is not None and a in market_cap and b in market_cap:
            cap_a, cap_b = market_cap[a], market_cap[b]
        else:
            # 시총 미가용 시 가격을 프록시로 사용(상대 변동만 의미)
            cap_a, cap_b = prices[a], prices[b]
        stake = pair.get("stake_pct") or 1.0
        return nav_discount(cap_a, cap_b, float(stake), pair.get("net_debt"))

    # group_chain / industry_peer / statistical -> OLS 스프레드
    spread, _, _ = ols_spread(prices[a], prices[b])
    return spread


def analyze_pair(
    pair: dict[str, Any],
    prices: pd.DataFrame,
    config,
    *,
    market_cap: pd.DataFrame | None = None,
    name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """단일 페어의 괴리지표·z-score·반감기·백분위·해석을 계산한다.

    Args:
        pair: 후보 페어 레코드.
        prices: 가격 패널.
        config: Config.
        market_cap: 시총 패널(선택).
        name_map: {ticker: 표시명} (통계 발굴 쌍의 종목명 보강용).

    Returns:
        분석 결과 dict (시계열은 ISO 날짜 리스트로 직렬화 가능 형태).
        분석가 해석(narrative)·통화 코드 포함.
    """
    from src.analysis.narrative import build_narrative

    names = name_map or {}
    pair = dict(pair)
    pair.setdefault("name_a", names.get(pair["ticker_a"], pair["ticker_a"]))
    pair.setdefault("name_b", names.get(pair["ticker_b"], pair["ticker_b"]))

    window = config.analysis.zscore_window
    metric = compute_divergence_metric(pair, prices, market_cap=market_cap).dropna()
    rel = pair["relationship_type"]
    label = _LABELS.get(rel, "괴리 지표")

    if metric.empty:
        return {**pair, "label": label, "status": "insufficient_data"}

    z = rolling_zscore(metric, window)
    current_metric = float(metric.iloc[-1])
    current_z = float(z.dropna().iloc[-1]) if z.notna().any() else float("nan")
    mean_metric = float(metric.iloc[:-1].tail(window).mean()) if len(metric) > 1 else current_metric
    pct = historical_percentile(metric, current_metric)
    hl = half_life(metric)

    interpretation = _interpret(label, mean_metric, current_metric, current_z, pct, hl)

    result = {
        **{k: pair[k] for k in pair if k not in ("alpha",)},
        "label": label,
        "status": "ok",
        "currency": config.currency.code,
        "current_metric": current_metric,
        "mean_metric": mean_metric,
        "current_zscore": current_z,
        "percentile": pct,
        "half_life": None if np.isinf(hl) else hl,
        "interpretation": interpretation,
        # 시계열 (차트용) — 직렬화 가능 구조
        "series": {
            "dates": [d.strftime("%Y-%m-%d") for d in metric.index],
            "metric": [float(x) for x in metric.to_numpy()],
            "zscore": [None if pd.isna(x) else float(x) for x in z.reindex(metric.index).to_numpy()],
            "price_a": [float(x) for x in prices[pair["ticker_a"]].reindex(metric.index).to_numpy()],
            "price_b": [float(x) for x in prices[pair["ticker_b"]].reindex(metric.index).to_numpy()],
        },
    }
    result["narrative"] = build_narrative(result)
    return result


def _interpret(
    label: str,
    mean_v: float,
    cur_v: float,
    z: float,
    pct: float,
    hl: float,
) -> str:
    """경제적 해석 문장 생성 (순수 함수)."""
    is_pct_metric = "할인율" in label or "디스카운트" in label
    if is_pct_metric:
        mean_s = f"{mean_v * 100:.1f}%"
        cur_s = f"{cur_v * 100:.1f}%"
    else:
        mean_s = f"{mean_v:.4f}"
        cur_s = f"{cur_v:.4f}"

    if np.isnan(z):
        return f"{label} 현재 {cur_s} (평소 {mean_s}). 표본 부족으로 z-score 산출 불가."

    direction = "벌어짐" if z > 0 else "좁혀짐"
    extreme = abs(z)
    if extreme >= 2:
        strength = "평소 대비 매우 크게"
    elif extreme >= 1:
        strength = "평소 대비 다소"
    else:
        strength = "평소 수준에서"

    hl_s = "평균회귀 신호 약함" if np.isinf(hl) else f"평균회귀 반감기 약 {hl:.0f}거래일"
    return (
        f"{label} 평소 {mean_s} → 현재 {cur_s}, "
        f"z-score {z:+.2f}로 {strength} {direction} "
        f"(2년 백분위 {pct:.0f}%). {hl_s}."
    )
