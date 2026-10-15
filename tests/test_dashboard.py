"""마켓 브리핑 대시보드 모듈 테스트 (네트워크 없이)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.brief import empty_briefing, validate_briefing
from src.config import Config
from src.data.consensus import (
    parse_consensus_html,
    summarize_by_category,
    top_covered_tickers,
)
from src.data.market import build_quotes, build_snapshot
from src.viz.dashboard import generate_dashboard

_SAMPLE_HTML = """
<table><tbody>
<tr><th>날짜</th><th>분류</th><th>제목</th><th>작성자</th><th>제공출처</th></tr>
<tr><td>2026-06-23</td><td>기업</td><td><a href="/analysis/downpdf?report_idx=650214">이오테크닉스(039030) 공정 다변화</a></td><td>박성순</td><td>대신증권</td></tr>
<tr><td>2026-06-23</td><td>산업</td><td><a href="/analysis/downpdf?report_idx=650201">조선 업황 점검 LNG 발주 확대</a></td><td>김선호</td><td>미래에셋증권</td></tr>
<tr><td>2026-06-23</td><td>기업</td><td>이오테크닉스(039030) HBM 수혜</td><td>이나연</td><td>삼성증권</td></tr>
<tr><td>잘못된행</td><td>x</td><td>스킵되어야</td></tr>
</tbody></table>
"""


def test_parse_consensus_html():
    rows = parse_consensus_html(_SAMPLE_HTML)
    assert len(rows) == 3  # 헤더·잘못된 행 제외
    eo = [r for r in rows if r["ticker"] == "039030"]
    assert len(eo) == 2
    assert rows[0]["category"] == "기업"
    assert rows[0]["broker"] == "대신증권"


def test_consensus_captures_report_idx():
    rows = parse_consensus_html(_SAMPLE_HTML)
    eo = [r for r in rows if r["ticker"] == "039030" and r["report_idx"]]
    assert eo and eo[0]["report_idx"] == "650214"
    assert eo[0]["pdf_url"].endswith("report_idx=650214")


def test_select_reports_priority():
    from src.data.reports import select_reports
    rows = parse_consensus_html(_SAMPLE_HTML)
    sel = select_reports(rows, watchlist_tickers={"039030"}, top=5)
    # report_idx 없는 리포트(삼성증권 행)는 제외, 산업 리포트 우선
    assert all(r.get("report_idx") for r in sel)
    assert sel[0]["category"] == "산업"  # 산업 리포트가 1순위


def test_consensus_aggregates():
    rows = parse_consensus_html(_SAMPLE_HTML)
    cats = summarize_by_category(rows)
    assert cats["기업"] == 2 and cats["산업"] == 1
    tops = top_covered_tickers(rows)
    assert tops[0]["ticker"] == "039030" and tops[0]["count"] == 2
    assert "대신증권" in tops[0]["brokers"]


def test_market_build_snapshot():
    listing = pd.DataFrame({
        "Code": ["005930", "000660", "111111"],
        "Name": ["삼성전자", "SK하이닉스", "잡주"],
        "Close": [70000, 200000, 500],
        "ChagesRatio": [1.5, -2.0, 29.0],
        "Marcap": [4e14, 1.5e14, 1e10],  # 잡주는 min_marcap 미달
    })
    indices = {"KOSPI": {"close": 3000.0, "change_pct": 0.8}}
    listing["Market"] = "KOSPI"
    snap = build_snapshot(listing, indices, top_n=5, min_marcap=5e11)
    # 잡주(작은 시총)는 등락 상위에서 제외
    g_tickers = {r["ticker"] for r in snap["top_gainers"]}
    assert "111111" not in g_tickers
    assert snap["indices"]["KOSPI"]["change_pct"] == 0.8
    assert snap["top_marcap"][0]["ticker"] == "005930"
    # 지수 기여도: 시총 큰 SK하이닉스(-2%×1.5e14)가 잡주(+29%×1e10)보다 더 끌어내림
    down = snap["index_drivers"]["down"]
    assert down[0]["ticker"] == "000660"  # %낙폭 작아도 시총 커서 지수 1위 드라이버
    assert "111111" not in {r["ticker"] for r in down}


def test_validate_briefing_requires_sources():
    brief = empty_briefing("KR", "2026-06-23")
    brief["hot_sectors"] = [
        {"sector": "조선", "trend": "호조", "tier": "ib_news",
         "source_url": "https://x.com/a", "source_name": "CNBC"},
        {"sector": "방산", "trend": "수출", "tier": "ib_news",
         "source_url": "", "source_name": ""},  # 출처 없음
    ]
    chk = validate_briefing(brief)
    assert chk["n_items"] == 2
    assert chk["n_unsourced"] == 1
    assert chk["ok"] is False


def test_validate_briefing_ok():
    brief = empty_briefing("KR", "2026-06-23")
    brief["broker_views"] = [
        {"firm": "Goldman", "view": "비중확대", "tier": "ib_news",
         "source_url": "https://goldmansachs.com/x"},
    ]
    chk = validate_briefing(brief)
    assert chk["ok"] is True and chk["n_unsourced"] == 0


def test_generate_dashboard_smoke(tmp_path):
    from src.config import FeaturesConfig
    cfg = Config()
    object.__setattr__(cfg, "features", FeaturesConfig(pairs=True, us=True))  # 페어 옵션 켬
    brief = empty_briefing("KR", "2026-06-23")
    brief["market_tone"] = "반도체 강세."
    brief["hot_sectors"] = [{"sector": "조선", "trend": "수주 호조", "tier": "ib_news",
                             "source_url": "https://cnbc.com/x", "source_name": "CNBC"}]
    report_views = {
        "as_of": "2026-06-23",
        "trends": {
            "today": {"n_reports": 2, "categories": [{"category": "기업", "count": 2}],
                      "stocks": [{"ticker": "039030", "name": "이오테크닉스", "count": 2,
                                  "close": 460000.0, "change_pct": 1.2,
                                  "reports": [{"broker": "한국IR협의회", "title": "공정 다변화",
                                               "opinion": None, "concern_excerpt": "",
                                               "pdf_url": "https://consensus.hankyung.com/x",
                                               "date": "2026-06-23"}]}],
                      "industry_reports": []},
            "yesterday": {"n_reports": 0, "categories": [], "stocks": [], "industry_reports": []},
            "7d": {"n_reports": 2, "categories": [], "stocks": [], "industry_reports": []},
            "30d": {"n_reports": 2, "categories": [], "stocks": [], "industry_reports": []},
        },
        "index": [{"title": "이오테크닉스 공정 다변화", "name": "이오테크닉스",
                   "ticker": "039030", "broker": "한국IR협의회", "date": "2026-06-23",
                   "category": "기업", "opinion": None, "target_price": None,
                   "has_concern": False, "pdf_url": "https://consensus.hankyung.com/x"}],
    }
    market = build_snapshot(
        pd.DataFrame({"Code": ["005930"], "Name": ["삼성전자"], "Close": [70000],
                      "ChagesRatio": [1.0], "Marcap": [4e14]}),
        {"KOSPI": {"close": 3000.0, "change_pct": 0.8}})
    consensus = {"source_url": "https://consensus.hankyung.com/", "fetched_n": 3,
                 "by_category": {"기업": 2, "산업": 1}, "top_tickers": []}
    pairs = [{"status": "ok", "ticker_a": "005930", "ticker_b": "000660",
              "name_a": "삼성전자", "name_b": "SK하이닉스", "current_zscore": -2.4,
              "score": 0.9, "theme": "반도체", "narrative": {"signal": "🔴 크게 벌어짐"}}]
    out = generate_dashboard(cfg, briefing=brief, market_snapshot=market,
                             consensus=consensus, pairs=pairs, report_views=report_views,
                             generated_at="2026-06-23 08:00", out_path=tmp_path / "d.html")
    h = out.read_text(encoding="utf-8")
    assert 'data-m="KR"' in h and 'data-m="US"' in h        # 시장 탭
    assert "오늘의 한눈에" in h and "조선" in h               # 브리핑
    assert "페어 분석" in h and "삼성전자" in h               # 페어 탭
    assert "투자 자문이 아닙니다" in h                         # 디스클레이머
    assert 'id="panel-US"' in h                                # US 패널 존재
    assert 'data-m="US"' in h                                  # US 탭
    # 기간별 리포트 동향(종목 중심)
    assert "기간별 리포트 동향" in h
    assert 'data-win="today"' in h and 'data-win="30d"' in h  # 기간 탭
    assert "많이 다뤄진 종목" in h                              # 종목 중심
    assert "이오테크닉스" in h and "460,000원" in h            # 종목 + 현재가
    assert "리포트 2건" in h                                    # 종목별 리포트 수
    assert "repSearch" in h                                     # 종목 검색


def test_build_quotes():
    listing = pd.DataFrame({
        "Code": ["000660", "005930"], "Name": ["SK하이닉스", "삼성전자"],
        "Close": [200000, 70000], "ChagesRatio": [-2.5, 1.0], "Marcap": [1.5e14, 4e14]})
    q = build_quotes(listing, ["000660", "999999"])
    assert q["000660"]["close"] == 200000.0
    assert q["000660"]["change_pct"] == -2.5
    assert "999999" not in q  # 없는 종목은 제외
