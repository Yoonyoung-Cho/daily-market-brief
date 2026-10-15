"""리포트 아카이브: 휴리스틱 파서·기간 필터·집계 (순수 함수, 네트워크 없이)."""
from __future__ import annotations

from datetime import date

from src.data.archive import (
    aggregate,
    detect_concern,
    filter_window,
    name_from_title,
    parse_opinion,
    parse_report,
    parse_target_price,
    summarize_excerpt,
    title_thesis,
)


def test_summarize_excerpt():
    # 불릿(■/◼ 등) → 포인트 이어붙임
    text = "주가 및 주요이벤트 재무지표 체크포인트 한컴(030520) ■ AI 매출 89억→360억 전망 ◼ 소버린 AI 확장"
    s = summarize_excerpt(text)
    assert "AI 매출 89억" in s and "체크포인트" not in s
    # 불릿 없고 표/헤더(지표블록)면 빈값
    assert summarize_excerpt("시가총액 855억원 총발행주식수 76,668주 상승여력 -원") == ""
    assert summarize_excerpt("") == ""


def test_summarize_prose():
    from src.data.archive import summarize_prose
    t = "진영(285800) 제목 Company Brief 26.1Q 매출 85억(+15.8% YoY)을 시현하였다. 둘째 문장이다."
    s = summarize_prose(t)
    assert "85억" in s and "Company Brief" not in s
    # 애널리스트/지표 헤더는 버림
    assert summarize_prose("Analyst 홍길동 1234-5678 시가총액 100억 발행주식수 50주") == ""


def test_title_thesis():
    assert title_thesis("현대건설(000720) 원전으로 한 번 더 도약") == "원전으로 한 번 더 도약"
    assert title_thesis("[산업] 조선 업황 점검") == "조선 업황 점검"
    assert title_thesis("제목만 있음") == "제목만 있음"


def test_parse_opinion():
    assert parse_opinion("투자의견 Buy 유지") == "Buy"
    assert parse_opinion("투자의견: 매수") == "Buy"
    assert parse_opinion("투자의견 중립 제시") == "Hold"
    assert parse_opinion("비중확대 의견") is None  # '투자의견' 키워드 없으면 미검출
    assert parse_opinion("특별한 의견 없음") is None


def test_parse_target_price():
    assert parse_target_price("6개월 목표주가 45,000 유지") == "45,000원"
    assert parse_target_price("목표주가: 120000원") == "120000원"
    assert parse_target_price("목표가 없음") is None


def test_detect_concern():
    has, exc = detect_concern("투자포인트는 좋으나 리스크 요인은 경쟁 심화다")
    assert has and "리스크" in exc
    assert detect_concern("전망이 매우 밝다")[0] is False


def test_name_from_title():
    assert name_from_title("이오테크닉스(039030) 공정 다변화") == "이오테크닉스"
    assert name_from_title("[산업] 조선 업황 점검") == ""


def test_parse_report_record():
    meta = {"report_idx": "650210", "date": "2026-06-23", "category": "기업",
            "title": "NH투자증권(005940) 멀티플", "ticker": "005940", "broker": "대신증권",
            "pdf_url": "https://x/650210"}
    text = "투자의견 Buy 유지 6개월 목표주가 45,000 유지. 리스크 요인은 증시 부진."
    rec = parse_report(meta, text)
    assert rec["opinion"] == "Buy"
    assert rec["target_price"] == "45,000원"
    assert rec["has_concern"] is True
    assert rec["name"] == "NH투자증권"


def _sample_archive():
    return [
        {"date": "2026-06-23", "category": "기업", "ticker": "039030", "name": "이오테크닉스",
         "broker": "A", "opinion": "Buy", "target_price": "100,000원", "has_concern": False},
        {"date": "2026-06-23", "category": "기업", "ticker": "039030", "name": "이오테크닉스",
         "broker": "B", "opinion": None, "target_price": None, "has_concern": True,
         "concern_excerpt": "경쟁 심화 우려"},
        {"date": "2026-06-22", "category": "산업", "ticker": None, "name": "",
         "broker": "C", "opinion": "Hold", "target_price": None, "has_concern": False},
    ]


def test_filter_window():
    arr = _sample_archive()
    today = date(2026, 6, 23)
    assert len(filter_window(arr, today, "today")) == 2
    assert len(filter_window(arr, today, "yesterday")) == 1
    assert len(filter_window(arr, today, "7d")) == 3   # 둘 다 7일 내


def test_aggregate():
    agg = aggregate(_sample_archive())
    assert agg["n_reports"] == 3
    # 종목 중심: 039030 이 2회 언급으로 1위, 그 종목의 리포트 2건이 묶임
    assert agg["stocks"][0]["ticker"] == "039030"
    assert agg["stocks"][0]["count"] == 2
    assert len(agg["stocks"][0]["reports"]) == 2
    # 두 번째 리포트엔 우려가 inline 으로 담김
    concerns = [r for r in agg["stocks"][0]["reports"] if r.get("concern_excerpt")]
    assert concerns and "우려" in concerns[0]["concern_excerpt"]
    # 산업 리포트(종목코드 없음)는 industry_reports 로
    assert len(agg["industry_reports"]) == 1
    # 분류 분포 제공
    cats = {c["category"]: c["count"] for c in agg["categories"]}
    assert cats.get("기업") == 2 and cats.get("산업") == 1


def test_build_action_records():
    from src.data.us_analyst import build_action_records
    rows = [
        {"GradeDate": "2026-06-20 10:00:00", "Firm": "Goldman Sachs",
         "ToGrade": "Buy", "FromGrade": "Hold", "Action": "up",
         "priceTargetAction": "Raises", "currentPriceTarget": 250.0, "priorPriceTarget": 200.0},
        {"GradeDate": "2026-06-19 10:00:00", "Firm": "Morgan Stanley",
         "ToGrade": "Underweight", "FromGrade": "Equal-Weight", "Action": "down",
         "priceTargetAction": "Lowers", "currentPriceTarget": 100.0, "priorPriceTarget": 130.0},
    ]
    recs = build_action_records("NVDA", "NVIDIA", "AI반도체", rows)
    assert len(recs) == 2
    up = recs[0]
    assert up["opinion"] == "Buy" and up["target_price"] == "$250"
    assert "상향" in up["llm_summary"] and up["ticker"] == "NVDA"
    down = recs[1]
    assert down["opinion"] == "Sell" and down["has_concern"] is True


def test_llm_summary_prep_apply(tmp_path):
    """prep→apply 파일 기계 로직(순수 I/O). 네트워크·LLM 없이."""
    import json as _j
    from datetime import date as _date
    from src.config import Config
    from src.data import llm_summary as ls
    cfg = Config()
    object.__setattr__(cfg.cache, "dir", str(tmp_path))
    today = _date.today().strftime("%Y-%m-%d")  # prep 은 최근 31일만 대상 → 오늘 날짜로
    arc = {
        "R1": {"ticker": "005930", "name": "삼성전자", "date": today,
               "extracted": True, "text_excerpt": "가" * 200},
        "R2": {"ticker": "000660", "name": "SK하이닉스", "date": today,
               "extracted": True, "text_excerpt": "나" * 200, "llm_summary": "이미있음"},
        "R3": {"ticker": None, "name": "", "date": today,
               "extracted": True, "text_excerpt": "다" * 200},  # 티커없음 → 제외
    }
    (tmp_path / "report_archive.json").write_text(_j.dumps(arc), encoding="utf-8")
    n = ls.prep(cfg)
    assert n == 1  # R1만(R2 이미요약, R3 티커없음)
    inp = _j.loads((tmp_path / "summarize_input.json").read_text(encoding="utf-8"))
    assert inp[0]["report_idx"] == "R1"
    # LLM 출력 모의 → apply
    (tmp_path / "summarize_output.json").write_text(
        _j.dumps({"R1": "삼성전자 실적 개선 기대"}), encoding="utf-8")
    upd = ls.apply(cfg)
    assert upd == 1
    after = _j.loads((tmp_path / "report_archive.json").read_text(encoding="utf-8"))
    assert after["R1"]["llm_summary"] == "삼성전자 실적 개선 기대"
    assert not (tmp_path / "summarize_input.json").exists()  # 정리됨


def test_split_private_keeps_excerpt_out_of_public():
    from src.data.archive import split_private
    rec = parse_report({"report_idx": "1", "title": "삼성전자(005930) 좋다", "authors": "홍길동"},
                       "투자의견 Buy ■ HBM 매출 성장 전망 ■ 리스크 요인은 경쟁")
    public, private = split_private(rec)
    assert "text_excerpt" not in public and "authors" not in public
    assert private["text_excerpt"].startswith("투자의견")
    assert public["opinion"] == "Buy" and public["points"]  # 화면용 요약은 공개 레코드에 남음
