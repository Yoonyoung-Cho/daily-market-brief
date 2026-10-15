"""신규 기능: 통화 표기·분석가 해석·워치리스트·HTML 리포트."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.analysis.divergence import analyze_pair
from src.analysis.narrative import build_narrative
from src.config import Config
from src.data.collector import load_watchlist, watchlist_names, watchlist_tickers
from src.viz.charts import actual_price_chart
from src.viz.report import generate_report


def test_currency_format_kr_us():
    kr = Config(market="KR")
    us = Config(market="US")
    assert kr.format_price(70000) == "70,000원"
    assert kr.currency.code == "KRW"
    assert us.format_price(123.456) == "$123.46"
    assert us.currency.code == "USD"


def test_build_narrative_has_all_parts(pref_common_prices):
    pair = {
        "ticker_a": "005930", "ticker_b": "005935",
        "relationship_type": "pref_common", "source": "seed",
        "correlation": 0.95, "coint_pvalue": 0.01, "half_life": 20.0,
        "name_a": "삼성전자", "name_b": "삼성전자우",
        "rationale": "같은 회사의 보통주/우선주",
    }
    res = analyze_pair(pair, pref_common_prices, Config())
    nar = res["narrative"]
    assert set(nar) == {"headline", "what", "why", "caveat", "signal"}
    assert "매매 신호" in nar["caveat"]  # 투자 권유 아님 명시
    assert "매매 신호" in nar["signal"]  # 지금 읽는 법에도 명시
    assert all(len(v) > 0 for v in nar.values())


def test_narrative_insufficient_data():
    nar = build_narrative({"relationship_type": "statistical", "current_metric": None,
                           "current_zscore": float("nan")})
    assert "보류" in nar["headline"] or "짧아" in nar["what"]


def test_actual_price_chart_currency(pref_common_prices):
    pair = {"ticker_a": "005930", "ticker_b": "005935",
            "relationship_type": "pref_common", "source": "seed",
            "name_a": "삼성전자", "name_b": "삼성전자우"}
    res = analyze_pair(pair, pref_common_prices, Config())
    fig = actual_price_chart(res)
    # 이중 y축 + 원화 접미 표기
    assert fig.layout.yaxis2 is not None
    assert fig.layout.yaxis.ticksuffix == "원"


def test_watchlist_loading():
    cfg = Config()
    wl = load_watchlist(cfg)
    assert wl.get("name") == "HOT_THEMES_KR"
    assert len(watchlist_tickers(cfg)) >= 8
    names = watchlist_names(cfg)
    assert names.get("005930") == "삼성전자"


def test_generate_report_writes_html(cointegrated_prices, pref_common_prices, tmp_path):
    prices = pd.concat([cointegrated_prices, pref_common_prices], axis=1)
    cfg = Config()
    pairs = [
        {"ticker_a": "AAA", "ticker_b": "BBB", "relationship_type": "statistical",
         "source": "statistical", "correlation": 0.9, "coint_pvalue": 0.01},
        {"ticker_a": "005930", "ticker_b": "005935", "relationship_type": "pref_common",
         "source": "seed", "name_a": "삼성전자", "name_b": "삼성전자우",
         "rationale": "보통주/우선주"},
    ]
    analyses = [analyze_pair(p, prices, cfg) for p in pairs]
    out = generate_report(analyses, cfg,
                          watchlist={"title": "테스트", "source": "합성"},
                          generated_at="2026-06-22 16:10",
                          out_path=tmp_path / "report.html")
    assert out.exists()
    htmltext = out.read_text(encoding="utf-8")
    # 자기완결성·핵심 요소 확인
    assert "Plotly" in htmltext            # plotly.js 인라인
    assert "투자 자문이 아닙니다" in htmltext   # 디스클레이머
    assert "이게 뭔가요" in htmltext           # 교육 섹션
    assert "삼성전자" in htmltext              # 종목명
    assert "왜 비교하나" in htmltext           # rationale 표기
