"""도메인 시드 페어 로딩/검증 (domain-curator 산출물 사용).

seed_pairs.json 스키마:
    ticker_a, name_a, ticker_b, name_b, relationship_type,
    mechanism, stake_pct?, net_debt?, notes
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import PROJECT_ROOT

VALID_RELATIONSHIPS = {"pref_common", "holdco_sub", "group_chain", "industry_peer"}

DEFAULT_SEED_PATH = PROJECT_ROOT / "data" / "seed_pairs.json"


def load_seed_pairs(path: str | Path | None = None) -> list[dict[str, Any]]:
    """시드 페어 JSON 을 로드하고 스키마를 검증한다.

    검증 실패 항목(필수 필드 누락, 잘못된 relationship_type, placeholder)은
    제외한다. 구조적 관계는 변할 수 있으므로 검증 안 된 항목은 버린다.

    Args:
        path: 시드 JSON 경로. None 이면 data/seed_pairs.json.

    Returns:
        검증을 통과한 시드 페어 dict 리스트.
    """
    p = Path(path) if path else DEFAULT_SEED_PATH
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    valid: list[dict[str, Any]] = []
    for item in raw:
        if not _is_valid_seed(item):
            continue
        item.setdefault("stake_pct", None)
        item.setdefault("net_debt", None)
        item.setdefault("notes", "")
        item.setdefault("rationale", "")
        item.setdefault("theme", "")
        item.setdefault("pinned", False)
        valid.append(item)
    return valid


def _is_valid_seed(item: dict[str, Any]) -> bool:
    """시드 항목 스키마 검증 (순수 함수)."""
    required = {"ticker_a", "ticker_b", "relationship_type"}
    if not required.issubset(item):
        return False
    if item["relationship_type"] not in VALID_RELATIONSHIPS:
        return False
    # placeholder / 미사용 항목 배제
    if "placeholder" in str(item.get("mechanism", "")).lower():
        return False
    if str(item.get("name_b", "")).startswith("(예시"):
        return False
    if item["ticker_a"] == item["ticker_b"]:
        return False
    return True


def seed_lookup(seeds: list[dict[str, Any]]) -> dict[frozenset[str], dict[str, Any]]:
    """티커 쌍(순서무관) -> 시드 메타 매핑 (통계 발굴 쌍 태깅용).

    Args:
        seeds: 검증된 시드 리스트.

    Returns:
        frozenset({ticker_a, ticker_b}) -> 시드 dict.
    """
    return {frozenset({s["ticker_a"], s["ticker_b"]}): s for s in seeds}
