"""괴리 계산: z-score 수렴, 룩어헤드 부재, 관계유형 분기, 반감기."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import Config
from src.analysis.divergence import (
    analyze_pair,
    half_life,
    historical_percentile,
    ols_spread,
    preferred_discount,
    rolling_zscore,
)


def test_zscore_converges_to_standard_normal():
    """정상 백색잡음의 z-score 는 평균 0·표준편차 1 에 수렴한다."""
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(0, 1, 3000))
    z = rolling_zscore(s, window=60).dropna()
    assert abs(z.mean()) < 0.1
    assert abs(z.std() - 1.0) < 0.15


def test_no_lookahead_bias():
    """z_t 는 t 이후 데이터에 의존하지 않는다.

    전체 시계열로 계산한 z 와, 미래를 잘라낸 부분 시계열로 계산한 z 가
    같은 시점에서 동일해야 한다.
    """
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(0, 1, 300))
    window = 60
    z_full = rolling_zscore(s, window)
    cut = 200
    z_partial = rolling_zscore(s.iloc[:cut], window)
    # 공통 구간(window 이후 ~ cut 직전)에서 동일
    common = z_partial.dropna().index
    aligned_full = z_full.loc[common]
    aligned_part = z_partial.loc[common]
    pd.testing.assert_series_equal(aligned_full, aligned_part, check_exact=False, rtol=1e-9)


def test_rolling_excludes_current_observation():
    """rolling 후 shift(1) 로 현재 관측치가 통계에서 빠진다."""
    s = pd.Series([0, 0, 0, 0, 0, 100.0])  # 마지막에 급등
    z = rolling_zscore(s, window=5)
    # 마지막 값은 '직전 5개(모두 0)'로 표준화 -> std=0 -> NaN
    assert pd.isna(z.iloc[-1])


def test_preferred_discount_sign():
    """우선주가 보통주보다 싸면 할인율은 양수."""
    common = pd.Series([100.0, 110.0])
    pref = pd.Series([80.0, 88.0])
    disc = preferred_discount(common, pref)
    assert (disc > 0).all()
    assert abs(disc.iloc[0] - 0.2) < 1e-9


def test_ols_spread_beta_recovery(cointegrated_prices: pd.DataFrame):
    """OLS 스프레드의 β 가 참값(0.95) 근방으로 추정된다."""
    _, beta, _ = ols_spread(cointegrated_prices["AAA"], cointegrated_prices["BBB"])
    assert 0.7 < beta < 1.2


def test_half_life_mean_reverting():
    """평균회귀 AR(1) 계열은 유한 반감기를 가진다."""
    rng = np.random.default_rng(2)
    n = 1000
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + rng.normal(0, 1)
    hl = half_life(pd.Series(x))
    assert np.isfinite(hl)
    assert 0 < hl < 50


def test_half_life_random_walk_is_inf():
    """랜덤워크는 평균회귀하지 않아 반감기 무한."""
    rng = np.random.default_rng(3)
    rw = pd.Series(np.cumsum(rng.normal(0, 1, 1000)))
    hl = half_life(rw)
    # 랜덤워크는 평균회귀가 없거나(∞) 유한표본에서 매우 긴 반감기를 갖는다.
    # 핵심 주장: 짧은 반감기로 오판하지 않는다.
    assert np.isinf(hl) or hl > 40


def test_historical_percentile():
    """백분위는 현재값 이하 비율."""
    s = pd.Series(range(100))
    assert abs(historical_percentile(s, 49) - 50.0) < 1.0


def test_analyze_pref_common(pref_common_prices: pd.DataFrame):
    """pref_common 분석은 우선주 할인율 라벨과 ok 상태를 낸다."""
    cfg = Config()
    pair = {
        "ticker_a": "005930", "ticker_b": "005935",
        "relationship_type": "pref_common", "source": "seed",
        "correlation": 0.95, "coint_pvalue": 0.01, "half_life": 20.0,
        "name_a": "삼성전자", "name_b": "삼성전자우",
    }
    res = analyze_pair(pair, pref_common_prices, cfg)
    assert res["status"] == "ok"
    assert res["label"] == "우선주 할인율"
    assert 0.1 < res["current_metric"] < 0.35
    assert "series" in res and len(res["series"]["dates"]) > 0
