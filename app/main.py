"""Streamlit UI — reporter 서브에이전트의 화면.

추천 목록(테이블)에서 쌍을 선택 -> 상세 차트/해석 화면.
모든 화면에 투자 자문 아님 디스클레이머 표시.

실행:
    streamlit run app/main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# 프로젝트 루트를 import 경로에 추가 (streamlit run app/main.py 대응)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.pipeline import load_analysis, run_pipeline  # noqa: E402
from src.viz.charts import (  # noqa: E402
    divergence_band_chart,
    normalized_price_chart,
    zscore_chart,
)

st.set_page_config(page_title="주가 괴리율(페어 스프레드) 분석", layout="wide")

cfg = load_config()

REL_KR = {
    "pref_common": "보통주-우선주",
    "holdco_sub": "지주사-자회사",
    "group_chain": "그룹 밸류체인",
    "industry_peer": "동일산업",
    "statistical": "통계 발굴",
}


def _disclaimer() -> None:
    st.warning(f"⚠️ {cfg.disclaimer}")


def _summary_table(analyses: list[dict]) -> pd.DataFrame:
    rows = []
    for a in analyses:
        rows.append({
            "쌍": f"{a.get('name_a', a['ticker_a'])} / {a.get('name_b', a['ticker_b'])}",
            "관계유형": REL_KR.get(a["relationship_type"], a["relationship_type"]),
            "출처": "시드" if a.get("source") == "seed" else "통계",
            "괴리지표": a.get("label", ""),
            "현재값": _fmt_metric(a),
            "z-score": round(a.get("current_zscore", float("nan")), 2),
            "백분위": f"{a.get('percentile', float('nan')):.0f}%",
            "반감기(일)": "—" if a.get("half_life") is None else round(a["half_life"], 0),
            "스코어": round(a.get("score", 0.0), 3),
        })
    return pd.DataFrame(rows)


def _fmt_metric(a: dict) -> str:
    v = a.get("current_metric")
    if v is None:
        return "—"
    if "할인율" in a.get("label", "") or "디스카운트" in a.get("label", ""):
        return f"{v * 100:.1f}%"
    return f"{v:.4f}"


def main() -> None:
    st.title("📊 주가 괴리율(페어 스프레드) 분석")
    st.caption(
        f"MARKET={cfg.market} · UNIVERSE={cfg.universe} · "
        f"LOOKBACK={cfg.lookback_days}일 · WINDOW={cfg.rolling_window}일"
    )
    _disclaimer()

    with st.sidebar:
        st.header("파이프라인")
        limit = st.number_input("유니버스 제한(개발용, 0=전체)", 0, 500, 0, step=10)
        force = st.checkbox("캐시 무시 재수집", value=False)
        if st.button("🔄 파이프라인 실행 / 갱신"):
            with st.spinner("수집·스크리닝·괴리분석 중…"):
                summary = run_pipeline(
                    cfg,
                    universe_limit=(limit or None),
                    force=force,
                )
            st.success(f"분석 완료: {summary['n_analyzed']}쌍")

    analyses = load_analysis(cfg)
    if not analyses:
        st.info("아직 분석 결과가 없습니다. 좌측에서 **파이프라인 실행**을 눌러주세요.")
        return

    st.subheader("🔎 추천 페어 (스코어 순)")
    table = _summary_table(analyses)
    st.dataframe(table, use_container_width=True, hide_index=True)

    labels = [
        f"{a.get('name_a', a['ticker_a'])} / {a.get('name_b', a['ticker_b'])} "
        f"[{REL_KR.get(a['relationship_type'], a['relationship_type'])}]"
        for a in analyses
    ]
    idx = st.selectbox("상세 분석할 쌍 선택", range(len(labels)),
                       format_func=lambda i: labels[i])
    sel = analyses[idx]

    st.markdown("---")
    st.subheader(f"📈 상세 분석 — {labels[idx]}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재 괴리값", _fmt_metric(sel))
    c2.metric("z-score", f"{sel.get('current_zscore', float('nan')):.2f}")
    c3.metric("역사적 백분위", f"{sel.get('percentile', float('nan')):.0f}%")
    c4.metric("반감기(일)", "—" if sel.get("half_life") is None else f"{sel['half_life']:.0f}")

    st.info(f"💬 {sel.get('interpretation', '')}")
    if sel.get("mechanism"):
        st.caption(f"괴리 메커니즘: {sel['mechanism']}")

    st.plotly_chart(normalized_price_chart(sel), use_container_width=True)
    cc1, cc2 = st.columns(2)
    with cc1:
        st.plotly_chart(
            divergence_band_chart(sel, cfg.analysis.band_sigmas),
            use_container_width=True,
        )
    with cc2:
        st.plotly_chart(zscore_chart(sel), use_container_width=True)

    st.markdown("---")
    _disclaimer()


if __name__ == "__main__":
    main()
