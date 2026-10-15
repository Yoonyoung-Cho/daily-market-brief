"""경계 계층(DataProvider/collector) + 시각화 테스트 — 네트워크 없이 주입으로 검증."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.config import Config
from src.data.collector import collect_prices, load_universe_names
from src.data.provider import (
    DataProvider,
    _retry,
    default_date_range,
    get_provider,
    KRDataProvider,
    USDataProvider,
)
from src.analysis.divergence import analyze_pair
from src.viz.charts import (
    divergence_band_chart,
    normalized_price_chart,
    zscore_chart,
)


class FakeProvider(DataProvider):
    """네트워크 없는 테스트용 DataProvider."""

    def __init__(self, config, prices, names):
        super().__init__(config)
        self._prices = prices
        self._names = names

    def list_universe(self):
        return pd.DataFrame(
            {"ticker": list(self._names), "name": list(self._names.values())}
        )

    def fetch_prices(self, tickers, start, end):
        return self._prices[[t for t in tickers if t in self._prices.columns]]

    def fetch_market_cap(self, tickers, date):
        return pd.Series({t: 1.0 for t in tickers})

    def fetch_fundamentals(self, tickers):
        rows = {t: {"name": self._names.get(t, t), "marcap": 5e12, "shares": 1e8,
                    "close": 100.0, "per": 12.3, "pbr": 1.1} for t in tickers}
        return pd.DataFrame.from_dict(rows, orient="index")


def test_get_provider_dispatch():
    assert isinstance(get_provider(Config(market="KR")), KRDataProvider)
    assert isinstance(get_provider(Config(market="US")), USDataProvider)
    with pytest.raises(ValueError):
        get_provider(Config(market="JP"))


def test_default_date_range_ordering():
    start, end = default_date_range(Config(), today=datetime(2026, 6, 22))
    assert start < end
    assert end == "2026-06-22"


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("temp")
        return "ok"

    assert _retry(flaky, retries=3, backoff=0.0) == "ok"
    assert calls["n"] == 2


def test_retry_exhausts_and_raises():
    def always_fail():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        _retry(always_fail, retries=2, backoff=0.0)


def test_collect_prices_with_fake_provider(cointegrated_prices, tmp_path):
    cfg = Config()
    object.__setattr__(cfg.cache, "dir", str(tmp_path))
    names = {"AAA": "에이", "BBB": "비", "CCC": "씨"}
    prov = FakeProvider(cfg, cointegrated_prices, names)

    out = collect_prices(cfg, provider=prov, force=True)
    assert not out.empty
    assert cfg.prices_path.exists()

    # 두 번째 호출은 캐시 사용(force=False, TTL 내)
    cached = collect_prices(cfg, provider=prov, force=False)
    assert list(cached.columns) == list(out.columns)

    mapping = load_universe_names(cfg, provider=prov)
    assert mapping["AAA"] == "에이"


def test_collect_fundamentals_bluechip_flag(cointegrated_prices, tmp_path):
    from src.data.collector import collect_fundamentals, market_cap_panel

    cfg = Config()
    object.__setattr__(cfg.cache, "dir", str(tmp_path))
    names = {"AAA": "에이", "BBB": "비", "CCC": "씨"}
    prov = FakeProvider(cfg, cointegrated_prices, names)
    funds = collect_fundamentals(cfg, ["AAA", "BBB"], provider=prov, force=True)
    # FakeProvider marcap=5e12 >= 3e12 기본 임계 -> 대형주
    assert funds["AAA"]["is_bluechip"] is True
    assert funds["AAA"]["per"] == 12.3
    assert (cfg.cache_dir / "fundamentals.json").exists()
    # 시총 패널 = 가격 × 상장주식수
    cap = market_cap_panel(cointegrated_prices[["AAA"]], funds)
    assert (cap["AAA"] > 0).all()


@pytest.fixture
def sample_analysis(pref_common_prices):
    pair = {
        "ticker_a": "005930", "ticker_b": "005935",
        "relationship_type": "pref_common", "source": "seed",
        "correlation": 0.95, "coint_pvalue": 0.01, "half_life": 20.0,
        "name_a": "삼성전자", "name_b": "삼성전자우",
    }
    return analyze_pair(pair, pref_common_prices, Config())


def test_charts_return_figures(sample_analysis):
    f1 = normalized_price_chart(sample_analysis)
    f2 = divergence_band_chart(sample_analysis, (1.0, 2.0))
    f3 = zscore_chart(sample_analysis)
    for f in (f1, f2, f3):
        assert isinstance(f, go.Figure)
        assert len(f.data) >= 1
