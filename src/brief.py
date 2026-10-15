"""데일리 브리핑 데이터 계약 + 신뢰성 검증 (순수 함수).

`brief-writer` 가 채우고 `fact-checker` 가 검증하는 JSON 구조를 정의.
모든 항목은 출처(source_url)를 가져야 하며, 검증이 이를 강제한다(환각 차단).
브리핑은 최신본(`briefing_{kr,us}.json`)과 날짜별 사본(`briefs/{kr,us}/YYYY-MM-DD.json`)
두 곳에 저장돼 언제 들어와도 과거 브리핑을 볼 수 있다.

CLI:
    python -m src.brief validate          # KR·US 브리핑 기계 검증(JSON 출력)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import Config

# 소스 신뢰도 티어
TIER_LABELS = {
    "consensus": "한경 컨센서스 리포트",
    "market_data": "시장 데이터",
    "analyst_data": "애널리스트 데이터(yfinance)",
    "ib_news": "IB 뷰(뉴스 보도)",
    "news": "뉴스 보도",
    "llm": "LLM 종합(검증 대상)",
}
_VALID_TIERS = set(TIER_LABELS)

# brief-writer 가 산출할 JSON 스키마
BRIEFING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["market", "as_of_date", "market_tone", "hot_sectors",
                 "notable_stocks", "broker_views"],
    "properties": {
        "market": {"type": "string", "enum": ["KR", "US"]},
        "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
        "plain_summary": {
            "type": "array",
            "description": "초심자용 3문장 요약(지수 / 리포트·섹터 / 주의점)",
            "items": {"type": "string"},
        },
        "market_tone": {"type": "string", "description": "지수·시장 분위기 한 문단"},
        "news": {
            "type": "array",
            "description": "오늘 화제가 된 뉴스(무슨 일 + 왜 중요한가)",
            "items": {
                "type": "object",
                "required": ["title", "summary_plain", "why_it_matters", "tier",
                             "source_url", "source_name"],
                "properties": {
                    "title": {"type": "string"},
                    "summary_plain": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "date": {"type": "string"},
                    "tier": {"type": "string", "enum": list(_VALID_TIERS)},
                    "source_url": {"type": "string"},
                    "source_name": {"type": "string"},
                },
            },
        },
        "glossary": {
            "type": "array",
            "description": "본문에 등장한 용어 한 줄 풀이",
            "items": {
                "type": "object",
                "required": ["term", "meaning"],
                "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
            },
        },
        "hot_sectors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["sector", "trend", "tier", "source_url", "source_name"],
                "properties": {
                    "sector": {"type": "string"},
                    "trend": {"type": "string"},
                    "drivers": {"type": "string"},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "tier": {"type": "string", "enum": list(_VALID_TIERS)},
                    "source_url": {"type": "string"},
                    "source_name": {"type": "string"},
                },
            },
        },
        "notable_stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "note", "tier", "source_url", "source_name"],
                "properties": {
                    "name": {"type": "string"},
                    "ticker": {"type": "string"},
                    "note": {"type": "string"},
                    "tier": {"type": "string", "enum": list(_VALID_TIERS)},
                    "source_url": {"type": "string"},
                    "source_name": {"type": "string"},
                },
            },
        },
        "broker_views": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["firm", "view", "tier", "source_url"],
                "properties": {
                    "firm": {"type": "string"},
                    "view": {"type": "string"},
                    "date": {"type": "string"},
                    "tier": {"type": "string", "enum": list(_VALID_TIERS)},
                    "source_url": {"type": "string"},
                },
            },
        },
        "key_reports": {
            "type": "array",
            "description": "당일 증권사 리포트(PDF 본문 기반) 핵심 요약",
            "items": {
                "type": "object",
                "required": ["title", "broker", "summary", "tier", "source_url"],
                "properties": {
                    "title": {"type": "string"},
                    "broker": {"type": "string"},
                    "ticker": {"type": "string"},
                    "opinion": {"type": "string", "description": "투자의견(본문에 있으면)"},
                    "target_price": {"type": "string", "description": "목표주가(본문에 있으면)"},
                    "summary": {"type": "string", "description": "리포트 본문 핵심 1~2줄"},
                    "tier": {"type": "string", "enum": list(_VALID_TIERS)},
                    "source_url": {"type": "string", "description": "리포트 PDF URL"},
                },
            },
        },
    },
}

_SOURCED_SECTIONS = ("hot_sectors", "notable_stocks", "broker_views", "key_reports", "news")


def empty_briefing(market: str, as_of_date: str) -> dict[str, Any]:
    """빈 브리핑 골격."""
    return {
        "market": market,
        "as_of_date": as_of_date,
        "plain_summary": [],
        "market_tone": "",
        "news": [],
        "hot_sectors": [],
        "notable_stocks": [],
        "broker_views": [],
        "key_reports": [],
        "glossary": [],
    }


def validate_briefing(brief: dict[str, Any]) -> dict[str, Any]:
    """브리핑 신뢰성 검증 (순수 함수).

    검사: (1) 필수 키 존재, (2) 모든 항목에 source_url, (3) tier 유효성.

    Args:
        brief: 브리핑 dict.

    Returns:
        {ok, errors, n_items, n_unsourced} — fact-checker 가 사용.
    """
    errors: list[str] = []
    for key in ("market", "as_of_date", "market_tone"):
        if key not in brief:
            errors.append(f"필수 키 누락: {key}")

    n_items = 0
    n_unsourced = 0
    for section in _SOURCED_SECTIONS:
        for i, item in enumerate(brief.get(section, [])):
            n_items += 1
            url = str(item.get("source_url", "")).strip()
            if not url.startswith("http"):
                n_unsourced += 1
                errors.append(f"{section}[{i}] 출처 URL 없음/형식오류")
            tier = item.get("tier")
            if tier not in _VALID_TIERS:
                errors.append(f"{section}[{i}] tier 무효: {tier!r}")
    ps = brief.get("plain_summary")
    if ps and not (isinstance(ps, list) and len(ps) == 3):  # 비어 있으면 '미작성'으로 허용
        errors.append("plain_summary 는 정확히 3문장 리스트여야 함")
    return {
        "ok": n_unsourced == 0 and not errors,
        "errors": errors,
        "n_items": n_items,
        "n_unsourced": n_unsourced,
    }


def filter_unsourced(brief: dict[str, Any]) -> dict[str, Any]:
    """출처 URL 없는 항목을 제거한 사본을 반환한다 (순수 함수, 렌더 직전 안전장치)."""
    out = dict(brief)
    for section in _SOURCED_SECTIONS:
        out[section] = [it for it in brief.get(section, [])
                        if str(it.get("source_url", "")).startswith("http")]
    return out


def briefing_path(config: Config, market: str) -> Path:
    """브리핑 JSON 경로."""
    return config.cache_dir / f"briefing_{market.lower()}.json"


def load_briefing(config: Config, market: str = "KR") -> dict[str, Any] | None:
    """저장된 브리핑 로드. 없으면 None."""
    path = briefing_path(config, market)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dated_briefing_path(config: Config, market: str, as_of_date: str) -> Path:
    """날짜별 브리핑 사본 경로: data/briefs/{kr|us}/YYYY-MM-DD.json."""
    return config.cache_dir / "briefs" / market.lower() / f"{as_of_date}.json"


def save_briefing(config: Config, brief: dict[str, Any]) -> Path:
    """브리핑 저장 — 최신본 + 날짜별 사본(as_of_date 기준)."""
    market = brief.get("market", "KR")
    path = briefing_path(config, market)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(brief, fh, ensure_ascii=False, indent=2)
    as_of = str(brief.get("as_of_date") or "").strip()
    if as_of:
        dated = dated_briefing_path(config, market, as_of)
        dated.parent.mkdir(parents=True, exist_ok=True)
        with dated.open("w", encoding="utf-8") as fh:
            json.dump(brief, fh, ensure_ascii=False, indent=2)
    return path


def archive_briefings(config: Config) -> list[Path]:
    """최신본(briefing_*.json)을 날짜별 사본으로 복사한다(LLM 이 직접 파일을 쓴 경우 대비).

    Returns:
        생성·갱신된 날짜별 사본 경로.
    """
    out: list[Path] = []
    for market in ("KR", "US"):
        brief = load_briefing(config, market)
        if brief and brief.get("as_of_date"):
            out.append(save_briefing(config, brief))
    return out


def main() -> None:
    """CLI: python -m src.brief validate."""
    import argparse
    from src.config import load_config

    ap = argparse.ArgumentParser(description="브리핑 검증")
    ap.add_argument("cmd", choices=["validate", "archive"])
    args = ap.parse_args()
    cfg = load_config()
    if args.cmd == "validate":
        result = {}
        for market in ("KR", "US"):
            b = load_briefing(cfg, market)
            result[market] = validate_briefing(b) if b else {"ok": False, "errors": ["브리핑 없음"],
                                                              "n_items": 0, "n_unsourced": 0}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for p in archive_briefings(cfg):
            print(f"[brief] 아카이브 {p}")


if __name__ == "__main__":
    main()
