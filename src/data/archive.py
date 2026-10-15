"""리포트 아카이브 — 증권사 리포트를 매일 증분 누적하고 기간별 경향성을 집계한다.

- 증분 수집: 한경 컨센서스 목록에서 **아직 없는 report_idx 만** 내려받아 파싱·누적.
- 휴리스트 파서(순수 함수): 투자의견·목표주가·우려점을 표준 패턴에서 추출.
- 기간 집계(순수 함수): 오늘/어제/1주/1달 윈도우로 많이 언급된 종목·산업·투자의견 분포·
  우려 리포트를 정리.

요약(summary)·우려점 정제는 /daily-brief 의 LLM 단계에서 보강할 수 있다(하이브리드).

CLI:
    python -m src.data.archive ingest        # 새 리포트만 수집·누적
    python -m src.data.archive trends --window 7d
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import Config

_ARCHIVE_NAME = "report_archive.json"      # 메타·의견·목표가·요약 (git 추적)
_EXCERPTS_NAME = "report_excerpts.json"    # 본문 발췌 (로컬 전용, git 제외 — 저작물)
# 저장소에 올리지 않는 필드: 본문 발췌(저작물)·작성자 이름(개인정보)
_PRIVATE_FIELDS = ("text_excerpt", "authors")

# ── 휴리스틱 파서 (순수 함수) ──────────────────────────────────
_OPINION_RE = re.compile(
    r"투자의견\s*[:은는]?\s*"
    r"(Buy|BUY|매수|적극매수|Strong\s*Buy|Trading\s*Buy|Outperform|Overweight|비중확대|"
    r"Hold|HOLD|중립|Neutral|Marketperform|Sell|SELL|매도|Underweight|비중축소|Reduce)",
    re.I,
)
_TARGET_RE = re.compile(r"목표주가\s*[:]?\s*([0-9][0-9,]{2,})\s*원?")
_CONCERN_KEYS = ["리스크 요인", "위험 요인", "우려", "불확실", "하회", "부진", "둔화", "악화"]
_CONCERN_RE = re.compile("|".join(_CONCERN_KEYS))

_OPINION_MAP = {
    "buy": "Buy", "매수": "Buy", "적극매수": "Buy", "strong buy": "Buy",
    "trading buy": "Buy", "outperform": "Buy", "overweight": "Buy", "비중확대": "Buy",
    "hold": "Hold", "중립": "Hold", "neutral": "Hold", "marketperform": "Hold",
    "sell": "Sell", "매도": "Sell", "underweight": "Sell", "비중축소": "Sell", "reduce": "Sell",
}


def parse_opinion(text: str) -> str | None:
    """본문에서 투자의견을 추출해 Buy/Hold/Sell 로 정규화. 없으면 None."""
    m = _OPINION_RE.search(text or "")
    if not m:
        return None
    return _OPINION_MAP.get(m.group(1).strip().lower(), m.group(1).strip())


def parse_target_price(text: str) -> str | None:
    """본문에서 목표주가(원)를 추출. 없으면 None."""
    m = _TARGET_RE.search(text or "")
    return f"{m.group(1)}원" if m else None


def detect_concern(text: str) -> tuple[bool, str]:
    """우려/리스크 언급 여부 + 발췌. (있으면 True, 주변 문구)."""
    if not text:
        return False, ""
    m = _CONCERN_RE.search(text)
    if not m:
        return False, ""
    s = max(0, m.start() - 30)
    e = min(len(text), m.end() + 70)
    return True, text[s:e].strip()


# 리포트 본문 불릿 기호(신뢰 가능한 사각/원형만; ▶ 등은 장식·헤더에 쓰여 제외)
_BULLET_CHARS = "■◼◾●□"
_BULLET_SPLIT = re.compile("[" + _BULLET_CHARS + "]")
# 표/헤더(지표블록) 판별용 — 본문이 아니라 시세표일 때 거른다
_HEADER_JUNK = ("발행주식수", "총발행", "시가총액", "상승여력", "평균 거래", "평균거래",
                "52주", "60일", "Analyst", "Stock Indicator", "주가수익률")
# 본문 시작 앵커(이 뒤부터가 분석 내용)
_CONTENT_ANCHORS = ("Company Brief", "Company Update", "Company Analysis", "Company Note",
                    "Flash Note", "Result Comment", "Issue Comment", "Issue & News",
                    "Earnings Review", "투자포인트")


def _clean_bullet(b: str, *, max_len: int = 80) -> str:
    """단일 불릿/문장 정리(잡음 제거 + 길이 제한). HBM·GPU 등 짧은 약어는 보존."""
    s = _NOISE_RE.sub(" ", b)
    s = re.sub(r"[A-Z]{6,}", " ", s)   # 긴 ALL-CAPS(브로커명)만 제거, 짧은 약어 보존
    s = re.sub(r"\S+@\S+", "", s)
    s = re.sub(r"\(\d{5,6}[,\w/]*\)", "", s)
    s = re.sub(r"20\d{2}[.\-]\d{2}[.\-]\d{2}", "", s)
    s = s.replace("Y o Y", "YoY").replace("Q o Q", "QoQ").replace("y o y", "YoY")
    s = re.sub(r"\d{2,4}-\d{3,4}", "", s)   # 전화/내선
    s = re.sub(r"\(\s*\)", "", s)           # 빈 괄호 "( )"
    s = re.sub(r"\s+\d+\s*$", "", s)
    s = " ".join(s.split())
    return (s[:max_len] + "…") if len(s) > max_len else s


def summarize_bullets(text: str, *, max_bullets: int = 3) -> list[str]:
    """본문의 불릿 핵심 포인트들을 리스트로(강점·기대·전망). 불릿 없으면 빈 리스트."""
    if not text or not any(c in text for c in _BULLET_CHARS):
        return []
    out: list[str] = []
    for raw in _BULLET_SPLIT.split(text)[1:]:
        if not raw.strip():
            continue
        b = _clean_bullet(raw)
        # 헤더/지표블록·한글 없는 불릿은 버림(장식 마커 오인 방지)
        if len(b) >= 8 and not any(j in b for j in _HEADER_JUNK) and re.search(r"[가-힣]", b):
            out.append(b)
        if len(out) >= max_bullets:
            break
    return out


# 프로즈(문장) 전용 경량 클리너 — 머리말·연락처만 제거, 재무용어(목표주가·상향 등)는 보존
_PROSE_JUNK = re.compile(r"주가 및 주요이벤트|재무지표|밸류에이션 지표|체크포인트|기업분석|"
                         r"Company Brief|Company Update|Company Analysis|Company Report|"
                         r"Company Note|Company Issue Brief|Appendix 참조|"
                         r"금융투자분석사의 확인 및 중요 공시는")


def _clean_prose(s: str) -> str:
    s = _PROSE_JUNK.sub(" ", s)
    s = re.sub(r"[A-Z]{6,}", " ", s)
    s = re.sub(r"\S+@\S+", "", s)
    s = re.sub(r"\(\d{5,6}[,\w/]*\)", "", s)
    s = re.sub(r"20\d{2}[.\-]\d{2}[.\-]\d{2}", "", s)
    s = re.sub(r"\d{2,4}-\d{3,4}", "", s)
    s = s.replace("Y o Y", "YoY").replace("Q o Q", "QoQ").replace("y o y", "YoY")
    return " ".join(s.split())


def summarize_prose(text: str, *, max_chars: int = 90) -> str:
    """불릿 없는 본문에서 핵심 '한 문장'을 뽑는다(앵커 뒤 본문). 지표표면 "" 반환."""
    if not text:
        return ""
    body = None
    for anc in _CONTENT_ANCHORS:
        if anc in text:
            body = text.split(anc, 1)[1]
            break
    if body is None:  # 앵커 없으면 '종목명(코드)' 헤더 뒤부터
        m = re.search(r"\(\d{5,6}[^)]*\)", text[:90])
        body = text[m.end():] if m else text
    # 선두 잡음 제거: '| 섹터 |', 리딩 숫자('00 '), 날짜
    body = re.sub(r"^\s*\d{1,3}\s+", "", body)
    body = re.sub(r"^\s*(?:\|[^|]*\|\s*)+", "", body)
    body = re.sub(r"^\s*20\d{2}[.\-]\s?\d{1,2}[.\-]\s?\d{1,2}", "", body)
    s = _clean_prose(body)
    s = re.sub(r"^\s*(?:\|[^|]*\|\s*)+", "", s)
    head = s[:130]
    # 지표표(시세블록) 판별: 마커 2개 이상이거나 대표 마커면 버림
    if sum(1 for j in _HEADER_JUNK if j in head) >= 2 or "Appendix" in head or "총발행" in head:
        return ""
    if not re.search(r"[가-힣]", s[:30]):       # 앞부분에 한글 없으면 표/영문 헤더
        return ""
    # 첫 문장만(한국어 종결 '~다./음./함./됨.' 기준)
    m = re.search(r"^(.{15,}?[다음함됨])\.\s", s)
    out = (m.group(1) + ".") if m else s
    return (out[:max_chars] + "…") if len(out) > max_chars else out


def summarize_excerpt(text: str, *, max_chars: int = 200) -> str:
    """본문 요약: 불릿 우선, 없으면 앵커 기반 산문. 둘 다 안 되면 "" ."""
    bullets = summarize_bullets(text)
    if bullets:
        s = " · ".join(bullets)
        return (s[:max_chars] + "…") if len(s) > max_chars else s
    return summarize_prose(text)


def title_thesis(title: str) -> str:
    """리포트 제목에서 '종목명(코드)'·말머리·반복을 떼고 핵심 한 줄만 남긴다.

    예: '현대건설(000720) 원전으로 한 번 더 도약' -> '원전으로 한 번 더 도약'.
    일부 목록 HTML 은 제목을 여러 번 반복해 담으므로 반복도 제거한다.
    """
    if not title:
        return ""
    t = " ".join(title.split())  # 개행·중복공백 정리
    # 반복 제거: 앞부분이 다시 등장하면 그 지점에서 자른다
    for n in (16, 14, 12, 10, 8):
        if len(t) > n:
            j = t.find(t[:n], n)
            if j != -1:
                t = t[:j].strip()
                break
    t = re.sub(r"^\s*\S+?\(\d{6}[^)]*\)\s*", "", t)  # 선두 'name(code)' 제거
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", t)          # '[산업]' 말머리 제거
    t = re.sub(r"\(\d{6}[^)]*\)", "", t)             # 잔여 코드 제거
    return " ".join(t.split()).strip()


_NOISE_RE = re.compile(
    r"주가 및 주요이벤트|재무지표|밸류에이션 지표|체크포인트|기업분석|"
    r"Company Brief|Company Update|Company Analysis|"
    r"현재주가|투자의견|목표주가|매수|적극매수|중립|비중확대|Initiation|NDR|後記|"
    r"신규|유지|상향|하향|\d+개월"
)


def name_from_title(title: str) -> str:
    """제목에서 종목명 추출('이오테크닉스(039030) ...' -> '이오테크닉스')."""
    m = re.match(r"\s*(.+?)\s*\(\d{6}\)", title or "")
    return m.group(1).strip() if m else ""


def parse_report(meta: dict[str, Any], text: str) -> dict[str, Any]:
    """리포트 메타 + 본문 -> 아카이브 레코드 (순수 함수).

    본문 발췌(`text_excerpt`)도 함께 반환하지만, 저장 시 `split_private` 로 분리돼
    git 추적 파일에는 들어가지 않는다. 화면용 요약(`summary`·`points`)은 여기서 미리 계산.
    """
    has_concern, excerpt = detect_concern(text)
    return {
        "report_idx": meta.get("report_idx"),
        "date": meta.get("date"),
        "category": meta.get("category", ""),
        "title": meta.get("title", ""),
        "ticker": meta.get("ticker"),
        "name": name_from_title(meta.get("title", "")),
        "broker": meta.get("broker", ""),
        "pdf_url": meta.get("pdf_url"),
        "opinion": parse_opinion(text),
        "target_price": parse_target_price(text),
        "has_concern": has_concern,
        "concern_excerpt": excerpt,
        "summary": summarize_excerpt(text),
        "points": summarize_bullets(text),
        "text_excerpt": (text or "")[:600],
        "extracted": len(text or "") >= 200,
    }


def split_private(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """레코드를 (공개 가능 레코드, 비공개 필드) 로 나눈다 (순수 함수)."""
    public = {k: v for k, v in record.items() if k not in _PRIVATE_FIELDS}
    private = {k: record[k] for k in _PRIVATE_FIELDS if record.get(k)}
    return public, private


# ── 기간 집계 (순수 함수) ──────────────────────────────────────
_WINDOWS = {"today": 0, "yesterday": 1, "7d": 6, "30d": 29, "90d": 89, "all": 99999}


def filter_window(
    reports: list[dict[str, Any]], today: date, window: str
) -> list[dict[str, Any]]:
    """윈도우(today/yesterday/7d/30d)에 해당하는 리포트만 (순수 함수).

    Args:
        reports: 아카이브 레코드 리스트.
        today: 기준일.
        window: 'today'|'yesterday'|'7d'|'30d'.

    Returns:
        해당 기간 리포트.
    """
    def to_date(s: str) -> date | None:
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            return None

    if window == "all":
        return list(reports)
    if window == "yesterday":
        y = today - timedelta(days=1)
        return [r for r in reports if to_date(r.get("date", "")) == y]
    if window == "today":
        return [r for r in reports if to_date(r.get("date", "")) == today]
    days = _WINDOWS.get(window, 6)
    start = today - timedelta(days=days)
    return [r for r in reports if (d := to_date(r.get("date", ""))) and start <= d <= today]


def aggregate(
    reports: list[dict[str, Any]], *, top_n: int = 8, per_stock: int = 6
) -> dict[str, Any]:
    """기간 리포트를 **종목 중심**으로 집계 (순수 함수).

    "많이 언급된 종목이 뭐고, 그 종목에 대해 여러 리포트가 어떤 의견·내용을 냈는지"를
    보여주기 위한 구조. 우려는 리포트별로 곁들일 뿐 따로 모으지 않는다.

    Returns:
        {n_reports, categories, stocks, industry_reports}.
        stocks[i] = {ticker, name, count, reports:[{broker,title,opinion,
                     concern_excerpt,excerpt,pdf_url}]}.
    """
    from collections import Counter

    by_ticker: dict[str, dict[str, Any]] = {}
    cats: Counter = Counter()
    industry: list[dict[str, Any]] = []
    for r in reports:
        cats[r.get("category") or "기타"] += 1
        tk = r.get("ticker")
        # 요약 우선순위: LLM 요약 > 불릿 포인트 > 앵커 산문 > 제목 핵심
        txt = r.get("text_excerpt", "")
        llm = r.get("llm_summary")
        points = [] if llm else (r.get("points") or summarize_bullets(txt))
        if llm:
            summary = llm
        elif points:
            summary = " · ".join(points)
        else:
            summary = summarize_prose(txt) or title_thesis(r.get("title", ""))
        brief = {
            "broker": r.get("broker", ""), "title": r.get("title", ""),
            "opinion": r.get("opinion"), "target_price": r.get("target_price"),
            "concern_excerpt": r.get("concern_excerpt", ""),
            "llm_summary": llm,          # LLM 구조 요약(있으면 최우선)
            "points": points,            # ■ 핵심 포인트(있으면 줄바꿈 렌더)
            "summary": summary,          # 폴백/검색용 단문
            "pdf_url": r.get("pdf_url"), "date": r.get("date", ""),
        }
        if tk:
            slot = by_ticker.setdefault(
                tk, {"ticker": tk, "name": r.get("name") or tk, "count": 0, "reports": []})
            slot["count"] += 1
            slot["reports"].append(brief)
        elif r.get("category") in ("산업", "시장") and len(industry) < 10:
            industry.append(brief)

    stocks = sorted(by_ticker.values(), key=lambda x: x["count"], reverse=True)[:top_n]
    for s in stocks:
        s["reports"] = s["reports"][:per_stock]
    return {
        "n_reports": len(reports),
        "categories": [{"category": k, "count": v} for k, v in cats.most_common()],
        "stocks": stocks,
        "industry_reports": industry,
    }


# ── 증분 수집 (경계 I/O) ───────────────────────────────────────
def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_archive(config: Config) -> dict[str, Any]:
    """아카이브 로드(공개 레코드만). {report_idx: record}."""
    return _load_json(config.cache_dir / _ARCHIVE_NAME)


def load_excerpts(config: Config) -> dict[str, str]:
    """본문 발췌 로드(로컬 전용). {report_idx: text_excerpt}."""
    return _load_json(config.cache_dir / _EXCERPTS_NAME)


def save_archive(config: Config, archive: dict[str, Any]) -> Path:
    """아카이브 저장. 비공개 필드(본문 발췌·작성자)는 git 제외 파일로 분리해 저장한다.

    이미 공개 파일에 섞여 있던 비공개 필드도 이 호출에서 분리된다(1회 마이그레이션).
    """
    path = config.cache_dir / _ARCHIVE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    excerpts = load_excerpts(config)
    public_all: dict[str, Any] = {}
    for idx, rec in archive.items():
        public, private = split_private(rec)
        if "points" not in public and private.get("text_excerpt"):
            public["points"] = summarize_bullets(private["text_excerpt"])
        public_all[idx] = public
        if private.get("text_excerpt"):
            excerpts[idx] = private["text_excerpt"]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(public_all, fh, ensure_ascii=False, indent=2)
    with (config.cache_dir / _EXCERPTS_NAME).open("w", encoding="utf-8") as fh:
        json.dump(excerpts, fh, ensure_ascii=False, indent=2)
    return path


def ingest_new_reports(
    config: Config,
    *,
    download_text: bool = True,
    max_new: int = 60,
    lookback_days: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """컨센서스 목록에서 아직 없는 리포트만 내려받아 아카이브에 누적한다.

    메인 페이지(당일분)만이 아니라 **최근 `lookback_days` 일의 날짜검색 결과도 함께** 훑기
    때문에, 며칠 실행을 놓쳐도 다음 실행에서 빈 날이 자동으로 채워진다(무인 운영의 핵심).

    Args:
        config: Config.
        download_text: True 면 PDF 본문까지 받아 의견·목표가·우려 파싱.
        max_new: 1회 최대 신규 처리 수(과부하 방지).
        lookback_days: 며칠 전까지 다시 훑을지. None 이면 config.digest.backfill_days.
        today: 기준일(테스트 주입).

    Returns:
        {n_total, n_new, n_extracted, range} 요약.
    """
    from src.data.consensus import fetch_consensus, fetch_consensus_range
    from src.data.reports import fetch_report_text

    archive = load_archive(config)
    consensus = fetch_consensus(config, force=True)  # 목록은 항상 최신
    metas: dict[str, dict[str, Any]] = {
        m["report_idx"]: m for m in consensus.get("reports", []) if m.get("report_idx")}

    days = config.digest.backfill_days if lookback_days is None else lookback_days
    ref = today or datetime.now().date()
    sdate = (ref - timedelta(days=days)).strftime("%Y-%m-%d")
    edate = ref.strftime("%Y-%m-%d")
    if days > 0:
        try:
            for m in fetch_consensus_range(config, sdate, edate):
                if m.get("report_idx"):
                    metas.setdefault(m["report_idx"], m)
        except Exception as exc:  # noqa: BLE001 - 백필 실패는 비치명적
            print(f"[warn] 백필({sdate}~{edate}) 실패: {exc}")

    new = 0
    extracted = 0
    # 최신 날짜 우선 처리(상한에 걸려도 오늘 것부터 채움)
    for meta in sorted(metas.values(), key=lambda m: m.get("date", ""), reverse=True):
        idx = meta.get("report_idx")
        if not idx or idx in archive:
            continue  # 이미 있는 데이터는 건너뜀(증분)
        if new >= max_new:
            break
        text = fetch_report_text(idx) if download_text else ""  # PDF 는 메모리에서만
        rec = parse_report(meta, text)
        rec["ingested_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        archive[idx] = rec
        new += 1
        if rec["extracted"]:
            extracted += 1

    save_archive(config, archive)
    return {"n_total": len(archive), "n_new": new, "n_extracted": extracted,
            "range": f"{sdate}~{edate}"}


def backfill_archive(
    config: Config,
    *,
    days: int = 30,
    today: date | None = None,
    with_text: bool = True,
    max_pdf: int = 80,
) -> dict[str, Any]:
    """과거 날짜 범위 리포트를 한 번에 백필한다(한경 날짜검색 사용).

    메타데이터는 전부 누적(종목·산업 언급 집계용), PDF 본문은 상한(max_pdf) 내에서
    기업/종목 리포트 우선으로 받아 의견·목표가·우려를 채운다.

    Args:
        config: Config.
        days: 오늘로부터 며칠 전까지.
        today: 기준일(테스트 주입).
        with_text: PDF 본문 추출 여부.
        max_pdf: PDF 다운로드 상한(과부하 방지).

    Returns:
        {n_total, n_new, n_text} 요약.
    """
    from src.data.consensus import fetch_consensus_range
    from src.data.reports import fetch_report_text

    ref = today or datetime.now().date()
    sdate = (ref - timedelta(days=days)).strftime("%Y-%m-%d")
    edate = ref.strftime("%Y-%m-%d")
    metas = fetch_consensus_range(config, sdate, edate)

    archive = load_archive(config)
    # 최신 + 종목 있는 기업 리포트 우선으로 PDF 다운로드(메모리에서만)
    metas_sorted = sorted(metas, key=lambda m: m.get("date", ""), reverse=True)
    new = 0
    text_done = 0
    for meta in metas_sorted:
        idx = meta.get("report_idx")
        if not idx or idx in archive:
            continue
        text = ""
        want_text = (with_text and text_done < max_pdf
                     and (meta.get("ticker") or meta.get("category") == "기업"))
        if want_text:
            text = fetch_report_text(idx)
            if text:
                text_done += 1
        rec = parse_report(meta, text)
        rec["ingested_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        archive[idx] = rec
        new += 1

    save_archive(config, archive)
    return {"n_total": len(archive), "n_new": new, "n_text": text_done,
            "range": f"{sdate}~{edate}"}


def build_period_views(
    config: Config, *, today: date | None = None
) -> dict[str, Any]:
    """대시보드용: 4개 기간 집계 + 검색 인덱스 생성.

    Returns:
        {trends: {today, yesterday, 7d, 30d}, index: [...간략 레코드...], as_of}.
    """
    archive = load_archive(config)
    reports = list(archive.values())
    ref = today or datetime.now().date()
    trends = {w: aggregate(filter_window(reports, ref, w)) for w in _WINDOWS}

    # 기간별 상위 종목에 현재가 부착(주가도 함께 보여주기)
    tickers = sorted({s["ticker"] for w in trends.values() for s in w["stocks"]
                      if s.get("ticker")})
    if tickers:
        try:
            from src.data.market import fetch_quotes
            quotes = fetch_quotes(config, tickers)
            for w in trends.values():
                for s in w["stocks"]:
                    q = quotes.get(str(s.get("ticker")))
                    if q:
                        s["close"] = q["close"]
                        s["change_pct"] = q["change_pct"]
        except Exception:  # noqa: BLE001
            pass

    index = [{
        "title": r.get("title", ""), "name": r.get("name", ""),
        "ticker": r.get("ticker"), "broker": r.get("broker", ""),
        "date": r.get("date", ""), "category": r.get("category", ""),
        "opinion": r.get("opinion"), "target_price": r.get("target_price"),
        "has_concern": r.get("has_concern", False), "pdf_url": r.get("pdf_url"),
    } for r in sorted(reports, key=lambda x: x.get("date", ""), reverse=True)]
    return {"trends": trends, "index": index, "as_of": ref.strftime("%Y-%m-%d")}


def _us_prices(config: Config) -> dict[str, float]:
    """us_consensus.json 에서 {ticker: 현재가}."""
    path = config.cache_dir / "us_consensus.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        c = json.load(fh)
    return {tk: v["price"] for tk, v in c.items()
            if isinstance(v, dict) and isinstance(v.get("price"), (int, float))}


def _target_stat(records: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any] | None:
    """기간 내 목표가 제시 액션들로 평균 목표가·상승여력 통계 (순수 함수).

    Returns:
        {n, avg_target, avg_upside_pct} 또는 목표가가 없으면 None.
    """
    ups: list[float] = []
    tgts: list[float] = []
    for r in records:
        tp = r.get("target_price")
        if not tp:
            continue
        m = re.search(r"[\d,]+(?:\.\d+)?", str(tp))
        if not m:
            continue
        val = float(m.group(0).replace(",", ""))
        tgts.append(val)
        px = prices.get(r.get("ticker"))
        if px:
            ups.append((val / px - 1) * 100)
    if not tgts:
        return None
    return {
        "n": len(tgts),
        "avg_target": sum(tgts) / len(tgts),
        "avg_upside_pct": (sum(ups) / len(ups)) if ups else None,
    }


def build_us_views(config: Config) -> dict[str, Any]:
    """미국 애널리스트 액션(us_archive.json)으로 기간별 뷰를 만든다.

    yfinance 액션 날짜는 실데이터라, 기간 윈도우 기준일을 '최신 액션 날짜'로 잡아
    오늘/어제/1주/1달이 의미 있게 채워지도록 한다.

    Returns:
        {trends, index, as_of}.
    """
    path = config.cache_dir / "us_archive.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        records = list(json.load(fh).values())
    if not records:
        return {"trends": {}, "index": [], "as_of": ""}

    dates = [r.get("date", "") for r in records if r.get("date")]
    ref = max(datetime.strptime(d, "%Y-%m-%d").date() for d in dates)
    # KR 과 동일: 오늘/어제/1주/한달 (최근 31일만 보관하므로 그 이상은 없음)
    us_windows = ["today", "yesterday", "7d", "30d"]
    prices = _us_prices(config)
    trends = {}
    for w in us_windows:
        win_recs = filter_window(records, ref, w)
        agg = aggregate(win_recs)
        agg["target_stat"] = _target_stat(win_recs, prices)
        trends[w] = agg
    index = [{
        "title": r.get("title", ""), "name": r.get("name", ""),
        "ticker": r.get("ticker"), "broker": r.get("broker", ""),
        "date": r.get("date", ""), "category": r.get("category", ""),
        "opinion": r.get("opinion"), "target_price": r.get("target_price"),
        "has_concern": r.get("has_concern", False), "pdf_url": r.get("pdf_url"),
    } for r in sorted(records, key=lambda x: x.get("date", ""), reverse=True)]
    return {"trends": trends, "index": index, "as_of": ref.strftime("%Y-%m-%d")}


def main() -> None:
    ap = argparse.ArgumentParser(description="리포트 아카이브")
    sub = ap.add_subparsers(dest="cmd")
    ing = sub.add_parser("ingest")
    ing.add_argument("--no-text", action="store_true", help="PDF 본문 다운로드 생략(메타만)")
    ing.add_argument("--lookback", type=int, default=None,
                     help="며칠 전까지 다시 훑어 놓친 날을 채울지(기본 config digest.backfill_days)")
    bf = sub.add_parser("backfill")
    bf.add_argument("--days", type=int, default=30)
    bf.add_argument("--max-pdf", type=int, default=80)
    bf.add_argument("--no-text", action="store_true")
    tr = sub.add_parser("trends")
    tr.add_argument("--window", default="7d", choices=list(_WINDOWS))
    args = ap.parse_args()
    from src.config import load_config

    cfg = load_config()
    if args.cmd == "ingest":
        out = ingest_new_reports(cfg, download_text=not args.no_text,
                                 lookback_days=args.lookback)
        print(f"[archive] {out['range']} 누적 {out['n_total']}건 "
              f"(신규 {out['n_new']}, 본문추출 {out['n_extracted']})")
    elif args.cmd == "backfill":
        out = backfill_archive(cfg, days=args.days, with_text=not args.no_text,
                               max_pdf=args.max_pdf)
        print(f"[backfill] {out['range']} → 누적 {out['n_total']}건 "
              f"(신규 {out['n_new']}, 본문 {out['n_text']})")
    elif args.cmd == "trends":
        from datetime import datetime as _dt
        archive = load_archive(cfg)
        agg = aggregate(filter_window(list(archive.values()), _dt.now().date(), args.window))
        cats = " · ".join(f"{c['category']} {c['count']}" for c in agg["categories"])
        print(f"[{args.window}] 리포트 {agg['n_reports']}건 · {cats}")
        print("많이 언급된 종목:", [(s["name"], s["count"]) for s in agg["stocks"][:5]])
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
