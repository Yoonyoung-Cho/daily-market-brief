"""한경 컨센서스 리포트 PDF 다운로드 + 본문 텍스트 추출.

제목만 보지 않고 **리포트 본문**(목표주가·투자의견·논거)을 읽기 위해 PDF 를 내려받아
텍스트를 추출한다. **PDF 는 디스크에 저장하지 않는다** — 메모리에서 바로 텍스트를 뽑고
버린다(저작물 원본을 로컬·저장소·클라우드 어디에도 남기지 않기 위해).

- 선별(`select_reports`)은 순수 함수: 산업 리포트 + 워치리스트/다빈도 종목 기업 리포트 우선.
- 다운로드·추출은 경계 I/O. 이미지 스캔 PDF 등 추출 실패는 비치명적으로 건너뛴다.

CLI:
    python -m src.data.reports --top 8
"""
from __future__ import annotations

import argparse
import io
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from src.config import Config

_UA = {"User-Agent": "Mozilla/5.0 (compatible; pair-spread-research/1.0)"}
_MIN_TEXT_LEN = 200  # 이보다 짧으면 추출 실패(이미지 PDF 가능성)로 간주


def select_reports(
    reports: list[dict[str, Any]],
    *,
    watchlist_tickers: set[str] | None = None,
    top: int = 8,
) -> list[dict[str, Any]]:
    """본문을 읽을 리포트를 우선순위로 선별한다 (순수 함수).

    우선순위: (1) 산업 리포트, (2) 워치리스트 종목 기업 리포트, (3) 기타 기업 리포트.
    PDF 링크(report_idx)가 있는 것만.

    Args:
        reports: parse_consensus_html 결과.
        watchlist_tickers: 워치리스트 종목코드 집합(우선순위 가점).
        top: 최대 선별 개수.

    Returns:
        선별된 리포트 리스트(상위 top).
    """
    wl = watchlist_tickers or set()

    def priority(r: dict[str, Any]) -> int:
        if not r.get("report_idx"):
            return 99
        cat = r.get("category", "")
        if cat == "산업":
            return 0
        if r.get("ticker") in wl:
            return 1
        if cat == "기업":
            return 2
        return 3

    ranked = sorted((r for r in reports if r.get("report_idx")), key=priority)
    return ranked[:top]


def download_report_bytes(report_idx: str, *, retries: int = 3,
                          backoff: float = 1.5) -> bytes | None:
    """리포트 PDF 를 메모리로 내려받는다(디스크 저장 없음). 실패·PDF 아님이면 None."""
    url = f"https://consensus.hankyung.com/analysis/downpdf?report_idx={report_idx}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            return data if data.startswith(b"%PDF") else None
        except Exception:  # noqa: BLE001
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    return None


def extract_pdf_text(source: bytes | Path, *, max_chars: int = 4000) -> str:
    """PDF 본문 텍스트 추출(pypdf). bytes(메모리) 또는 경로 모두 받는다. 실패 시 "".

    Args:
        source: PDF 바이트 또는 파일 경로.
        max_chars: 추출 상한(브리핑 요약엔 앞부분으로 충분).

    Returns:
        추출 텍스트(공백 정리). 실패 시 "".
    """
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001 - pypdf 미설치
        return ""
    try:
        reader = PdfReader(io.BytesIO(source) if isinstance(source, bytes) else str(source))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) >= max_chars:
                break
        text = "\n".join(parts)
        text = " ".join(text.split())  # 공백 정리
        return text[:max_chars]
    except Exception:  # noqa: BLE001
        return ""


def fetch_report_text(report_idx: str) -> str:
    """리포트 1건: 메모리 다운로드 → 텍스트 추출. PDF 는 남기지 않는다."""
    data = download_report_bytes(report_idx)
    return extract_pdf_text(data) if data else ""


def fetch_report_texts(
    config: Config,
    *,
    top: int = 8,
    force: bool = False,
) -> dict[str, Any]:
    """당일 컨센서스 리포트 중 핵심 N건의 본문 텍스트를 수집·캐싱한다.

    Args:
        config: Config.
        top: 본문을 읽을 리포트 수.
        force: 캐시 무시.

    Returns:
        {generated, reports: [{report_idx, title, broker, category, ticker,
         pdf_url, text, extracted}]} dict.
    """
    from src.data.consensus import fetch_consensus
    from src.data.collector import watchlist_tickers

    out_path = config.cache_dir / "report_texts.json"
    if not force and out_path.exists():
        from src.data.collector import _is_cache_fresh
        if _is_cache_fresh(out_path, config.cache.ttl_hours):
            with out_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)

    consensus = fetch_consensus(config)
    wl = set(watchlist_tickers(config))
    selected = select_reports(consensus.get("reports", []), watchlist_tickers=wl, top=top)

    results: list[dict[str, Any]] = []
    for r in selected:
        idx = r["report_idx"]
        text = fetch_report_text(idx)
        results.append({
            "report_idx": idx,
            "title": r.get("title", ""),
            "broker": r.get("broker", ""),
            "category": r.get("category", ""),
            "ticker": r.get("ticker"),
            "pdf_url": r.get("pdf_url"),
            "text": text,
            "extracted": len(text) >= _MIN_TEXT_LEN,
        })

    out = {
        "source": "한경 컨센서스 리포트 PDF 본문",
        "n_selected": len(results),
        "n_extracted": sum(1 for x in results if x["extracted"]),
        "reports": results,
    }
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="한경 컨센서스 리포트 본문 추출")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    from src.config import load_config

    out = fetch_report_texts(load_config(), top=args.top, force=args.force)
    print(f"[reports] 선별 {out['n_selected']}건, 본문 추출 성공 {out['n_extracted']}건")
    for r in out["reports"]:
        flag = "✓" if r["extracted"] else "✗(추출실패)"
        print(f"  {flag} [{r['category']}] {r['title'][:42]} | {r['broker']}")


if __name__ == "__main__":
    main()
