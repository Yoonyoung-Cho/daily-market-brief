"""우량주 큐레이션·핀·펀더멘털·탭/필터 기능 테스트."""
from __future__ import annotations

import pandas as pd

from src.analysis.ranking import rank_pairs, score_pair
from src.config import Config
from src.data.collector import market_cap_panel
from src.screening.seeds import load_seed_pairs, seed_lookup
from src.viz.report import _fmt_marcap, generate_report
from src.analysis.divergence import analyze_pair


def test_pinned_seed_present():
    """SK스퀘어/SK하이닉스 가 핀(pinned) 시드로 로드된다."""
    seeds = load_seed_pairs()
    lk = seed_lookup(seeds)
    pair = lk.get(frozenset({"402340", "000660"}))
    assert pair is not None
    assert pair["pinned"] is True
    assert pair["relationship_type"] == "holdco_sub"


def test_structural_and_pinned_bonus():
    """구조적·핀 페어가 통계 페어보다 높은 스코어를 받는다."""
    base = {"status": "ok", "correlation": 0.85, "coint_pvalue": 0.02,
            "half_life": 30.0, "current_zscore": 1.0}
    stat = {**base, "source": "statistical", "relationship_type": "statistical"}
    struct = {**base, "source": "seed", "relationship_type": "pref_common"}
    pinned = {**base, "source": "seed", "relationship_type": "holdco_sub", "pinned": True}
    s_stat = score_pair(stat, 0.3, 0.2)
    s_struct = score_pair(struct, 0.3, 0.2)
    s_pin = score_pair(pinned, 0.3, 0.2)
    assert s_pin > s_struct > s_stat


def test_rank_puts_pinned_first():
    base = {"status": "ok", "correlation": 0.85, "coint_pvalue": 0.02,
            "half_life": 30.0, "current_zscore": 2.5}
    items = [
        {**base, "source": "statistical", "relationship_type": "statistical", "ticker_a": "X", "ticker_b": "Y"},
        {**base, "source": "seed", "relationship_type": "holdco_sub", "pinned": True,
         "current_zscore": 0.2, "ticker_a": "402340", "ticker_b": "000660"},
    ]
    ranked = rank_pairs(items, 0.3, 0.2)
    assert ranked[0].get("pinned") is True  # 낮은 |z| 라도 핀이 1위


def test_market_cap_panel():
    idx = pd.bdate_range("2024-01-02", periods=5)
    prices = pd.DataFrame({"005930": [100, 101, 102, 103, 104]}, index=idx, dtype=float)
    funds = {"005930": {"shares": 10.0}}
    cap = market_cap_panel(prices, funds)
    assert cap["005930"].iloc[0] == 1000.0  # 100 * 10


def test_fmt_marcap():
    assert _fmt_marcap(2.065e15).endswith("조원")
    assert _fmt_marcap(None) == "—"


def test_report_has_tabs_and_filters(cointegrated_prices, pref_common_prices, tmp_path):
    prices = pd.concat([cointegrated_prices, pref_common_prices], axis=1)
    cfg = Config()
    pairs = [
        {"ticker_a": "005930", "ticker_b": "005935", "relationship_type": "pref_common",
         "source": "seed", "name_a": "삼성전자", "name_b": "삼성전자우", "rationale": "보통/우선"},
        {"ticker_a": "AAA", "ticker_b": "BBB", "relationship_type": "statistical",
         "source": "statistical", "correlation": 0.9, "coint_pvalue": 0.01},
    ]
    analyses = []
    for p in pairs:
        a = analyze_pair(p, prices, cfg)
        a["category"] = "structural" if p["relationship_type"] == "pref_common" else "statistical"
        a["is_bluechip"] = True
        analyses.append(a)
    out = generate_report(analyses, cfg, watchlist={"title": "T", "source": "S"},
                          generated_at="2026-06-22", out_path=tmp_path / "r.html")
    h = out.read_text(encoding="utf-8")
    assert 'data-tab="structural"' in h        # 탭
    assert 'id="bluechipOnly"' in h            # 대형주 필터
    assert 'id="minZ"' in h                    # 최소 z 필터
    assert 'data-cat="structural"' in h        # 카드 카테고리 속성
    assert "대형 우량주" in h                    # 우량주 배지
    assert "지금 읽는 법" in h                   # 시그널 라인
    assert "스코어란?" in h                      # 스코어 설명
    assert 'value="z" selected' in h           # 기본 정렬 = |z|


def test_pinned_section_always_on_top(cointegrated_prices, pref_common_prices, tmp_path):
    """핀(pinned) 페어는 #cards 가 아니라 별도 고정 영역에 렌더된다."""
    prices = pd.concat([cointegrated_prices, pref_common_prices], axis=1)
    cfg = Config()
    pinned = analyze_pair(
        {"ticker_a": "005930", "ticker_b": "005935", "relationship_type": "holdco_sub",
         "source": "seed", "name_a": "지주", "name_b": "자회사", "pinned": True,
         "stake_pct": 1.0}, prices, cfg)
    normal = analyze_pair(
        {"ticker_a": "AAA", "ticker_b": "BBB", "relationship_type": "statistical",
         "source": "statistical", "correlation": 0.9, "coint_pvalue": 0.01}, prices, cfg)
    out = generate_report([pinned, normal], cfg, watchlist={"title": "T", "source": "S"},
                          generated_at="2026-06-23", out_path=tmp_path / "p.html")
    h = out.read_text(encoding="utf-8")
    assert "pinned-section" in h
    # 고정 영역은 추천 페어 헤딩(#cards)보다 먼저 등장
    assert h.index("pinned-section") < h.index('id="cards"')
