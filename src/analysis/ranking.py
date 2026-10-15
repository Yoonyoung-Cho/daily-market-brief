"""쌍 추천 랭킹 — 경제적 근거(시드) 가산 + 통계 품질 종합 스코어.

스코어 = 시드보너스 + 공적분 점수 + 상관 점수 + 반감기 점수 + 괴리(|z|) 점수
모든 구성요소는 0~1 로 정규화 후 가중합.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def _coint_score(p: float | None) -> float:
    """공적분 p-value -> 0~1 (낮을수록 높음)."""
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return 0.0
    return float(max(0.0, 1.0 - min(p, 1.0)))


def _corr_score(c: float | None) -> float:
    """상관계수 -> 0~1."""
    if c is None or (isinstance(c, float) and math.isnan(c)):
        return 0.0
    return float(max(0.0, min(abs(c), 1.0)))


def _halflife_score(hl: float | None) -> float:
    """반감기 -> 0~1 (짧을수록 높음). 5~120 거래일을 선호 구간으로."""
    if hl is None or (isinstance(hl, float) and (math.isnan(hl) or math.isinf(hl))):
        return 0.0
    # 1/(1+hl/30): 30일에서 0.5, 매우 짧으면 1 에 근접
    return float(1.0 / (1.0 + hl / 30.0))


def _zscore_score(z: float | None) -> float:
    """|z-score| -> 0~1 (현재 괴리가 클수록 주목도↑). z=3 에서 포화."""
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return 0.0
    return float(min(abs(z) / 3.0, 1.0))


_STRUCTURAL = {"pref_common", "holdco_sub"}


def score_pair(
    analysis: dict[str, Any],
    seed_bonus: float,
    structural_bonus: float = 0.20,
) -> float:
    """단일 분석 결과의 종합 스코어.

    경제적 근거가 강한 쌍을 위로 올린다: 시드 가산 + '누가봐도' 구조적
    (보통주-우선주/지주사-자회사) 가산 + 핀(pinned) 가산.

    Args:
        analysis: analyze_pair 결과 dict.
        seed_bonus: 시드 쌍 가산점.
        structural_bonus: 구조적 페어 가산점.

    Returns:
        0 이상의 스코어.
    """
    if analysis.get("status") != "ok":
        return 0.0
    bonus = seed_bonus if analysis.get("source") == "seed" else 0.0
    if analysis.get("relationship_type") in _STRUCTURAL:
        bonus += structural_bonus
    if analysis.get("pinned"):
        bonus += 0.5
    score = (
        bonus
        + 0.30 * _coint_score(analysis.get("coint_pvalue"))
        + 0.20 * _corr_score(analysis.get("correlation"))
        + 0.25 * _halflife_score(analysis.get("half_life"))
        + 0.25 * _zscore_score(analysis.get("current_zscore"))
    )
    return float(score)


def rank_pairs(
    analyses: list[dict[str, Any]],
    seed_bonus: float = 0.30,
    structural_bonus: float = 0.20,
) -> list[dict[str, Any]]:
    """분석 결과 리스트에 score 를 부여해 내림차순 정렬한다.

    Args:
        analyses: analyze_pair 결과 리스트.
        seed_bonus: 시드 가산점.
        structural_bonus: 구조적 페어 가산점.

    Returns:
        score 키가 추가되고 정렬된 새 리스트.
    """
    scored = []
    for a in analyses:
        item = dict(a)
        item["score"] = score_pair(a, seed_bonus, structural_bonus)
        scored.append(item)
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
