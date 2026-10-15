"""데일리 브리핑(초심자 섹션·아카이브·잡주 필터) 테스트 — 네트워크 없이."""
from __future__ import annotations

import json

from src.brief import (
    dated_briefing_path,
    empty_briefing,
    filter_unsourced,
    save_briefing,
    validate_briefing,
)
from src.config import Config, DigestConfig, FeaturesConfig, load_config
from src.dashboard_pipeline import drop_small_caps, list_history_dates, snapshot_dashboard
from src.viz.dashboard import generate_dashboard


def _cfg(tmp_path) -> Config:
    cfg = Config()
    object.__setattr__(cfg.cache, "dir", str(tmp_path))
    return cfg


def test_config_has_digest_and_features():
    cfg = load_config()
    assert isinstance(cfg.digest, DigestConfig) and cfg.digest.backfill_days >= 1
    assert isinstance(cfg.features, FeaturesConfig)
    assert cfg.digest.min_marcap_krw > 0


def test_plain_summary_must_be_three_sentences():
    b = empty_briefing("KR", "2026-09-22")
    b["plain_summary"] = ["하나", "둘"]
    assert validate_briefing(b)["ok"] is False
    b["plain_summary"] = ["하나", "둘", "셋"]
    assert validate_briefing(b)["ok"] is True


def test_news_requires_source_and_filter_unsourced():
    b = empty_briefing("KR", "2026-09-22")
    b["news"] = [
        {"title": "A", "summary_plain": "a", "why_it_matters": "x", "tier": "news",
         "source_url": "https://n.example/a", "source_name": "연합"},
        {"title": "B", "summary_plain": "b", "why_it_matters": "y", "tier": "news",
         "source_url": "", "source_name": ""},
    ]
    chk = validate_briefing(b)
    assert chk["n_unsourced"] == 1
    clean = filter_unsourced(b)
    assert [n["title"] for n in clean["news"]] == ["A"]
    assert len(b["news"]) == 2  # 원본은 불변


def test_save_briefing_writes_dated_copy(tmp_path):
    cfg = _cfg(tmp_path)
    b = empty_briefing("KR", "2026-09-22")
    b["plain_summary"] = ["1", "2", "3"]
    save_briefing(cfg, b)
    dated = dated_briefing_path(cfg, "KR", "2026-09-22")
    assert dated.exists()
    assert json.loads(dated.read_text(encoding="utf-8"))["plain_summary"] == ["1", "2", "3"]


def test_drop_small_caps_removes_junk():
    b = empty_briefing("KR", "2026-09-22")
    b["notable_stocks"] = [
        {"name": "대형", "ticker": "005930", "marcap": 4e14, "note": "", "tier": "consensus",
         "source_url": "https://x", "source_name": "x"},
        {"name": "잡주", "ticker": "111111", "marcap": 5e10, "note": "", "tier": "news",
         "source_url": "https://x", "source_name": "x"},
        {"name": "시세없음", "ticker": "222222", "note": "", "tier": "news",
         "source_url": "https://x", "source_name": "x"},  # 시총 미부착은 유지
    ]
    removed = drop_small_caps(b, 1e12)
    assert removed == ["잡주"]
    assert [s["name"] for s in b["notable_stocks"]] == ["대형", "시세없음"]


def test_dashboard_beginner_sections_and_history(tmp_path):
    cfg = _cfg(tmp_path)
    b = empty_briefing("KR", "2026-09-22")
    b["plain_summary"] = ["코스피가 내렸습니다.", "리포트는 조선에 몰렸습니다.", "⚠️ 금리 결정 주간입니다."]
    b["news"] = [{"title": "삼성전자 실적", "summary_plain": "실적을 알렸습니다.",
                  "why_it_matters": "가장 큰 회사입니다.", "tickers": ["005930"],
                  "date": "2026-09-22", "tier": "news",
                  "source_url": "https://news.example/1", "source_name": "연합뉴스"}]
    b["glossary"] = [{"term": "시총", "meaning": "주가 × 주식 수"}]
    out = generate_dashboard(cfg, briefing=b, market_snapshot=None, consensus=None, pairs=[],
                             generated_at="2026-09-22 08:30", out_path=tmp_path / "d.html",
                             history_dates=["2026-09-22", "2026-09-19"], history_dir="history")
    h = out.read_text(encoding="utf-8")
    assert "초심자 3줄 요약" in h and "코스피가 내렸습니다." in h
    assert "오늘의 뉴스" in h and "왜 중요?" in h and "가장 큰 회사입니다." in h
    assert "오늘의 용어" in h and "주가 × 주식 수" in h
    assert 'href="history/2026-09-19.html"' in h          # 지난 브리핑 링크
    assert "페어 분석" not in h                             # features.pairs=False 기본
    assert "투자 자문이 아닙니다" in h


def test_dashboard_pairs_flag_shows_section(tmp_path):
    cfg = _cfg(tmp_path)
    object.__setattr__(cfg, "features", FeaturesConfig(pairs=True, us=False))
    pairs = [{"status": "ok", "ticker_a": "005930", "ticker_b": "000660",
              "name_a": "삼성전자", "name_b": "SK하이닉스", "current_zscore": -2.4,
              "score": 0.9, "theme": "반도체", "narrative": {"signal": "벌어짐"}}]
    out = generate_dashboard(cfg, briefing=None, market_snapshot=None, consensus=None,
                             pairs=pairs, generated_at="2026-09-22 08:30",
                             out_path=tmp_path / "d.html")
    h = out.read_text(encoding="utf-8")
    assert "페어 분석" in h and 'data-m="US"' not in h


def test_snapshot_and_history_listing(tmp_path):
    cfg = _cfg(tmp_path)
    dash = tmp_path / "dashboard.html"
    dash.write_text('<a href="history/2026-09-19.html">x</a>', encoding="utf-8")
    snap = snapshot_dashboard(cfg, dash, "2026-09-22")
    assert snap.name == "2026-09-22.html" and snap.parent == cfg.history_dir
    (cfg.history_dir / "2026-09-19.html").write_text("", encoding="utf-8")
    (cfg.history_dir / "notes.txt").write_text("", encoding="utf-8")
    assert list_history_dates(cfg) == ["2026-09-22", "2026-09-19"]
