"""plotly 차트 — 정규화 가격, 괴리지표+밴드, z-score.

분석 결과 dict 의 'series' 를 입력으로 받는 순수 함수들.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go


def _currency_tickformat(currency: str) -> tuple[str, str, str]:
    """통화코드 -> (틱포맷, 접두, 접미). KRW=원 접미, USD=$ 접두."""
    if currency == "USD":
        return ",.2f", "$", ""
    return ",.0f", "", "원"


def actual_price_chart(analysis: dict[str, Any]) -> go.Figure:
    """두 종목의 실제 가격 추이(통화 단위). 스케일 차이가 크면 보조축 사용.

    정규화 차트가 '같이 움직이는가'를 본다면, 이 차트는 '실제 얼마인가'를 보여준다.

    Args:
        analysis: analyze_pair 결과.

    Returns:
        plotly Figure (이중 y축).
    """
    s = analysis["series"]
    dates = s["dates"]
    pa = np.array(s["price_a"], dtype=float)
    pb = np.array(s["price_b"], dtype=float)
    name_a = analysis.get("name_a", analysis["ticker_a"])
    name_b = analysis.get("name_b", analysis["ticker_b"])
    tickfmt, pre, suf = _currency_tickformat(analysis.get("currency", "KRW"))
    hover = f"{pre}%{{y:{tickfmt}}}{suf}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=pa, name=name_a, mode="lines",
                             yaxis="y", hovertemplate=hover))
    fig.add_trace(go.Scatter(x=dates, y=pb, name=name_b, mode="lines",
                             yaxis="y2", hovertemplate=hover))
    fig.update_layout(
        title="실제 가격 추이 (좌축=첫 종목, 우축=둘째 종목)",
        yaxis=dict(title=f"{name_a} 가격", tickformat=tickfmt,
                   tickprefix=pre, ticksuffix=suf),
        yaxis2=dict(title=f"{name_b} 가격", tickformat=tickfmt,
                    tickprefix=pre, ticksuffix=suf,
                    overlaying="y", side="right"),
        hovermode="x unified",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def normalized_price_chart(analysis: dict[str, Any]) -> go.Figure:
    """두 종목의 정규화(시작=100) 가격 추이.

    Args:
        analysis: analyze_pair 결과.

    Returns:
        plotly Figure.
    """
    s = analysis["series"]
    dates = s["dates"]
    pa = np.array(s["price_a"], dtype=float)
    pb = np.array(s["price_b"], dtype=float)
    na = pa / pa[0] * 100 if len(pa) and pa[0] else pa
    nb = pb / pb[0] * 100 if len(pb) and pb[0] else pb
    name_a = analysis.get("name_a", analysis["ticker_a"])
    name_b = analysis.get("name_b", analysis["ticker_b"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=na, name=name_a, mode="lines"))
    fig.add_trace(go.Scatter(x=dates, y=nb, name=name_b, mode="lines"))
    fig.update_layout(
        title="정규화 가격 추이 (시작=100, 같이 움직이는지 비교용)",
        yaxis_title="지수(시작일=100)",
        hovermode="x unified",
        template="plotly_white",
    )
    return fig


def divergence_band_chart(
    analysis: dict[str, Any], band_sigmas: tuple[float, float] = (1.0, 2.0)
) -> go.Figure:
    """괴리 원지표 시계열 + 롤링 평균 ±1σ/±2σ 밴드.

    Args:
        analysis: analyze_pair 결과.
        band_sigmas: 밴드 시그마(예: (1, 2)).

    Returns:
        plotly Figure.
    """
    import pandas as pd

    s = analysis["series"]
    dates = s["dates"]
    metric = pd.Series(s["metric"], index=pd.to_datetime(dates))
    window = max(5, len(metric) // 8)
    mean = metric.rolling(window, min_periods=window).mean().shift(1)
    std = metric.rolling(window, min_periods=window).std(ddof=0).shift(1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=metric.to_numpy(), name=analysis["label"], mode="lines"))
    fig.add_trace(go.Scatter(x=dates, y=mean.to_numpy(), name="롤링 평균",
                             line=dict(dash="dash", color="gray")))
    for k in band_sigmas:
        upper = (mean + k * std).to_numpy()
        lower = (mean - k * std).to_numpy()
        fig.add_trace(go.Scatter(x=dates, y=upper, name=f"+{k:g}σ",
                                 line=dict(width=0.5, color="rgba(200,80,80,0.4)")))
        fig.add_trace(go.Scatter(x=dates, y=lower, name=f"-{k:g}σ",
                                 line=dict(width=0.5, color="rgba(80,120,200,0.4)")))
    fig.update_layout(
        title=f"{analysis['label']} 추이 + 표준편차 밴드",
        yaxis_title=analysis["label"],
        hovermode="x unified",
        template="plotly_white",
    )
    return fig


def zscore_chart(analysis: dict[str, Any]) -> go.Figure:
    """z-score 추이 + ±1/±2 기준선.

    Args:
        analysis: analyze_pair 결과.

    Returns:
        plotly Figure.
    """
    s = analysis["series"]
    dates = s["dates"]
    z = [np.nan if v is None else v for v in s["zscore"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=z, name="z-score", mode="lines"))
    for level, color in [(2, "red"), (1, "orange"), (0, "gray"),
                         (-1, "orange"), (-2, "red")]:
        fig.add_hline(y=level, line_dash="dot",
                      line_color=color, opacity=0.5)
    fig.update_layout(
        title="괴리 z-score 추이 (평소 0, ±2 이탈 시 주목)",
        yaxis_title="z-score",
        hovermode="x unified",
        template="plotly_white",
    )
    return fig
