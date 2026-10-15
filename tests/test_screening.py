"""스크리닝: 공적분 검정·상관·시드 처리."""
from __future__ import annotations

import pandas as pd

from src.config import Config
from src.screening.screener import engle_granger, log_returns, screen_pairs


def test_cointegrated_pair_passes(cointegrated_prices: pd.DataFrame):
    """알려진 공적분 쌍 (AAA, BBB) 은 검정을 통과해야 한다."""
    res = engle_granger(cointegrated_prices["AAA"], cointegrated_prices["BBB"])
    assert res["coint_pvalue"] < 0.05
    assert res["adf_pvalue"] < 0.05
    assert 0.7 < res["beta"] < 1.2  # 참값 0.95 근방


def test_independent_pair_fails(cointegrated_prices: pd.DataFrame):
    """무관한 쌍 (AAA, CCC) 은 공적분 검정을 통과하지 못해야 한다."""
    res = engle_granger(cointegrated_prices["AAA"], cointegrated_prices["CCC"])
    assert res["coint_pvalue"] > 0.05 or res["adf_pvalue"] > 0.05


def test_short_series_returns_safe_default():
    """관측치 부족 시 p-value 1.0 (배제 가능)."""
    s = pd.Series([1.0, 2.0, 3.0])
    res = engle_granger(s, s)
    assert res["coint_pvalue"] == 1.0


def test_log_returns_shape(cointegrated_prices: pd.DataFrame):
    """로그수익률은 첫 행이 제거된다."""
    lr = log_returns(cointegrated_prices)
    assert len(lr) == len(cointegrated_prices) - 1


def test_screen_pairs_includes_cointegrated(cointegrated_prices: pd.DataFrame):
    """통계 발굴: 공적분 쌍이 후보에 포함되고 무관 쌍은 제외."""
    cfg = Config()
    records = screen_pairs(cointegrated_prices, seeds=[], config=cfg)
    pairs = {frozenset({r["ticker_a"], r["ticker_b"]}) for r in records}
    assert frozenset({"AAA", "BBB"}) in pairs
    assert frozenset({"AAA", "CCC"}) not in pairs


def test_seed_pair_always_included(cointegrated_prices: pd.DataFrame):
    """시드 쌍은 통계 통과 여부와 무관하게 포함되고 source='seed'."""
    cfg = Config()
    seed = [{
        "ticker_a": "AAA", "ticker_b": "CCC",
        "relationship_type": "industry_peer", "mechanism": "test",
        "stake_pct": None, "net_debt": None, "notes": "",
    }]
    records = screen_pairs(cointegrated_prices, seeds=seed, config=cfg)
    seed_rec = [r for r in records
                if frozenset({r["ticker_a"], r["ticker_b"]}) == frozenset({"AAA", "CCC"})]
    assert len(seed_rec) == 1
    assert seed_rec[0]["source"] == "seed"
