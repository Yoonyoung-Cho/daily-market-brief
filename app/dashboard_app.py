"""마켓 브리핑 대시보드 — Streamlit 버전.

정적 HTML 대시보드(src/viz/dashboard.py)와 **같은 백엔드·데이터**를 쓰되, 화면만
Streamlit 으로. 커스텀 다크 테마 + 카드 CSS 로 기본 Streamlit 의 밋밋함을 보완.

실행:
    streamlit run app/dashboard_app.py
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.brief import TIER_LABELS, load_briefing  # noqa: E402
from src.config import load_config  # noqa: E402
from src.data.archive import build_period_views, ingest_new_reports  # noqa: E402
from src.data.consensus import fetch_consensus  # noqa: E402
from src.data.market import fetch_market_snapshot  # noqa: E402
from src.pipeline import load_analysis  # noqa: E402

cfg = load_config()
st.set_page_config(page_title="마켓 브리핑 대시보드", page_icon="📰", layout="wide")

# ── 스타일(밋밋함 보완) ────────────────────────────────────────
st.markdown("""
<style>
  .block-container{padding-top:1.6rem;max-width:1180px}
  h1,h2,h3{letter-spacing:-.3px}
  .card{background:#1a2030;border:1px solid #28324a;border-radius:14px;padding:14px 16px;margin-bottom:10px}
  .stock b{font-size:1.06rem}
  .pcode{color:#9aa7bd;font-size:.74rem;margin-left:6px}
  .px-up{color:#ff6b6b;font-weight:700}.px-dn{color:#4d9dff;font-weight:700}
  .rcount{float:right;font-size:.74rem;color:#9aa7bd;background:#16202e;border-radius:12px;padding:2px 9px}
  .rep{font-size:.85rem;margin:7px 0;color:#dbe7fb;border-top:1px solid #222b40;padding-top:7px}
  .rbroker{color:#5b9dff;font-weight:600}.rdate{color:#9aa7bd;font-size:.76rem}
  .op{background:#1f3a2f;color:#8ee0c0;border-radius:10px;padding:1px 7px;font-size:.72rem;margin-left:4px}
  .tg{background:#2a2440;color:#cbb6ff;border-radius:10px;padding:1px 7px;font-size:.72rem;margin-left:4px}
  .cexc{color:#ffc9c9;font-size:.8rem;margin-top:3px}
  .pt{margin:2px 0;line-height:1.45;font-size:.84rem}
  .badge{display:inline-block;font-size:.72rem;padding:2px 9px;border-radius:14px;margin-right:5px;background:#222b40;color:#9aa7bd}
  .b-con{background:#1f3a2f;color:#8ee0c0}.b-ib{background:#1b2c4a;color:#9cc2ff}
  a{color:#9cc2ff !important}
  .disc{background:#2a1d22;border:1px solid #5a2b33;color:#ffd6d6;padding:9px 13px;border-radius:9px;font-size:.84rem}
</style>
""", unsafe_allow_html=True)


def esc(t) -> str:
    return html.escape(str(t))


# ── 데이터 로딩(캐시) ──────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _market():
    try:
        return fetch_market_snapshot(cfg)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _consensus():
    try:
        return fetch_consensus(cfg)
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def _views():
    try:
        return build_period_views(cfg)
    except Exception:
        return None


def _pct_html(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    cls = "px-up" if v > 0 else ("px-dn" if v < 0 else "")
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "·")
    return f'<span class="{cls}">{arrow}{abs(v):.2f}%</span>'


def _report_line_html(r: dict) -> str:
    """종목 카드 안의 리포트 한 줄 — 제목이 아니라 '내용 요약'을 보여준다."""
    tag = f'<span class="op">{esc(r["opinion"])}</span>' if r.get("opinion") else ""
    if r.get("target_price"):
        tag += f'<span class="tg">목표 {esc(r["target_price"])}</span>'
    pdf = (f' <a href="{esc(r.get("pdf_url") or "#")}" target="_blank">PDF↗</a>'
           if r.get("pdf_url") else "")
    concern = (f'<div class="cexc">⚠️ {esc(r["concern_excerpt"])}</div>'
               if r.get("concern_excerpt") else "")
    points = r.get("points") or []
    if r.get("llm_summary"):
        content = f'<div class="pt">{esc(r["llm_summary"]).replace(chr(10), "<br>")}</div>'
    elif points:
        content = "".join(f'<div class="pt">· {esc(p)}</div>' for p in points)
    elif r.get("summary"):
        content = f'<div class="pt">{esc(r["summary"])}</div>'
    else:
        content = f'<div class="pt" style="color:#9aa7bd">{esc(r.get("title",""))} (본문 미수집)</div>'
    return (f'<div class="rep"><span class="rbroker">{esc(r.get("broker",""))}</span> '
            f'{tag}{pdf}{content}{concern}</div>')


def _stock_card_html(s: dict) -> str:
    """기간 내 한 종목 카드: 종목명·현재가 + 그 종목 리포트들."""
    close = s.get("close")
    price = (f'{close:,.0f}원 {_pct_html(s.get("change_pct"))}'
             if isinstance(close, (int, float)) and close == close else "")
    reps = "".join(_report_line_html(r) for r in s.get("reports", []))
    return (f'<div class="card stock"><b>{esc(s.get("name",""))}</b>'
            f'<span class="pcode">{esc(s.get("ticker",""))}</span> {price}'
            f'<span class="rcount">리포트 {s.get("count",0)}건</span>{reps}</div>')


# ── 사이드바 ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 데이터")
    st.caption(f"시장 {cfg.market} · 통화 {cfg.currency.code}")
    if st.button("🔄 데이터 갱신 (수집)", use_container_width=True):
        with st.spinner("시장·컨센서스·리포트 아카이브 갱신 중…"):
            try:
                fetch_market_snapshot(cfg, force=True)
                fetch_consensus(cfg, force=True)
                ingest_new_reports(cfg)
            except Exception as e:  # noqa: BLE001
                st.error(f"갱신 실패: {e}")
        st.cache_data.clear()
        st.rerun()
    st.caption("※ 리서치 '요약 텍스트'(핫섹터·해석)는 LLM 단계라 "
               "Claude Code 의 /daily-brief 로 갱신합니다.")

# ── 헤더 ───────────────────────────────────────────────────────
brief = load_briefing(cfg, "KR") or {}
st.title("📰 마켓 브리핑 대시보드")
st.caption(f"기준일 {brief.get('as_of_date','-')} · 데이터: FinanceDataReader(KRX) · 한경 컨센서스 · IB 뉴스 보도")
st.markdown(f'<div class="disc">⚠️ {esc(cfg.disclaimer)} 증권사 뷰는 뉴스로 보도된 요약이며 원문 리포트가 아닙니다.</div>',
            unsafe_allow_html=True)

tab_kr, tab_us = st.tabs(["🇰🇷 한국", "🇺🇸 미국 (준비중)"])

with tab_kr:
    market = _market()
    views = _views()
    consensus = _consensus()

    # 지수
    if market and market.get("indices"):
        cols = st.columns(len(market["indices"]) + 2)
        for col, (name, d) in zip(cols, market["indices"].items()):
            col.metric(name, f"{(d.get('close') or 0):,.2f}",
                       f"{d.get('change_pct', 0):.2f}%")

    # 오늘의 한눈에 — 실시간 지수 데이터 기반(손글씨 텍스트 아님)
    st.subheader("📌 오늘의 한눈에")
    if market and market.get("indices"):
        idx = market["indices"]
        line = " · ".join(f'{n} {d.get("close",0):,.2f}({d.get("change_pct",0):+.2f}%)'
                          for n, d in idx.items())
        dn = (market.get("index_drivers", {}) or {}).get("down", [])[:3]
        if dn:
            line += " · 하락기여: " + ", ".join(f'{r["name"]}({r["change_pct"]:+.1f}%)' for r in dn)
        st.info(line)
    else:
        st.info("지수 데이터가 없습니다. 사이드바에서 데이터 갱신을 눌러주세요.")
    lt = brief.get("market_tone")
    if lt:
        st.caption(f"🔎 리서치 코멘트(기준일 {brief.get('as_of_date','?')}, /daily-brief 로 갱신): {lt}")

    # 📚 기간별 리포트 동향
    st.subheader("📚 기간별 리포트 동향")
    if not views or not views.get("index"):
        st.caption("아카이브가 비어 있습니다. 사이드바에서 데이터 갱신, 또는 "
                   "`python -m src.data.archive backfill --days 30` 으로 과거를 채우세요.")
    else:
        labels = {"today": "오늘", "yesterday": "어제", "7d": "1주일", "30d": "1달"}
        win = st.radio("기간", list(labels), format_func=lambda w: labels[w],
                       horizontal=True, label_visibility="collapsed")
        agg = views["trends"].get(win, {})
        cats = " · ".join(f'{c["category"]} {c["count"]}' for c in agg.get("categories", []))
        st.caption(f"총 {agg.get('n_reports', 0)}건 · {cats or '—'}")
        st.markdown("**많이 언급된 종목 — 리포트들이 뭐라고 했나**")

        stocks = agg.get("stocks", [])
        if not stocks:
            st.caption("이 기간에 종목 언급 리포트가 없습니다.")
        for row in range(0, len(stocks), 2):
            for col, s in zip(st.columns(2), stocks[row:row + 2]):
                col.markdown(_stock_card_html(s), unsafe_allow_html=True)

    # 종목 검색
    st.subheader("🔎 종목 검색")
    if views and views.get("index"):
        q = st.text_input("종목명 또는 코드", placeholder="예: 이오테크닉스, 005930",
                          label_visibility="collapsed")
        if q:
            ql = q.strip().lower()
            hits = [r for r in views["index"]
                    if ql in (r.get("name", "") or "").lower()
                    or ql in (r.get("ticker", "") or "")
                    or ql in (r.get("title", "") or "").lower()][:40]
            st.caption(f"{len(hits)}건")
            for r in hits:
                op = f' · **{r["opinion"]}**' if r.get("opinion") else ""
                tp = f' · 목표 {r["target_price"]}' if r.get("target_price") else ""
                cc = " · ⚠️우려" if r.get("has_concern") else ""
                pdf = f' · [PDF]({r["pdf_url"]})' if r.get("pdf_url") else ""
                st.markdown(f'**{r.get("name") or r.get("title")}** '
                            f'<span class="rdate">{r.get("date","")} [{r.get("broker","")}]</span>'
                            f'{op}{tp}{cc}{pdf}<br>'
                            f'<span style="color:#9aa7bd;font-size:.85rem">{esc(r.get("title",""))}</span>',
                            unsafe_allow_html=True)

    # 핫 섹터 / 증권사 뷰
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔥 핫 섹터 (오늘)")
        for s in brief.get("hot_sectors", []):
            st.markdown(f'<div class="card"><b>{esc(s.get("sector",""))}</b> '
                        f'<span class="badge b-ib">{esc(TIER_LABELS.get(s.get("tier",""),""))}</span><br>'
                        f'{esc(s.get("trend",""))}<br>'
                        f'<a href="{esc(s.get("source_url","#"))}" target="_blank">{esc(s.get("source_name","출처"))} ↗</a></div>',
                        unsafe_allow_html=True)
    with c2:
        st.subheader("🏦 증권사 뷰")
        for v in brief.get("broker_views", []):
            st.markdown(f'<div class="card"><b>{esc(v.get("firm",""))}</b> '
                        f'<span class="rdate">{esc(v.get("date",""))}</span><br>'
                        f'{esc(v.get("view",""))}<br>'
                        f'<a href="{esc(v.get("source_url","#"))}" target="_blank">출처 ↗</a></div>',
                        unsafe_allow_html=True)

    # 등락(지수 기여) + 페어
    if market and market.get("index_drivers"):
        st.subheader("📊 지수를 움직인 종목 (시총 기여)")
        import pandas as pd
        dn = market["index_drivers"].get("down", [])[:7]
        up = market["index_drivers"].get("up", [])[:7]
        cc1, cc2 = st.columns(2)
        if dn:
            cc1.caption("⬇️ 끌어내림")
            cc1.dataframe(pd.DataFrame([{"종목": r["name"], "등락%": round(r["change_pct"], 2),
                                         "시총(조)": round(r["marcap"] / 1e12, 1)} for r in dn]),
                          hide_index=True, use_container_width=True)
        if up:
            cc2.caption("⬆️ 끌어올림")
            cc2.dataframe(pd.DataFrame([{"종목": r["name"], "등락%": round(r["change_pct"], 2),
                                         "시총(조)": round(r["marcap"] / 1e12, 1)} for r in up]),
                          hide_index=True, use_container_width=True)

    st.subheader("🔗 페어 분석 (부가 기능)")
    pairs = [p for p in load_analysis(cfg) if p.get("status") == "ok"]
    if pairs:
        import pandas as pd
        st.dataframe(pd.DataFrame([{
            "페어": f'{p.get("name_a", p["ticker_a"])} ↔ {p.get("name_b", p["ticker_b"])}',
            "테마": p.get("theme", ""),
            "z-score": round(p.get("current_zscore", float("nan")), 2),
            "스코어": round(p.get("score", 0), 2),
            "지금 읽는 법": (p.get("narrative", {}) or {}).get("signal", ""),
        } for p in pairs[:12]]), hide_index=True, use_container_width=True)
    else:
        st.caption("페어 분석 결과가 없습니다. `python -m src.pipeline` 실행.")

with tab_us:
    import json as _json
    from src.data.archive import build_us_views
    ub = load_briefing(cfg, "US") or {}
    st.subheader("📌 오늘의 한눈에 (미국)")
    st.info(ub.get("market_tone") or "미국 요약이 아직 없습니다. /daily-brief 로 채우세요.")

    st.subheader("🔥 핫 섹터 (JPMorgan·Goldman 등 IB 뷰)")
    for s in ub.get("hot_sectors", []):
        tks = ", ".join(s.get("tickers", []) or [])
        st.markdown(f'<div class="card"><b>{esc(s.get("sector",""))}</b> '
                    f'<span class="badge b-ib">{esc(TIER_LABELS.get(s.get("tier",""),""))}</span><br>'
                    f'{esc(s.get("trend",""))}{f" · 관련: {esc(tks)}" if tks else ""}<br>'
                    f'<a href="{esc(s.get("source_url","#"))}" target="_blank">{esc(s.get("source_name","출처"))} ↗</a></div>',
                    unsafe_allow_html=True)

    st.subheader("🎯 종목별 컨센서스 (yfinance)")
    try:
        uc = _json.loads((cfg.cache_dir / "us_consensus.json").read_text(encoding="utf-8"))
    except Exception:
        uc = {}
    if uc:
        import pandas as pd
        if uc.get("_as_of"):
            st.caption(f"📅 컨센서스 기준일 {uc['_as_of']} (yfinance 현재 스냅샷)")
        rows = []
        for tk, c in uc.items():
            if tk == "_as_of" or not isinstance(c, dict):
                continue
            buy = (c.get("strongBuy", 0) or 0) + (c.get("buy", 0) or 0)
            rows.append({"종목": f'{c.get("name", tk)} ({tk})',
                         "매수": buy, "보유": c.get("hold", 0) or 0,
                         "매도": (c.get("sell", 0) or 0) + (c.get("strongSell", 0) or 0),
                         "평균목표": f'${c["pt_mean"]:,.0f}' if isinstance(c.get("pt_mean"), (int, float)) else "—",
                         "현재가": f'${c["price"]:,.0f}' if isinstance(c.get("price"), (int, float)) else "—"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("컨센서스 데이터가 없습니다. `python -m src.data.us_analyst` 실행.")

    st.subheader("📚 기간별 애널리스트 동향 (등급변경·목표가)")
    uv = build_us_views(cfg) or {}
    if uv.get("index"):
        labels = {"today": "오늘", "yesterday": "어제", "7d": "1주일", "30d": "1달"}
        uw = st.radio("기간", list(labels), format_func=lambda w: labels[w],
                      horizontal=True, label_visibility="collapsed", key="us_win")
        st.caption(f"기준일 {uv.get('as_of','')} · 뉴스가 매일 누적되며 기간이 분리됩니다")
        agg_us = uv["trends"].get(uw, {})
        ts = agg_us.get("target_stat")
        if ts:
            up = ts.get("avg_upside_pct")
            up_s = f" · 평균 상승여력 {up:+.0f}%" if isinstance(up, (int, float)) else ""
            st.markdown(f"🎯 **이 기간 목표가 제시 {ts['n']}건** · 평균 목표가 ${ts['avg_target']:,.0f}{up_s}")
        ustocks = agg_us.get("stocks", [])
        if not ustocks:
            st.caption("이 기간 액션이 없습니다.")
        for r0 in range(0, len(ustocks), 2):
            for col, s in zip(st.columns(2), ustocks[r0:r0 + 2]):
                col.markdown(_stock_card_html(s), unsafe_allow_html=True)
    else:
        st.caption("미국 액션 데이터가 없습니다. `python -m src.data.us_analyst` 실행.")

st.divider()
st.caption(f"소스 티어: {' · '.join(TIER_LABELS.values())}  |  ⚠️ {cfg.disclaimer}")
