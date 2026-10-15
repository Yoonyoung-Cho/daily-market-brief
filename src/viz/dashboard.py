"""데일리 브리핑 대시보드 HTML 렌더.

자기완결형 정적 HTML(서버·DB 불필요). KR·US 탭 = 초심자 3줄 요약 → 오늘의 뉴스 →
기간별 리포트 동향 → 핫 섹터 → 주목 종목 → 증권사 뷰 → 용어 풀이 (+ 옵션: 페어).
헤더에 날짜별 스냅샷(history) 링크를 두어 언제 들어와도 지난 브리핑을 볼 수 있다.
모든 리서치 항목에 소스 티어 배지 + 출처 링크를 표시(신뢰성).
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.brief import TIER_LABELS
from src.config import Config

_WIN_LABEL = {"today": "오늘", "yesterday": "어제", "7d": "1주일", "30d": "1달",
              "90d": "3개월", "all": "전체"}
_KR_WINDOWS = ["today", "yesterday", "7d", "30d"]
_US_WINDOWS = ["today", "yesterday", "7d", "30d"]  # KR 과 동일


def _esc(t: Any) -> str:
    return html.escape(str(t))


def _tier_badge(tier: str) -> str:
    label = TIER_LABELS.get(tier, tier or "")
    cls = {"consensus": "t-con", "ib_news": "t-ib", "news": "t-ib",
           "market_data": "t-mkt", "analyst_data": "t-mkt", "llm": "t-llm"}.get(tier, "t-llm")
    return f'<span class="tier {cls}">{_esc(label)}</span>'


def _plain_summary_html(brief: dict[str, Any]) -> str:
    """초심자 3줄 요약 카드."""
    rows = brief.get("plain_summary") or []
    if not rows:
        return '<p class="muted">초심자 요약이 아직 없습니다. /daily-brief 를 실행하세요.</p>'
    lis = "".join(f'<li>{_esc(s)}</li>' for s in rows[:3])
    return f'<ol class="plain">{lis}</ol>'


def _news_html(brief: dict[str, Any], *, tick_fmt: str = "kr") -> str:
    """오늘의 뉴스 카드: 무슨 일 + 왜 중요한가 + 출처."""
    rows = brief.get("news") or []
    if not rows:
        return '<p class="muted">오늘의 뉴스가 아직 없습니다.</p>'
    cards = []
    for n in rows:
        tks = ", ".join(n.get("tickers", []) or [])
        cards.append(f"""
        <div class="newsc">
          <div class="news-head"><b>{_esc(n.get('title',''))}</b>{_tier_badge(n.get('tier',''))}</div>
          <p class="news-what">{_esc(n.get('summary_plain',''))}</p>
          <p class="news-why">💡 왜 중요? {_esc(n.get('why_it_matters',''))}</p>
          <div class="srcrow">{f'<span class="tk">관련: {_esc(tks)}</span> ' if tks else ''}
            <span class="rdate">{_esc(n.get('date',''))}</span> {_src_link(n)}</div>
        </div>""")
    return f'<div class="newsgrid">{"".join(cards)}</div>'


def _glossary_html(brief: dict[str, Any]) -> str:
    """오늘의 용어 풀이."""
    rows = brief.get("glossary") or []
    if not rows:
        return ""
    lis = "".join(f'<li><b>{_esc(g.get("term",""))}</b> — {_esc(g.get("meaning",""))}</li>'
                  for g in rows)
    return f'<section><h2>📖 오늘의 용어</h2><ul class="gloss">{lis}</ul></section>'


def _history_nav_html(history_dates: list[str] | None, history_dir: str, current: str) -> str:
    """날짜별 스냅샷 링크(최신순). 대시보드 파일과 같은 폴더 기준 상대경로."""
    if not history_dates:
        return ""
    links = []
    for d in history_dates:
        cls = "hday active" if d == current else "hday"
        links.append(f'<a class="{cls}" href="{_esc(history_dir)}/{_esc(d)}.html">{_esc(d)}</a>')
    return (f'<div class="history"><span class="hlbl">📅 지난 브리핑</span>'
            f'<div class="hdays">{"".join(links)}</div></div>')


def _src_link(item: dict[str, Any]) -> str:
    url = item.get("source_url", "")
    name = item.get("source_name") or "출처"
    if not str(url).startswith("http"):
        return '<span class="nosrc">출처 없음</span>'
    return f'<a class="src" href="{_esc(url)}" target="_blank">{_esc(name)} ↗</a>'


def _pct(v: float | None) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    arrow = "▲" if v > 0 else ("▼" if v < 0 else "·")
    return f'<span class="{"up" if v > 0 else "down" if v < 0 else ""}">{arrow}{abs(v):.2f}%</span>'


def _indices_html(snapshot: dict[str, Any]) -> str:
    idx = (snapshot or {}).get("indices", {})
    if not idx:
        return ""
    cells = "".join(
        f'<div class="idx"><span class="iname">{_esc(name)}</span>'
        f'<span class="ival">{(d.get("close") or 0):,.2f}</span>{_pct(d.get("change_pct"))}</div>'
        for name, d in idx.items()
    )
    return f'<div class="indices">{cells}</div>'


def _live_market_tone(snap: dict[str, Any] | None) -> str:
    """실시간 지수 데이터(market_kr.json)로 '오늘의 한눈에' 팩트 문장을 만든다.

    손으로 쓴 market_tone(브리핑)이 오래되어도, 지수 숫자는 항상 최신을 반영한다.
    """
    if not snap or not snap.get("indices"):
        return ""
    idx = snap["indices"]
    parts = [f'{name} {d.get("close", 0):,.2f}({d.get("change_pct", 0):+.2f}%)'
             for name, d in idx.items()]
    line = " · ".join(parts)
    dr = snap.get("index_drivers", {}) or {}
    down = dr.get("down", [])[:3]
    up = dr.get("up", [])[:3]
    if down:
        line += " · 지수 하락 기여: " + ", ".join(
            f'{r["name"]}({r["change_pct"]:+.1f}%)' for r in down)
    if up:
        line += " · 상승 기여: " + ", ".join(
            f'{r["name"]}({r["change_pct"]:+.1f}%)' for r in up)
    return line


def _hot_sectors_html(brief: dict[str, Any]) -> str:
    rows = brief.get("hot_sectors", [])
    if not rows:
        return '<p class="muted">핫 섹터 데이터가 없습니다. /daily-brief 를 실행하세요.</p>'
    cards = []
    for s in rows:
        tickers = ", ".join(s.get("tickers", []) or [])
        cards.append(f"""
        <div class="hot">
          <div class="hot-head"><h4>{_esc(s.get('sector',''))}</h4>{_tier_badge(s.get('tier',''))}</div>
          <p class="trend">{_esc(s.get('trend',''))}</p>
          {f'<p class="drivers">동인: {_esc(s.get("drivers",""))}</p>' if s.get('drivers') else ''}
          {f'<p class="tk">관련: {_esc(tickers)}</p>' if tickers else ''}
          <div class="srcrow">{_src_link(s)}</div>
        </div>""")
    return f'<div class="hotgrid">{"".join(cards)}</div>'


def _marcap_str(v: float | None) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if v >= 1e12:
        return f"시총 {v / 1e12:.1f}조"
    if v >= 1e8:
        return f"시총 {v / 1e8:,.0f}억"
    return ""


def _notable_html(brief: dict[str, Any]) -> str:
    """종목 픽 카드: 종목명·현재가·등락 + 해석 + 리포트 요약 + 출처."""
    rows = brief.get("notable_stocks", [])
    if not rows:
        return '<p class="muted">주목 종목이 없습니다. /daily-brief 를 실행하세요.</p>'
    cards = []
    for s in rows:
        name = _esc(s.get("name", ""))
        tk = _esc(s.get("ticker", "")) if s.get("ticker") else ""
        close = s.get("close")
        price_html = ""
        if isinstance(close, (int, float)) and close == close:
            price_html = (f'<span class="pxnum">{close:,.0f}원</span> '
                          f'{_pct(s.get("change_pct"))}'
                          f'<span class="mcap">{_esc(_marcap_str(s.get("marcap")))}</span>')
        else:
            price_html = '<span class="muted">시세 미부착</span>'
        report = s.get("report_summary", "")
        cards.append(f"""
        <div class="pick">
          <div class="pick-top">
            <div class="pick-name">{name}<span class="pcode">{tk}</span></div>
            <div class="pick-px">{price_html}</div>
          </div>
          <p class="pick-note">💡 {_esc(s.get('note',''))}</p>
          {f'<p class="pick-rep">📄 리포트 요약: {_esc(report)}</p>' if report else ''}
          <div class="srcrow">{_tier_badge(s.get('tier',''))} {_src_link(s)}</div>
        </div>""")
    return f'<div class="pickgrid">{"".join(cards)}</div>'


def _stock_block(s: dict[str, Any]) -> str:
    """기간 내 한 종목: 종목명·현재가 + 그 종목에 대한 리포트들의 의견·내용."""
    name = _esc(s.get("name", s.get("ticker", "")))
    tk = _esc(s.get("ticker", ""))
    close = s.get("close")
    px = ""
    if isinstance(close, (int, float)) and close == close:
        px = f'<span class="spx">{close:,.0f}원 {_pct(s.get("change_pct"))}</span>'
    rep_lis = []
    for r in s.get("reports", []):
        tag = ""
        if r.get("opinion"):
            tag += f'<span class="opbadge">{_esc(r["opinion"])}</span>'
        if r.get("target_price"):
            tag += f'<span class="tgbadge">목표 {_esc(r["target_price"])}</span>'
        concern = (f'<div class="cexc">⚠️ {_esc(r["concern_excerpt"])}</div>'
                   if r.get("concern_excerpt") else "")
        pdf = (f'<a class="src" href="{_esc(r.get("pdf_url") or "#")}" target="_blank">PDF↗</a>'
               if r.get("pdf_url") else "")
        # 요약 우선순위: LLM 요약 > ■ 포인트 > 제목
        points = r.get("points") or []
        if r.get("llm_summary"):
            content = f'<div class="pt">{_esc(r["llm_summary"]).replace(chr(10), "<br>")}</div>'
        elif points:
            content = "".join(f'<div class="pt">· {_esc(p)}</div>' for p in points)
        else:
            content = (f'<div class="pt">{_esc(r.get("summary"))}</div>' if r.get("summary")
                       else f'<div class="pt muted">{_esc(r.get("title",""))} (본문 미수집)</div>')
        rep_lis.append(
            f'<li><span class="rbroker">{_esc(r.get("broker",""))}</span> {tag} {pdf}'
            f'<span class="rsum">{content}</span>{concern}</li>')
    return f"""
    <div class="stockblk">
      <div class="sb-head"><b>{name}</b> <span class="pcode">{tk}</span> {px}
        <span class="rcount">리포트 {s.get('count',0)}건</span></div>
      <ul class="rlist">{''.join(rep_lis)}</ul>
    </div>"""


def _agg_panel(win: str, agg: dict[str, Any], active: bool, mkt: str) -> str:
    """한 기간 패널: 많이 언급된 종목 + 종목별 리포트 의견/내용 (+ 우려는 inline)."""
    cats = " · ".join(f'{_esc(c["category"])} {c["count"]}' for c in agg.get("categories", []))
    stocks = "".join(_stock_block(s) for s in agg.get("stocks", []))
    if not stocks:
        stocks = '<p class="muted">이 기간에 종목 언급 리포트가 없습니다.</p>'
    industry = "".join(
        f'<li>{_esc(r.get("title",""))} <span class="muted">[{_esc(r.get("broker",""))}]</span> '
        f'{f"<a class=src href={_esc(r.get(chr(39)+chr(39)) or r.get("pdf_url") or "#")} target=_blank>PDF↗</a>" if r.get("pdf_url") else ""}</li>'
        for r in agg.get("industry_reports", [])[:6]
    )
    industry_html = (f'<p class="aglbl">산업·시장 리포트</p><ul class="indlist">{industry}</ul>'
                     if industry else "")
    ts = agg.get("target_stat")
    ts_html = ""
    if ts:
        up = ts.get("avg_upside_pct")
        up_html = (f' · 평균 상승여력 <span class="{"up" if up>0 else "down"}">{up:+.0f}%</span>'
                   if isinstance(up, (int, float)) else "")
        ts_html = (f'<div class="tstat">🎯 이 기간 목표가 제시 {ts["n"]}건 · '
                   f'평균 목표가 ${ts["avg_target"]:,.0f}{up_html}</div>')
    return f"""
    <div class="aggpanel{' active' if active else ''}" data-winp="{win}" data-mktp="{mkt}">
      <p class="muted">총 {agg.get('n_reports',0)}건 · {_esc(cats) or '—'}</p>
      {ts_html}
      <p class="aglbl">많이 다뤄진 종목 — 리포트/애널리스트가 뭐라고 했나</p>
      <div class="stockgrid">{stocks}</div>
      {industry_html}
    </div>"""


def _report_trends_html(views: dict[str, Any] | None, mkt: str = "kr",
                        empty_hint: str = "", windows: list[str] | None = None) -> str:
    """기간 탭 + 종목 검색 — 시장(mkt)별로 id/스코프·기간세트 분리."""
    if not views or not views.get("index"):
        return f'<p class="muted">{empty_hint or "데이터가 비어 있습니다."}</p>'
    wins = windows or _KR_WINDOWS
    first = wins[0]
    trends = views["trends"]
    buttons = "".join(
        f'<button class="wbtn{" active" if w == first else ""}" data-win="{w}" data-mkt="{mkt}">{_WIN_LABEL.get(w, w)}</button>'
        for w in wins
    )
    panels = "".join(_agg_panel(w, trends.get(w, {}), w == first, mkt) for w in wins)
    index_json = json.dumps(views["index"], ensure_ascii=False).replace("</", "<\\/")
    return f"""
    <p class="muted">기간을 누르면 그 기간에 어떤 종목·산업이 많이 다뤄졌는지, 리포트/애널리스트
    의견이 어땠는지 정리합니다. (아카이브가 쌓일수록 어제·1주·1달이 풍부해집니다)</p>
    <div class="wtabs">{buttons}</div>
    {panels}
    <div class="search">
      <p class="aglbl">🔎 종목 검색</p>
      <input id="repSearch-{mkt}" class="repsearch" data-mkt="{mkt}" type="text" placeholder="종목명 또는 코드">
      <div id="repResults-{mkt}" class="represults"></div>
    </div>
    <script>window.__REPORT_INDEX_{mkt.upper()}__ = {index_json};</script>"""


def _key_reports_html(brief: dict[str, Any]) -> str:
    """증권사 리포트(PDF 본문 기반) 핵심 요약 카드."""
    rows = brief.get("key_reports", [])
    if not rows:
        return ('<p class="muted">리포트 본문 요약이 없습니다. '
                'scripts/collect.sh 후 /daily-brief 를 실행하세요.</p>')
    cards = []
    for r in rows:
        op = r.get("opinion", "")
        tp = r.get("target_price", "")
        meta = " · ".join(x for x in [
            _esc(r.get("broker", "")),
            f"투자의견 {_esc(op)}" if op else "",
            f"목표가 {_esc(tp)}" if tp else "",
        ] if x)
        cards.append(f"""
        <div class="report">
          <div class="rep-head"><b>{_esc(r.get('title',''))}</b>{_tier_badge(r.get('tier',''))}</div>
          <div class="rep-meta">{meta}</div>
          <p class="rep-sum">{_esc(r.get('summary',''))}</p>
          <a class="src" href="{_esc(r.get('source_url','#'))}" target="_blank">리포트 PDF ↗</a>
        </div>""")
    return f'<div class="reportgrid">{"".join(cards)}</div>'


def _broker_views_html(brief: dict[str, Any], consensus: dict[str, Any]) -> str:
    views = brief.get("broker_views", [])
    vh = "".join(
        f'<div class="bv"><div class="bv-head"><b>{_esc(v.get("firm",""))}</b>'
        f'<span class="bvdate">{_esc(v.get("date",""))}</span>{_tier_badge(v.get("tier",""))}</div>'
        f'<p>{_esc(v.get("view",""))}</p>{_src_link(v)}</div>'
        for v in views
    ) or '<p class="muted">증권사 뷰 데이터가 없습니다.</p>'

    con = ""
    if consensus:
        cats = consensus.get("by_category", {})
        cat_str = " · ".join(f"{k} {n}건" for k, n in cats.items())
        tops = consensus.get("top_tickers", [])[:6]
        tlist = "".join(
            f'<li>{_esc(t.get("ticker",""))} — {_esc(t.get("count",0))}건 '
            f'({_esc(", ".join(t.get("brokers", [])[:2]))})</li>'
            for t in tops
        )
        con = f"""
        <div class="consensus">
          <h4>📋 한경 컨센서스 (오늘 {consensus.get('fetched_n',0)}건)</h4>
          <p class="muted">{_esc(cat_str)}</p>
          {f'<p class="muted">리포트 다수 종목:</p><ul class="tops">{tlist}</ul>' if tlist else ''}
          <a class="src" href="{_esc(consensus.get('source_url','#'))}" target="_blank">한경 컨센서스 ↗</a>
        </div>"""
    return vh + con


def _movers_html(snapshot: dict[str, Any]) -> str:
    if not snapshot:
        return ""

    def tbl(title: str, rows: list[dict[str, Any]], show_cap: bool = False) -> str:
        trs = "".join(
            f'<tr><td>{_esc(r.get("name",""))}</td>'
            f'<td class="num">{(r.get("close") or 0):,.0f}원</td>'
            f'<td class="num">{_pct(r.get("change_pct"))}</td>'
            f'{f"<td class=num>{_esc(_marcap_str(r.get(chr(39)+chr(39)) or r.get("marcap")))}</td>" if show_cap else ""}</tr>'
            for r in rows[:7]
        )
        cap_h = "<th>시총</th>" if show_cap else ""
        return f'<div class="movers"><h4>{title}</h4><table><tr><th>종목</th><th>종가</th><th>등락</th>{cap_h}</tr>{trs}</table></div>'

    drivers = snapshot.get("index_drivers", {}) or {}
    driver_block = ""
    if drivers.get("down") or drivers.get("up"):
        driver_block = f"""
        <p class="muted">코스피는 시총가중 지수입니다. 지수를 실제로 움직인 건 '% 낙폭'이 아니라
        <b>시총 큰 종목의 등락</b>입니다(아래 = 시총 기여도 기준).</p>
        <div class="moverwrap">
          {tbl("⬇️ 지수 끌어내린 종목 (시총 기여)", drivers.get("down", []), show_cap=True)}
          {tbl("⬆️ 지수 끌어올린 종목 (시총 기여)", drivers.get("up", []), show_cap=True)}
        </div>"""

    pct_block = f"""
    <p class="muted" style="margin-top:14px">참고: 아래는 <b>% 등락 상위</b>(시총 무관, 대부분 중소형주) — 지수 주도와는 다릅니다.</p>
    <div class="moverwrap">
      {tbl("📈 % 상승 상위", snapshot.get("top_gainers", []))}
      {tbl("📉 % 하락 상위", snapshot.get("top_losers", []))}
      {tbl("🏛 시총 상위", snapshot.get("top_marcap", []), show_cap=True)}
    </div>"""
    return driver_block + pct_block


def _pairs_html(pairs: list[dict[str, Any]], report_link: str) -> str:
    ok = [p for p in pairs if p.get("status") == "ok"]
    if not ok:
        return '<p class="muted">페어 분석 결과가 없습니다. python -m src.pipeline 실행.</p>'
    trs = []
    for p in ok[:12]:
        z = p.get("current_zscore")
        sig = (p.get("narrative", {}) or {}).get("signal", "")
        nm = f'{_esc(p.get("name_a", p["ticker_a"]))} ↔ {_esc(p.get("name_b", p["ticker_b"]))}'
        pin = "📌 " if p.get("pinned") else ""
        trs.append(
            f'<tr><td>{pin}{nm}</td><td>{_esc(p.get("theme",""))}</td>'
            f'<td class="num">{z:+.2f}</td><td>{_esc(p.get("score",0)):.2}</td>'
            f'<td class="sig">{_esc(sig)}</td></tr>'
        )
    return f"""
    <p class="muted">두 종목의 '평소 대비 가격차'를 통계로 본 기능입니다. 자세한 차트·해석은 전체 리포트에서.</p>
    <table class="pairtbl">
      <tr><th>페어</th><th>테마</th><th>z-score</th><th>스코어</th><th>지금 읽는 법</th></tr>
      {''.join(trs)}
    </table>
    <a class="biglink" href="{_esc(report_link)}" target="_blank">🔗 전체 페어 분석 리포트 열기 ↗</a>"""


def _us_consensus_html(consensus: dict[str, Any]) -> str:
    """미국 종목 컨센서스 표(매수/보유/매도 분포 + 평균목표가 + 현재가)."""
    if not consensus:
        return '<p class="muted">컨센서스 데이터가 없습니다.</p>'
    as_of = consensus.get("_as_of", "")
    rows = []
    for tk, c in consensus.items():
        if tk == "_as_of" or not isinstance(c, dict):
            continue
        buy = (c.get("strongBuy", 0) or 0) + (c.get("buy", 0) or 0)
        hold = c.get("hold", 0) or 0
        sell = (c.get("sell", 0) or 0) + (c.get("strongSell", 0) or 0)
        # 월별 매수의견 추이(3개월전→이번달)
        trend = ""
        bt = [x for x in (c.get("buy_trend") or []) if isinstance(x, int)]
        if len(bt) >= 2:
            d = bt[-1] - bt[0]
            arrow = (f'<span class="up">▲{d}</span>' if d > 0
                     else f'<span class="down">▼{abs(d)}</span>' if d < 0 else '<span class="muted">=</span>')
            trend = f' <span class="muted">[{"›".join(str(x) for x in bt)}]</span> {arrow}'
        pt = c.get("pt_mean")
        price = c.get("price")
        upside = ""
        if isinstance(pt, (int, float)) and isinstance(price, (int, float)) and price:
            up = (pt / price - 1) * 100
            upside = f'<span class="{"up" if up>0 else "down"}">{up:+.0f}%</span>'
        rows.append(
            f'<tr><td><b>{_esc(c.get("name", tk))}</b> <span class="pcode">{_esc(tk)}</span></td>'
            f'<td class="num">매수 {buy}{trend} · 보유 {hold} · 매도 {sell}</td>'
            f'<td class="num">{f"${pt:,.0f}" if isinstance(pt,(int,float)) else "—"}</td>'
            f'<td class="num">{f"${price:,.0f}" if isinstance(price,(int,float)) else "—"} {upside}</td></tr>')
    asof_html = f'<p class="muted">📅 컨센서스 기준일 {_esc(as_of)} (yfinance 현재 스냅샷) · 매수 옆 [3개월전›2›1›이번달] 월별 추이, ▲▼=3개월 순변화. 목표가는 일별 이력이 없어 현재 스냅샷 기준입니다.</p>' if as_of else ""
    return (asof_html +
            '<table class="pairtbl"><tr><th>종목</th><th>애널리스트 컨센서스</th>'
            '<th>평균 목표가</th><th>현재가 · 상승여력</th></tr>' + "".join(rows) + "</table>")


def _us_panel_html(views: dict[str, Any] | None, consensus: dict[str, Any],
                   brief: dict[str, Any]) -> str:
    """미국 시장 패널."""
    tone = brief.get("market_tone") or "미국 시장 요약이 아직 없습니다. /daily-brief 로 채우세요."
    trends = _report_trends_html(
        views, "us",
        "미국 애널리스트 액션이 비어 있습니다. <code>python -m src.data.us_analyst</code> 로 수집하세요.",
        windows=_US_WINDOWS)
    return f"""
    <div class="panel" id="panel-US">
      <section><h2>🔰 초심자 3줄 요약 (미국)</h2>{_plain_summary_html(brief)}</section>
      <section><h2>📌 오늘의 한눈에 (미국)</h2><div class="tone">{_esc(tone)}</div></section>
      <section><h2>📰 오늘의 뉴스</h2>{_news_html(brief, tick_fmt="us")}</section>
      <section><h2>🔥 핫 섹터·테마 <span class="sub">JPMorgan·Goldman 등 IB 뷰</span></h2>{_hot_sectors_html(brief)}</section>
      <section><h2>⭐ 주목 종목</h2>{_notable_html(brief)}</section>
      <section><h2>📚 기간별 애널리스트 동향 <span class="sub">등급변경·목표가 액션 · 종목 검색</span></h2>{trends}</section>
      <section><h2>🎯 종목별 컨센서스 <span class="sub">yfinance</span></h2>{_us_consensus_html(consensus)}</section>
      <section><h2>🏦 증권사 뷰 (글로벌 IB)</h2>{_broker_views_html(brief, {})}</section>
      {_glossary_html(brief)}
    </div>"""


def _css() -> str:
    return """
    :root{--bg:#0f1420;--card:#1a2030;--ink:#e8edf6;--sub:#9aa7bd;--brand:#5b9dff;
      --up:#ff6b6b;--down:#4d9dff;--gold:#ffcf5b;--line:#28324a;--ok:#4dd4ac;}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.6}
    .wrap{max-width:1060px;margin:0 auto;padding:24px 18px 60px}
    h1{font-size:1.7rem;margin:0 0 2px}
    .meta{color:var(--sub);font-size:.86rem}
    .disclaimer{background:#2a1d22;border:1px solid #5a2b33;color:#ffd6d6;padding:9px 13px;border-radius:9px;font-size:.83rem;margin:12px 0}
    .tabs{display:flex;gap:8px;margin:14px 0}
    .tab{background:#1a2030;border:1px solid var(--line);color:var(--sub);padding:9px 18px;border-radius:10px 10px 0 0;cursor:pointer;font-size:.95rem;font-weight:600}
    .tab.active{background:#1b2c4a;color:#cfe0ff;border-color:#3a5d96}
    .panel{display:none}.panel.active{display:block}
    .indices{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0}
    .idx{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;min-width:150px}
    .iname{display:block;font-size:.8rem;color:var(--sub)}.ival{font-size:1.3rem;font-weight:700;margin-right:8px}
    .up{color:var(--up)}.down{color:var(--down)}
    section{margin:22px 0}
    h2{font-size:1.2rem;margin:0 0 10px;border-left:4px solid var(--brand);padding-left:10px}
    h2 .sub{font-size:.78rem;color:var(--sub);font-weight:400;margin-left:6px}
    .pickgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:720px){.pickgrid{grid-template-columns:1fr}}
    .pick{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
    .pick-top{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
    .pick-name{font-size:1.12rem;font-weight:700}
    .pcode{font-size:.74rem;color:var(--sub);margin-left:6px;font-weight:400}
    .pick-px{text-align:right}
    .pxnum{font-size:1.2rem;font-weight:700}
    .mcap{display:block;font-size:.72rem;color:var(--sub)}
    .pick-note{margin:10px 0 4px;font-size:.92rem}
    .pick-rep{margin:4px 0;font-size:.85rem;color:#c4cee0;background:#141a28;border-radius:8px;padding:8px 10px}
    .reportgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:720px){.reportgrid{grid-template-columns:1fr}}
    .report{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
    .rep-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
    .rep-meta{font-size:.8rem;color:var(--brand);margin:4px 0}
    .rep-sum{font-size:.88rem;margin:6px 0 8px;color:#dbe7fb}
    .wtabs{display:flex;gap:6px;margin:6px 0 12px;flex-wrap:wrap}
    .wbtn{background:#1a2030;border:1px solid var(--line);color:var(--sub);padding:6px 14px;border-radius:18px;cursor:pointer;font-size:.85rem}
    .wbtn.active{background:#1b2c4a;color:#cfe0ff;border-color:#3a5d96;font-weight:700}
    .aggpanel{display:none}.aggpanel.active{display:block}
    .aglbl{font-size:.82rem;color:var(--sub);margin:12px 0 7px;font-weight:600}
    .stockgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:720px){.stockgrid{grid-template-columns:1fr}}
    .stockblk{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
    .sb-head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:8px}
    .sb-head b{font-size:1.06rem}
    .spx{font-size:.92rem;font-weight:600}
    .rcount{margin-left:auto;font-size:.74rem;color:var(--sub);background:#16202e;border-radius:12px;padding:2px 9px}
    .rlist{list-style:none;padding:0;margin:8px 0 0}
    .rlist li{font-size:.84rem;margin:9px 0;color:#dbe7fb}
    .rsum{color:#dbe7fb}
    .pt{margin:2px 0 2px 2px;line-height:1.45}
    .rbroker{color:var(--brand);font-weight:600}
    .rdate{color:var(--sub);font-size:.76rem}
    .opbadge{background:#1f3a2f;color:#8ee0c0;border-radius:10px;padding:1px 7px;font-size:.72rem;margin-left:4px}
    .tgbadge{background:#2a2440;color:#cbb6ff;border-radius:10px;padding:1px 7px;font-size:.72rem;margin-left:4px}
    .tstat{background:#15233a;border:1px solid #2a4a6e;border-radius:8px;padding:7px 11px;margin:8px 0;font-size:.9rem;color:#dbe7fb}
    .cexc{color:#ffc9c9;font-size:.8rem;margin-top:3px}
    .indlist{list-style:none;padding:0;margin:0}
    .indlist li{font-size:.84rem;margin:5px 0;color:#c4cee0}
    .search{margin-top:16px}
    #repSearch{width:100%;background:#141a28;border:1px solid var(--line);border-radius:9px;padding:10px 13px;color:var(--ink);font-size:.95rem}
    .represults{margin-top:10px}
    .rephit{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:9px 12px;margin:6px 0;font-size:.86rem}
    .plain{background:#15233a;border:1px solid #2a4a6e;border-radius:12px;padding:14px 18px 14px 38px;margin:0;font-size:1.04rem;line-height:1.75}
    .plain li{margin:4px 0}
    .newsgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:720px){.newsgrid{grid-template-columns:1fr}}
    .newsc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px}
    .news-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
    .news-what{margin:8px 0 4px;font-size:.92rem}
    .news-why{margin:4px 0;font-size:.86rem;color:#c4cee0;background:#141a28;border-radius:8px;padding:7px 10px}
    .gloss{list-style:none;padding:0;margin:0}
    .gloss li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:6px 0;font-size:.9rem}
    .history{display:flex;gap:10px;align-items:flex-start;margin:10px 0 4px;flex-wrap:wrap}
    .hlbl{font-size:.82rem;color:var(--sub);white-space:nowrap;padding-top:3px}
    .hdays{display:flex;gap:6px;flex-wrap:wrap}
    .hday{font-size:.78rem;color:#9cc2ff;background:#141a28;border:1px solid var(--line);border-radius:14px;padding:2px 9px;text-decoration:none}
    .hday.active{background:#1b2c4a;color:#cfe0ff;border-color:#3a5d96;font-weight:700}
    .tone{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;font-size:1.02rem}
    .tone-note{font-size:.86rem;color:#c4cee0;margin-top:8px;padding:10px 14px;background:#141a28;border-left:3px solid var(--brand);border-radius:8px}
    .tone-note.muted{color:var(--sub);border-left-color:#3a4a6a}
    .hotgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:720px){.hotgrid{grid-template-columns:1fr}}
    .hot{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
    .hot-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .hot h4{margin:0;font-size:1.05rem;color:#cfe0ff}
    .trend{margin:8px 0 4px}.drivers,.tk{font-size:.85rem;color:var(--sub);margin:2px 0}
    .srcrow{margin-top:8px}
    .tier{font-size:.68rem;padding:2px 8px;border-radius:20px;white-space:nowrap}
    .t-con{background:#1f3a2f;color:#8ee0c0}.t-ib{background:#1b2c4a;color:#9cc2ff}
    .t-mkt{background:#16202e;color:#a7b6cf}.t-llm{background:#3a2342;color:#f0b6ff}
    .src{color:#9cc2ff;font-size:.82rem;text-decoration:none}.nosrc{color:var(--up);font-size:.8rem}
    .notable{list-style:none;padding:0}.notable li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 13px;margin:7px 0;font-size:.92rem}
    .bv{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin:9px 0}
    .bv-head{display:flex;gap:10px;align-items:center}.bvdate{color:var(--sub);font-size:.8rem}
    .consensus{background:#141a28;border:1px dashed var(--line);border-radius:12px;padding:13px 15px;margin-top:10px}
    .consensus h4{margin:0 0 6px}.tops{margin:4px 0;padding-left:18px;font-size:.85rem;color:var(--sub)}
    .moverwrap{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
    @media(max-width:720px){.moverwrap{grid-template-columns:1fr}}
    .movers{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
    .movers h4{margin:0 0 8px;font-size:.95rem}
    table{width:100%;border-collapse:collapse;font-size:.86rem}
    .movers td{padding:4px 2px;border-bottom:1px solid #222b40}.num{text-align:right}
    .pairtbl th{text-align:left;color:var(--sub);font-size:.8rem;border-bottom:1px solid var(--line);padding:6px 4px}
    .pairtbl td{padding:7px 4px;border-bottom:1px solid #222b40;font-size:.86rem;vertical-align:top}
    .sig{color:#c4cee0;font-size:.8rem}
    .biglink{display:inline-block;margin-top:12px;background:#1b2c4a;color:#cfe0ff;padding:9px 16px;border-radius:9px;text-decoration:none}
    .muted{color:var(--sub);font-size:.88rem}
    .placeholder{background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:40px;text-align:center;color:var(--sub)}
    footer{margin-top:34px;color:var(--sub);font-size:.8rem;border-top:1px solid var(--line);padding-top:14px}
    """


def _js() -> str:
    return """
    document.querySelectorAll('.tab').forEach(function(t){
      t.addEventListener('click',function(){
        document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active')});
        document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('active')});
        t.classList.add('active');
        document.getElementById('panel-'+t.dataset.m).classList.add('active');
      });
    });
    // 기간 탭 전환 (시장별 스코프: data-mkt)
    document.querySelectorAll('.wbtn').forEach(function(b){
      b.addEventListener('click',function(){
        var mkt=b.dataset.mkt, win=b.dataset.win;
        document.querySelectorAll('.wbtn[data-mkt="'+mkt+'"]').forEach(function(x){x.classList.remove('active')});
        document.querySelectorAll('.aggpanel[data-mktp="'+mkt+'"]').forEach(function(x){x.classList.remove('active')});
        b.classList.add('active');
        var p=document.querySelector('.aggpanel[data-mktp="'+mkt+'"][data-winp="'+win+'"]');
        if(p) p.classList.add('active');
      });
    });
    // 종목 검색 (시장별)
    document.querySelectorAll('.repsearch').forEach(function(si){
      var mkt=si.dataset.mkt;
      var idx=window['__REPORT_INDEX_'+mkt.toUpperCase()+'__']||[];
      var box=document.getElementById('repResults-'+mkt);
      si.addEventListener('input',function(){
        var q=si.value.trim().toLowerCase();
        if(!q){box.innerHTML='';return;}
        var hits=idx.filter(function(r){
          return (r.name||'').toLowerCase().indexOf(q)>=0
            || (r.ticker||'').toLowerCase().indexOf(q)>=0
            || (r.title||'').toLowerCase().indexOf(q)>=0;
        }).slice(0,30);
        if(!hits.length){box.innerHTML='<p class=muted>해당 종목 언급 없음</p>';return;}
        box.innerHTML=hits.map(function(r){
          var op=r.opinion?(' · <b>'+r.opinion+'</b>'):'';
          var tp=r.target_price?(' · 목표 '+r.target_price):'';
          var cc=r.has_concern?' · ⚠️하향/우려':'';
          var lnk=r.pdf_url?(' <a class=src href="'+r.pdf_url+'" target=_blank>출처↗</a>'):'';
          return '<div class=rephit><b>'+(r.name||r.title)+'</b> <span class=muted>'+r.date+' ['+(r.broker||'')+']</span>'+op+tp+cc+lnk+'<br><span class=muted>'+(r.title||'')+'</span></div>';
        }).join('');
      });
    });
    """


def generate_dashboard(
    config: Config,
    *,
    briefing: dict[str, Any] | None,
    market_snapshot: dict[str, Any] | None,
    consensus: dict[str, Any] | None,
    pairs: list[dict[str, Any]],
    report_views: dict[str, Any] | None = None,
    us_views: dict[str, Any] | None = None,
    us_consensus: dict[str, Any] | None = None,
    us_briefing: dict[str, Any] | None = None,
    generated_at: str = "",
    report_link: str = "report.html",
    out_path: Path | None = None,
    history_dates: list[str] | None = None,
    history_dir: str = "history",
) -> Path:
    """데일리 브리핑 대시보드 HTML 생성.

    Args:
        config: Config.
        briefing: briefing_kr.json 내용(없으면 안내 표시).
        market_snapshot: market_kr.json.
        consensus: consensus_kr.json.
        pairs: pair_analysis.json (features.pairs 가 켜졌을 때만 표시).
        generated_at: 생성시각.
        report_link: 전체 페어 리포트 링크.
        out_path: 출력 경로. 기본 data/dashboard.html.
        history_dates: 날짜별 스냅샷 목록(최신순). 헤더에 링크로 표시.
        history_dir: 스냅샷 폴더명(대시보드 파일 기준 상대경로).

    Returns:
        생성된 HTML 경로.
    """
    out = out_path or (config.cache_dir / "dashboard.html")
    brief = briefing or {}
    disclaimer = _esc(config.disclaimer)
    gen_date = (generated_at or "")[:10]
    as_of = gen_date or brief.get("as_of_date", "")  # 헤더 기준일은 '생성일'(실시간)
    show_pairs = bool(getattr(getattr(config, "features", None), "pairs", False))
    show_us = bool(getattr(getattr(config, "features", None), "us", True))

    # '오늘의 한눈에' = 실시간 지수 데이터로 자동 생성(손글씨 market_tone 대신)
    live_tone = _live_market_tone(market_snapshot)
    tone = live_tone or "지수 데이터가 없습니다. bash scripts/dash.sh 로 수집하세요."
    # LLM 리서치 코멘트는 '오늘 생성분'일 때만 부가 표시(오래된 건 숨김 → 숫자 모순 방지)
    llm_tone = brief.get("market_tone") or ""
    llm_tone_html = ""
    if llm_tone and brief.get("as_of_date", "") == gen_date:
        llm_tone_html = f'<div class="tone-note">🔎 리서치 코멘트: {_esc(llm_tone)}</div>'
    elif llm_tone:
        llm_tone_html = (f'<div class="tone-note muted">🔎 리서치 코멘트(기준일 '
                         f'{_esc(brief.get("as_of_date",""))}, /daily-brief 로 갱신): {_esc(llm_tone)}</div>')

    pairs_section = (f'<section><h2>🔗 페어 분석 (옵션 기능)</h2>{_pairs_html(pairs, report_link)}</section>'
                     if show_pairs else "")
    kr_panel = f"""
    <div class="panel active" id="panel-KR">
      {_indices_html(market_snapshot)}
      <section><h2>🔰 초심자 3줄 요약</h2>{_plain_summary_html(brief)}</section>
      <section><h2>📌 오늘의 한눈에 <span class="sub">지수 실시간(생성 {_esc(generated_at)})</span></h2><div class="tone">{_esc(tone)}</div>{llm_tone_html}</section>
      <section><h2>📰 오늘의 뉴스 <span class="sub">무슨 일이 있었고 왜 중요한가</span></h2>{_news_html(brief)}</section>
      <section><h2>📚 기간별 리포트 동향 <span class="sub">오늘/어제/1주/1달 · 많이 다룬 종목과 리포트 의견 · 종목 검색</span></h2>{_report_trends_html(report_views, "kr", "아카이브가 비어 있습니다. <code>python -m src.data.archive ingest</code> 로 리포트를 쌓으세요(실행을 놓친 날은 자동 백필됩니다).")}</section>
      <section><h2>🔥 핫 섹터·테마 <span class="sub">오늘 요약</span></h2>{_hot_sectors_html(brief)}</section>
      <section><h2>⭐ 주목 종목 <span class="sub">시총·커버리지 기준 통과 종목만</span></h2>{_notable_html(brief)}</section>
      <section><h2>🏦 증권사 뷰 (국내·글로벌)</h2>{_broker_views_html(brief, consensus or {})}</section>
      <section><h2>📊 오늘의 등락·시총</h2>{_movers_html(market_snapshot or {})}</section>
      {_glossary_html(brief)}
      {pairs_section}
    </div>"""

    us_panel = _us_panel_html(us_views, us_consensus or {}, us_briefing or {}) if show_us else ""
    us_tab = '<button class="tab" data-m="US">🇺🇸 미국</button>' if show_us else ""

    body = f"""
    <div class="wrap">
      <h1>📰 데일리 마켓 브리핑</h1>
      <div class="meta">기준일 {_esc(as_of)} · 생성 {_esc(generated_at)} · 데이터: FinanceDataReader(KRX) · 한경 컨센서스 · yfinance · 뉴스 보도</div>
      {_history_nav_html(history_dates, history_dir, as_of)}
      <div class="disclaimer">⚠️ {disclaimer} 증권사 뷰는 <b>뉴스로 보도된 요약</b>이며 원문 리포트가 아닙니다.</div>
      <div class="tabs">
        <button class="tab active" data-m="KR">🇰🇷 한국</button>
        {us_tab}
      </div>
      {kr_panel}
      {us_panel}
      <footer>
        소스 티어: {" · ".join(TIER_LABELS.values())}.<br>
        가격·시총: FinanceDataReader(KRX). 리포트 메타: 한경 컨센서스. 글로벌 IB: 뉴스 보도 기반.<br>
        ⚠️ {disclaimer}
      </footer>
    </div>
    <script>{_js()}</script>"""

    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>데일리 마켓 브리핑 {_esc(as_of)}</title>
<style>{_css()}</style></head><body>{body}</body></html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
