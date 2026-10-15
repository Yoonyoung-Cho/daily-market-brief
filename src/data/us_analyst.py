"""미국 애널리스트 데이터 수집 (yfinance) — 등급변경·목표가·컨센서스.

미국엔 한경 컨센서스 같은 무료 리포트 PDF 아카이브가 없으므로, 애널리스트의
'등급변경/목표가 액션'을 리포트 이벤트로 변환해 KR 과 동일한 기간집계·카드 UI 에 태운다.

- `build_action_records`: yfinance upgrades_downgrades -> 리포트 레코드(순수 함수).
- `fetch_us_actions`/`fetch_us_consensus`: 네트워크 경계, JSON 캐싱.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import Config

# 등급 → Buy/Hold/Sell 정규화
_GRADE_MAP = {
    "buy": "Buy", "strong buy": "Buy", "outperform": "Buy", "overweight": "Buy",
    "accumulate": "Buy", "add": "Buy", "positive": "Buy", "sector outperform": "Buy",
    "hold": "Hold", "neutral": "Hold", "market perform": "Hold", "equal-weight": "Hold",
    "equalweight": "Hold", "in-line": "Hold", "sector perform": "Hold", "peer perform": "Hold",
    "sell": "Sell", "underperform": "Sell", "underweight": "Sell", "reduce": "Sell",
    "negative": "Sell", "sector underperform": "Sell",
}


def _norm_grade(g: str) -> str | None:
    return _GRADE_MAP.get(str(g or "").strip().lower())


def build_action_records(
    ticker: str, name: str, theme: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """yfinance upgrades_downgrades 행들을 리포트 레코드로 변환 (순수 함수).

    Args:
        ticker, name, theme: 종목 메타.
        rows: [{GradeDate, Firm, ToGrade, FromGrade, Action, priceTargetAction,
                currentPriceTarget, priorPriceTarget}] (dict 리스트).

    Returns:
        아카이브 호환 레코드 리스트(broker=Firm, opinion=등급, target_price=$X, llm_summary 포함).
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        gd = r.get("GradeDate")
        date = str(gd)[:10] if gd is not None else ""
        if not date or not date.startswith("20"):
            continue
        firm = str(r.get("Firm", "")).strip()
        to_grade = str(r.get("ToGrade", "")).strip()
        from_grade = str(r.get("FromGrade", "")).strip()
        action = str(r.get("Action", "")).strip().lower()  # up/down/main/init/reit
        pt_action = str(r.get("priceTargetAction", "")).strip()  # Raises/Lowers/Announces
        cur_pt = r.get("currentPriceTarget") or 0
        prior_pt = r.get("priorPriceTarget") or 0

        # 액션 한국어화
        if action == "up":
            act_kr = f"⬆️ 상향({from_grade}→{to_grade})" if from_grade else "⬆️ 상향"
        elif action == "down":
            act_kr = f"⬇️ 하향({from_grade}→{to_grade})" if from_grade else "⬇️ 하향"
        elif action in ("init", "initiated"):
            act_kr = "신규 커버리지"
        else:
            act_kr = f"{to_grade} 유지" if to_grade else "코멘트"

        pt_str = ""
        if cur_pt:
            arrow = ""
            if pt_action.lower().startswith("rais"):
                arrow = "↑"
            elif pt_action.lower().startswith("lower"):
                arrow = "↓"
            pt_str = f"목표가 ${cur_pt:,.0f}{arrow}"
            if prior_pt and prior_pt != cur_pt:
                pt_str += f"(직전 ${prior_pt:,.0f})"

        summary = f"{firm}: {act_kr}" + (f" · {pt_str}" if pt_str else "")
        idx = f"US-{ticker}-{date}-{firm}".replace(" ", "_")[:80]
        out.append({
            "report_idx": idx,
            "date": date,
            "category": "등급변경",
            "title": summary,
            "ticker": ticker,
            "name": name,
            "theme": theme,
            "broker": firm,
            "opinion": _norm_grade(to_grade) or to_grade or None,
            "target_price": f"${cur_pt:,.0f}" if cur_pt else None,
            "llm_summary": summary,   # 카드에 그대로 노출
            "has_concern": action == "down",
            "concern_excerpt": f"투자의견 하향: {from_grade}→{to_grade}" if action == "down" else "",
            "pdf_url": f"https://finance.yahoo.com/quote/{ticker}/analysis",
            "extracted": True,
        })
    return out


def fetch_us_actions(
    config: Config,
    *,
    months: int = 6,
    max_per_ticker: int = 40,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """미국 워치리스트 종목의 애널리스트 액션을 수집·캐싱한다.

    Returns:
        {report_idx: record} (KR report_archive 와 동일 구조).
    """
    path = config.cache_dir / "us_actions.json"
    if not force and path.exists():
        from src.data.collector import _is_cache_fresh
        if _is_cache_fresh(path, config.cache.ttl_hours):
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    import yfinance as yf

    wl = _load_us_watchlist(config)
    archive: dict[str, dict[str, Any]] = {}
    for t in wl.get("tickers", []):
        tk, name, theme = t["ticker"], t["name"], t.get("theme", "")
        try:
            ud = yf.Ticker(tk).upgrades_downgrades
        except Exception:  # noqa: BLE001
            continue
        if ud is None or len(ud) == 0:
            continue
        ud = ud.reset_index().tail(max_per_ticker)
        rows = ud.to_dict("records")
        for rec in build_action_records(tk, name, theme, rows):
            archive[rec["report_idx"]] = rec

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(archive, fh, ensure_ascii=False, indent=2, default=str)
    return archive


def fetch_us_news(config: Config, *, per_ticker: int = 6) -> dict[str, dict[str, Any]]:
    """종목별 최근 뉴스/분석을 '내용 있는 리포트 레코드'로 변환(제목+요약+실제 출처).

    yfinance 액션은 목표가만 있고 본문이 없으므로, 뉴스로 '왜(rationale)'를 보강한다.
    뉴스는 날짜가 최신이라 최근 기간 창도 채운다.
    """
    import yfinance as yf

    wl = _load_us_watchlist(config)
    out: dict[str, dict[str, Any]] = {}
    for t in wl.get("tickers", []):
        tk, name, theme = t["ticker"], t["name"], t.get("theme", "")
        try:
            news = yf.Ticker(tk).news or []
        except Exception:  # noqa: BLE001
            continue
        for n in news[:per_ticker]:
            c = n.get("content", n) if isinstance(n, dict) else {}
            title = (c.get("title") or "").strip()
            if not title:
                continue
            summ = (c.get("summary") or c.get("description") or "").strip()
            pub = str(c.get("pubDate") or "")[:10]
            prov = (c.get("provider") or {}).get("displayName", "뉴스")
            url = c.get("canonicalUrl") or c.get("clickThroughUrl") or {}
            url = url.get("url") if isinstance(url, dict) else url
            idx = f"USNEWS-{tk}-{n.get('id', title)}".replace(" ", "_")[:90]
            out[idx] = {
                "report_idx": idx, "date": pub or "", "category": "뉴스/분석",
                "ticker": tk, "name": name, "theme": theme, "broker": prov,
                "opinion": None, "target_price": None,
                "title": title,
                "llm_summary": f"{title}" + (f" — {summ}" if summ else ""),
                "has_concern": False, "concern_excerpt": "",
                "pdf_url": url or f"https://finance.yahoo.com/quote/{tk}/news",
                "extracted": True,
            }
    return out


def fetch_us_archive(config: Config, *, force: bool = False) -> dict[str, dict[str, Any]]:
    """미국 아카이브 = 등급변경 액션 + 뉴스(내용·출처). 합쳐서 us_archive.json 저장."""
    path = config.cache_dir / "us_archive.json"
    if not force and path.exists():
        from src.data.collector import _is_cache_fresh
        if _is_cache_fresh(path, config.cache.ttl_hours):
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
    # 증분 누적: 기존 아카이브 위에 새 액션·뉴스를 합친다(매일 돌리면 기간이 누적)
    archive: dict[str, dict[str, Any]] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            archive = json.load(fh)
    archive.update(fetch_us_actions(config, force=True))
    archive.update(fetch_us_news(config))

    # 최근 31일만 보관(오래된 등급액션 등 잡음 제거). 날짜 없는 건 버림.
    from datetime import datetime, timedelta
    cutoff = (datetime.now().date() - timedelta(days=31)).strftime("%Y-%m-%d")
    archive = {k: v for k, v in archive.items() if (v.get("date") or "") >= cutoff}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(archive, fh, ensure_ascii=False, indent=2, default=str)
    return archive


def fetch_us_consensus(config: Config, *, force: bool = False) -> dict[str, dict[str, Any]]:
    """종목별 컨센서스(매수/보유/매도 분포 + 목표가)와 현재가."""
    path = config.cache_dir / "us_consensus.json"
    if not force and path.exists():
        from src.data.collector import _is_cache_fresh
        if _is_cache_fresh(path, config.cache.ttl_hours):
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    import yfinance as yf
    from datetime import datetime

    wl = _load_us_watchlist(config)
    out: dict[str, dict[str, Any]] = {"_as_of": datetime.now().strftime("%Y-%m-%d")}
    for t in wl.get("tickers", []):
        tk = t["ticker"]
        rec: dict[str, Any] = {"name": t["name"], "theme": t.get("theme", "")}
        try:
            yt = yf.Ticker(tk)
            recs = yt.recommendations
            if recs is not None and len(recs):
                rows = recs.to_dict("records")
                row = rows[0]  # 0m(현재)
                rec.update({k: int(row.get(k, 0)) for k in
                            ("strongBuy", "buy", "hold", "sell", "strongSell")})
                # 월별 매수의견(strongBuy+buy) 추이: 3개월전→이번달 순
                bym = {r.get("period"): (int(r.get("strongBuy", 0) or 0) + int(r.get("buy", 0) or 0))
                       for r in rows}
                rec["buy_trend"] = [bym.get(p) for p in ("-3m", "-2m", "-1m", "0m")]
                if bym.get("-3m") is not None:
                    rec["prev_buy"] = bym["-3m"]
            pt = yt.analyst_price_targets or {}
            rec["pt_mean"] = pt.get("mean")
            rec["pt_high"] = pt.get("high")
            rec["pt_low"] = pt.get("low")
            rec["price"] = pt.get("current")
        except Exception:  # noqa: BLE001
            pass
        out[tk] = rec

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    return out


def _load_us_watchlist(config: Config) -> dict[str, Any]:
    path = config.cache_dir / "watchlist_us.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    """CLI: 미국 애널리스트 액션 + 컨센서스 수집."""
    from src.config import load_config

    cfg = load_config()
    a = fetch_us_archive(cfg, force=True)
    c = fetch_us_consensus(cfg, force=True)
    n_news = sum(1 for r in a.values() if r.get("category") == "뉴스/분석")
    print(f"[us] 아카이브 {len(a)}건(등급액션 {len(a)-n_news}·뉴스 {n_news}), 컨센서스 {len(c)}종목")


if __name__ == "__main__":
    main()
