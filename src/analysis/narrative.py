"""분석가 해석(equity-analyst) — 통계를 비전문가용 코멘트로 번역.

방법론: .claude/skills/equity-narrative/SKILL.md
순수 함수. analyze_pair 결과 dict 를 받아 headline/what/why/caveat 를 만든다.
예측·단정은 하지 않는다(통계적 사실 + 가능한 해석 + 한계만).
"""
from __future__ import annotations

import math
from typing import Any

_REL_KR = {
    "pref_common": "보통주-우선주",
    "holdco_sub": "지주사-자회사",
    "group_chain": "그룹·밸류체인",
    "industry_peer": "동일 산업",
    "statistical": "통계 발굴",
}

_WHY_TEMPLATE = {
    "pref_common": (
        "같은 회사의 보통주와 우선주라 본질 가치를 공유합니다. 보통은 둘의 "
        "가격차(우선주 할인율)가 일정한 범위에서 움직이므로, 그 폭이 평소와 "
        "달라지면 주목합니다."
    ),
    "holdco_sub": (
        "지주사와 자회사는 지분으로 묶여 있어, 자회사의 가치가 지주사 가치에 "
        "반영됩니다. 둘 사이 괴리(NAV 디스카운트)가 평소보다 깊거나 얕아지는지를 봅니다."
    ),
    "group_chain": (
        "두 회사는 같은 그룹이거나 공급망(밸류체인)으로 사업이 맞물려 비슷한 "
        "업황 사이클을 공유합니다. 그래서 가격이 함께 움직이는 경향이 있습니다."
    ),
    "industry_peer": (
        "두 회사는 같은 산업에 속해 업황(수요·가격 사이클)을 공유합니다. "
        "그래서 historically 비슷하게 움직였고, 그 관계가 흔들리는 순간을 봅니다."
    ),
    "statistical": (
        "경제적 인과를 단정할 수는 없지만, 과거 데이터에서 두 종목이 통계적으로 "
        "강하게 같이 움직였고 공적분 검정(장기 균형 관계 통계)을 통과했습니다."
    ),
}


def _josa(word: str, pair: tuple[str, str]) -> str:
    """한글 받침 유무로 조사를 고른다.

    Args:
        word: 앞 단어.
        pair: (받침 있을 때, 받침 없을 때) 예: ('이','가'), ('은','는').

    Returns:
        알맞은 조사.
    """
    if not word:
        return pair[1]
    last = word[-1]
    if "가" <= last <= "힣":
        has_batchim = (ord(last) - 0xAC00) % 28 != 0
        return pair[0] if has_batchim else pair[1]
    return pair[1]


def _rarity_phrase(z: float) -> str:
    """|z-score| 를 '얼마나 드문 일인지' 일상어로."""
    a = abs(z)
    if a >= 2:
        return "최근 기준으로 매우 드문 수준"
    if a >= 1:
        return "평소 범위를 다소 벗어난 수준"
    return "대체로 평소 범위 안"


def _pct_phrase(pct: float) -> str:
    """역사적 백분위를 '2년 전체 중 어느 위치인지'로 (상/하위 일관 표기)."""
    if math.isnan(pct):
        return "전체 분포 위치는 산출 불가"
    if pct >= 99.5:
        return "최근 2년 중 가장 높은 축(상위 1% 이내)"
    if pct <= 0.5:
        return "최근 2년 중 가장 낮은 축(하위 1% 이내)"
    if pct >= 50:
        return f"최근 2년 중 상위 {100 - pct:.0f}%"
    return f"최근 2년 중 하위 {pct:.0f}%"


def _metric_str(label: str, value: float) -> str:
    """지표 값을 표기(할인율/디스카운트는 %, 스프레드는 소수)."""
    if "할인율" in label or "디스카운트" in label:
        return f"{value * 100:.1f}%"
    return f"{value:.4f}"


def _signal_reading(analysis: dict[str, Any]) -> str:
    """'지금 읽는 법' — 주목도(|z| 구간) + 어느 쪽이 상대적으로 싼/비싼지 + 한계.

    매매 신호가 아니라 '상대적 위치'에 대한 통계적 관찰임을 명시한다.
    """
    rel = analysis.get("relationship_type", "statistical")
    z = analysis.get("current_zscore")
    a = analysis.get("name_a", analysis.get("ticker_a", "A"))
    b = analysis.get("name_b", analysis.get("ticker_b", "B"))
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return "데이터가 짧아 방향 판단 보류. 매매 신호가 아닙니다."

    az = abs(z)
    zone = ("🔴 크게 벌어짐(주목)" if az >= 2
            else "🟠 다소 벌어짐" if az >= 1
            else "🔵 평소 범위")

    if rel == "pref_common":
        direction = (f"우선주({b})가 보통주({a}) 대비 상대적으로 더 싸진 상태(할인율 확대)"
                     if z > 0 else
                     f"우선주({b}) 할인율이 줄어 상대적으로 비싸진 상태")
    elif rel == "holdco_sub":
        direction = (f"지주사({a})가 자회사({b}) 가치 대비 더 싸진 상태(NAV 디스카운트 확대)"
                     if z > 0 else
                     f"지주사({a})의 디스카운트가 줄어 상대적으로 비싸진 상태")
    else:
        direction = (f"{a}가 {b} 대비 상대적으로 비싼 편"
                     if z > 0 else
                     f"{a}가 {b} 대비 상대적으로 싼 편")

    return f"{zone} · {direction}. 되돌아온다는 보장은 없으며, 매매 신호가 아닙니다."


def build_narrative(analysis: dict[str, Any]) -> dict[str, str]:
    """analyze_pair 결과로부터 분석가 해석 dict 를 만든다.

    Args:
        analysis: analyze_pair 결과 (status='ok' 기대).

    Returns:
        {'headline','what','why','caveat'} dict.
    """
    rel = analysis.get("relationship_type", "statistical")
    label = analysis.get("label", "괴리 지표")
    name_a = analysis.get("name_a", analysis.get("ticker_a", "A"))
    name_b = analysis.get("name_b", analysis.get("ticker_b", "B"))
    z = analysis.get("current_zscore", float("nan"))
    pct = analysis.get("percentile", float("nan"))
    hl = analysis.get("half_life")
    cur_v = analysis.get("current_metric")
    mean_v = analysis.get("mean_metric")

    if cur_v is None or (isinstance(z, float) and math.isnan(z)):
        return {
            "headline": "데이터가 짧아 판단을 보류합니다.",
            "what": "표준화(z-score)에 필요한 과거 데이터가 부족해 '평소 대비' 비교가 어렵습니다.",
            "why": _WHY_TEMPLATE.get(rel, _WHY_TEMPLATE["statistical"]),
            "caveat": "더 긴 기간의 데이터가 쌓이면 다시 평가할 수 있습니다. 이는 매매 신호가 아닙니다.",
            "signal": _signal_reading(analysis),
        }

    direction = "벌어진" if z > 0 else "좁혀진"
    rarity = _rarity_phrase(z)
    pct_phrase = _pct_phrase(pct)

    headline = (
        f"{label}{_josa(label, ('이', '가'))} 최근 평균보다 {direction} 상태입니다 ({rarity})."
    )

    what = (
        f"현재 {label}{_josa(label, ('은', '는'))} {_metric_str(label, cur_v)}로, 최근 평균 "
        f"{_metric_str(label, mean_v)} 대비 {'높습니다' if z > 0 else '낮습니다'}. "
        f"통계적으로는 z-score {z:+.2f}입니다. z-score는 '최근 평소 대비 몇 표준편차나 "
        f"벗어났는지'를 뜻하며, ±1 안이면 평범, ±2 밖이면 드문 일입니다(지금은 {rarity}). "
        f"한편 2년 전체 분포로 보면 {pct_phrase}에 위치합니다 "
        f"— 최근 흐름과 장기 위치는 다를 수 있습니다."
    )

    why = _WHY_TEMPLATE.get(rel, _WHY_TEMPLATE["statistical"])
    if analysis.get("rationale"):
        why = f"{analysis['rationale']} ({_REL_KR.get(rel, rel)} 관계)"

    if hl is None:
        hl_txt = (
            "과거 데이터에서는 이 괴리가 평균으로 되돌아오는 경향이 뚜렷하지 않았습니다"
            "(평균회귀가 약함). 즉 벌어진 차이가 자동으로 좁혀진다는 보장은 없습니다."
        )
    else:
        hl_txt = (
            f"과거 기준 이 괴리가 평소 수준의 절반으로 돌아오는 데 통상 약 "
            f"{hl:.0f}거래일이 걸렸습니다(평균회귀 반감기). 다만 과거 패턴이지 미래 보장은 아닙니다."
        )

    caveat = (
        f"{hl_txt} 합병·정책 변화 등으로 두 종목의 관계 자체가 바뀌면 이 분석은 "
        f"무효가 될 수 있습니다. 본 해석은 통계적 상태 설명일 뿐 매매 신호가 아닙니다."
    )

    return {"headline": headline, "what": what, "why": why, "caveat": caveat,
            "signal": _signal_reading(analysis)}
