"""한경 컨센서스 증권사 리포트 메타 수집 (data-collector 확장).

consensus.hankyung.com 메인 페이지를 스크랩해 당일 발행 리포트의
메타데이터(날짜·분류·제목·종목코드·작성자·증권사)를 수집한다.

- 파싱(`parse_consensus_html`)은 순수 함수 → 네트워크 없이 단위테스트 가능.
- 네트워크 I/O 는 `fetch_consensus` 경계에 격리, 결과는 JSON 캐싱.
- 목표주가/투자의견은 메인 목록에 없으므로(공개 범위 한계) 수집하지 않는다.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from src.config import Config

CONSENSUS_URL = "https://consensus.hankyung.com/"
_UA = {"User-Agent": "Mozilla/5.0 (compatible; pair-spread-research/1.0)"}

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_TICKER_RE = re.compile(r"\((\d{6})\)")
_DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")
_REPORT_IDX_RE = re.compile(r"report_idx=(\d+)")
_PDF_BASE = "https://consensus.hankyung.com/analysis/downpdf?report_idx="
_VALID_CATEGORY = {"기업", "산업", "시장", "경제", "파생", "채권"}


def _clean(text: str) -> str:
    """HTML 태그 제거 + 공백 정리."""
    import html as _html

    return _html.unescape(_TAG_RE.sub("", text)).strip()


def parse_consensus_html(html: str) -> list[dict[str, Any]]:
    """한경 컨센서스 목록 HTML 을 파싱한다 (순수 함수).

    Args:
        html: consensus.hankyung.com 메인 페이지 HTML.

    Returns:
        리포트 메타 dict 리스트. 각 항목:
        {date, category, title, ticker(있으면), authors, broker}.
    """
    reports: list[dict[str, Any]] = []
    for tr in _ROW_RE.findall(html):
        cells = [_clean(c) for c in _CELL_RE.findall(tr)]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        date = cells[0]
        if not _DATE_RE.match(date):
            continue
        category = cells[1] if cells[1] in _VALID_CATEGORY else ""
        # 제목은 분류 다음, 가장 긴 셀로 추정
        rest = cells[2:]
        title = max(rest, key=len) if rest else ""
        broker = cells[-1] if len(cells) >= 4 else ""
        authors = cells[-2] if len(cells) >= 5 else ""
        m = _TITLE_TICKER_RE.search(title)
        ticker = m.group(1) if m else None
        im = _REPORT_IDX_RE.search(tr)
        report_idx = im.group(1) if im else None
        reports.append({
            "date": date,
            "category": category,
            "title": title,
            "ticker": ticker,
            "authors": authors,
            "broker": broker,
            "report_idx": report_idx,
            "pdf_url": (_PDF_BASE + report_idx) if report_idx else None,
        })
    return reports


def summarize_by_category(reports: list[dict[str, Any]]) -> dict[str, int]:
    """분류별 리포트 건수 (순수 함수). 산업/기업 어디에 리포트가 몰리는지 신호."""
    counts: dict[str, int] = {}
    for r in reports:
        key = r.get("category") or "기타"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def top_covered_tickers(reports: list[dict[str, Any]], n: int = 10) -> list[dict[str, Any]]:
    """리포트가 많이 나온 종목 상위 N (관심도 신호, 순수 함수).

    Args:
        reports: parse 결과.
        n: 상위 개수.

    Returns:
        [{ticker, count, sample_title, brokers}] 내림차순.
    """
    by_ticker: dict[str, dict[str, Any]] = {}
    for r in reports:
        tk = r.get("ticker")
        if not tk:
            continue
        slot = by_ticker.setdefault(tk, {"ticker": tk, "count": 0,
                                         "sample_title": r["title"], "brokers": set()})
        slot["count"] += 1
        if r.get("broker"):
            slot["brokers"].add(r["broker"])
    rows = sorted(by_ticker.values(), key=lambda x: x["count"], reverse=True)[:n]
    for row in rows:
        row["brokers"] = sorted(row["brokers"])
    return rows


def _fetch_html(url: str, retries: int, backoff: float) -> str:
    """URL HTML 가져오기 (백오프 재시도)."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    assert last is not None
    raise last


def fetch_consensus_range(
    config: Config,
    sdate: str,
    edate: str,
    *,
    max_pages: int = 60,
) -> list[dict[str, Any]]:
    """날짜 범위(sdate~edate)의 리포트 메타를 페이지네이션으로 모은다(과거 백필용).

    한경 컨센서스 /analysis/list 는 report_type 빈값이면 전 분류를 섞어 20건/페이지로
    최신→과거 순 반환한다. 페이지를 넘기며 sdate 이전이 나오면 중단한다.

    Args:
        config: Config.
        sdate, edate: 'YYYY-MM-DD'.
        max_pages: 안전 상한.

    Returns:
        report_idx 로 중복 제거된 리포트 메타 리스트.
    """
    seen: dict[str, dict[str, Any]] = {}
    for page in range(1, max_pages + 1):
        url = (f"https://consensus.hankyung.com/analysis/list"
               f"?sdate={sdate}&edate={edate}&now_page={page}")
        try:
            html = _fetch_html(url, config.cache.max_retries, config.cache.backoff_seconds)
        except Exception:  # noqa: BLE001
            break
        rows = parse_consensus_html(html)
        if not rows:
            break
        for r in rows:
            if r.get("report_idx"):
                seen.setdefault(r["report_idx"], r)
        # 이 페이지의 가장 오래된 날짜가 sdate 이전이면 더 볼 필요 없음
        page_min = min((r["date"] for r in rows if r.get("date")), default=edate)
        if page_min < sdate:
            break
    return [r for r in seen.values() if sdate <= (r.get("date") or "") <= edate]


def fetch_consensus(
    config: Config,
    *,
    html: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """한경 컨센서스 리포트 메타를 수집·캐싱한다.

    Args:
        config: Config.
        html: 주입용 HTML(테스트). 주어지면 네트워크 생략.
        force: 캐시 무시.

    Returns:
        {reports, by_category, top_tickers, source_url, fetched_n} dict.
    """
    path = config.cache_dir / "consensus_kr.json"
    if html is None and not force and path.exists():
        from src.data.collector import _is_cache_fresh

        if _is_cache_fresh(path, config.cache.ttl_hours):
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    if html is None:
        html = _fetch_html(CONSENSUS_URL, config.cache.max_retries,
                            config.cache.backoff_seconds)
    reports = parse_consensus_html(html)
    out = {
        "source": "한경 컨센서스 (consensus.hankyung.com)",
        "source_url": CONSENSUS_URL,
        "reports": reports,
        "by_category": summarize_by_category(reports),
        "top_tickers": top_covered_tickers(reports),
        "fetched_n": len(reports),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out
