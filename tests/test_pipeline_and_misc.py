"""파이프라인 통합·랭킹·시드·설정·콜렉터 정제 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.ranking import rank_pairs, score_pair
from src.config import Config, load_config
from src.data.collector import clean_prices, detect_price_jumps
from src.screening.seeds import _is_valid_seed, load_seed_pairs
from src.pipeline import run_pipeline


def test_load_config_defaults():
    """config.yaml 로딩 시 핵심 값이 채워진다."""
    cfg = load_config()
    assert cfg.market in {"KR", "US"}
    assert cfg.rolling_window > 0
    assert cfg.disclaimer  # 디스클레이머 존재


def test_clean_prices_removes_sparse_and_nonpositive():
    """관측 부족/0·음수 컬럼 처리."""
    idx = pd.bdate_range("2023-01-02", periods=10)
    df = pd.DataFrame({
        "good": np.linspace(100, 110, 10),
        "sparse": [100, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan],
        "zero": [0] * 10,
    }, index=idx)
    cleaned = clean_prices(df, min_obs_ratio=0.6)
    assert "good" in cleaned.columns
    assert "sparse" not in cleaned.columns
    assert "zero" not in cleaned.columns


def test_detect_price_jumps():
    """큰 점프를 표시한다."""
    s = pd.DataFrame({"x": [100.0, 101.0, 300.0, 301.0]})
    jumps = detect_price_jumps(s, threshold=0.5)
    assert bool(jumps["x"].iloc[2])  # 101 -> 300 점프


def test_seed_validation_rejects_bad():
    """잘못된 relationship_type / placeholder / 동일티커 배제."""
    assert not _is_valid_seed({"ticker_a": "A", "ticker_b": "B", "relationship_type": "bogus"})
    assert not _is_valid_seed({"ticker_a": "A", "ticker_b": "A", "relationship_type": "pref_common"})
    assert not _is_valid_seed({"ticker_a": "A", "ticker_b": "B",
                               "relationship_type": "pref_common", "mechanism": "placeholder"})
    assert _is_valid_seed({"ticker_a": "A", "ticker_b": "B", "relationship_type": "pref_common"})


def test_load_seed_pairs_real_file():
    """실제 seed_pairs.json 이 검증을 통과해 일부 시드를 반환."""
    seeds = load_seed_pairs()
    assert len(seeds) >= 5
    for s in seeds:
        assert s["relationship_type"] in {"pref_common", "holdco_sub", "group_chain", "industry_peer"}


def test_ranking_prefers_seed_and_low_pvalue():
    """시드 + 낮은 p-value + 짧은 반감기가 높은 스코어."""
    strong = {"status": "ok", "source": "seed", "correlation": 0.95,
              "coint_pvalue": 0.001, "half_life": 10.0, "current_zscore": 2.5}
    weak = {"status": "ok", "source": "statistical", "correlation": 0.81,
            "coint_pvalue": 0.049, "half_life": None, "current_zscore": 0.2}
    assert score_pair(strong, 0.3) > score_pair(weak, 0.3)
    ranked = rank_pairs([weak, strong], seed_bonus=0.3)
    assert ranked[0]["source"] == "seed"


def test_full_pipeline_with_injected_prices(cointegrated_prices, pref_common_prices, tmp_path):
    """가격 주입으로 전체 파이프라인이 산출물을 생성한다(네트워크 불필요)."""
    prices = pd.concat([cointegrated_prices, pref_common_prices], axis=1)
    cfg = Config()
    object.__setattr__(cfg.cache, "dir", str(tmp_path))
    summary = run_pipeline(cfg, prices=prices)
    assert summary["n_analyzed"] >= 1
    assert (tmp_path / "candidate_pairs.json").exists()
    assert (tmp_path / "pair_analysis.json").exists()
    # 모든 분석에 해석 문장과 series 가 있다
    import json
    data = json.loads((tmp_path / "pair_analysis.json").read_text(encoding="utf-8"))
    assert all("interpretation" in d for d in data)
