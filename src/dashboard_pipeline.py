"""데일리 브리핑 대시보드 오케스트레이션.

기계적 데이터(시장 스냅샷·한경 컨센서스·미국 애널리스트)를 수집하고, LLM(brief-writer)이
채운 브리핑과 리포트 아카이브를 합쳐 dashboard.html 을 렌더한다. 렌더할 때마다
`data/history/YYYY-MM-DD.html` 스냅샷을 남겨 언제 들어와도 지난 브리핑을 볼 수 있다.

흐름:
  1. (파이썬) 수집  ← scripts/collect.sh / 이 CLI --collect
  2. (LLM) brief-writer → briefing_kr.json, briefing_us.json  ← /daily-brief
  3. (파이썬) 렌더 + 스냅샷  ← 이 CLI --render

CLI:
    python -m src.dashboard_pipeline            # 수집 + 렌더
    python -m src.dashboard_pipeline --collect  # 수집만(브리핑 전)
    python -m src.dashboard_pipeline --render   # 렌더만(브리핑 후)
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from src.brief import archive_briefings, filter_unsourced, load_briefing, validate_briefing
from src.config import Config, load_config
from src.data.consensus import fetch_consensus
from src.data.market import fetch_market_snapshot
from src.viz.dashboard import generate_dashboard


def collect_market_data(config: Config, *, force: bool = False) -> dict[str, Any]:
    """시장 스냅샷·컨센서스 수집(기계적 데이터). 네트워크 실패는 비치명적.

    Returns:
        {market, consensus} (실패 시 해당 항목 None).
    """
    try:
        market = fetch_market_snapshot(config, force=force)
    except Exception as exc:  # noqa: BLE001
        market = None
        print(f"[warn] 시장 스냅샷 수집 실패: {exc}")
    try:
        consensus = fetch_consensus(config, force=force)
    except Exception as exc:  # noqa: BLE001
        consensus = None
        print(f"[warn] 한경 컨센서스 수집 실패: {exc}")
    return {"market": market, "consensus": consensus}


def _enrich_picks_with_prices(config: Config, briefing: dict[str, Any]) -> None:
    """브리핑의 주목 종목(notable_stocks)에 현재가·등락·시총을 붙인다.

    티커가 있는 픽만 대상. 네트워크 실패 시 가격 없이 진행(비치명적).
    """
    from src.data.market import fetch_quotes

    tickers = [str(s["ticker"]) for s in briefing.get("notable_stocks", [])
               if s.get("ticker")]
    if not tickers:
        return
    try:
        quotes = fetch_quotes(config, tickers)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 종목 시세 부착 실패: {exc}")
        return
    for s in briefing.get("notable_stocks", []):
        q = quotes.get(str(s.get("ticker")))
        if q:
            s["close"] = q["close"]
            s["change_pct"] = q["change_pct"]
            s["marcap"] = q["marcap"]
            if not s.get("name"):
                s["name"] = q["name"]


def drop_small_caps(briefing: dict[str, Any], min_marcap: float) -> list[str]:
    """시총이 붙은 픽 중 기준 미달(잡주)을 제거한다 (순수 함수, 렌더 직전 안전장치).

    Args:
        briefing: 시세가 부착된 브리핑(in-place 수정).
        min_marcap: 최소 시총.

    Returns:
        제거된 종목명 리스트.
    """
    removed: list[str] = []
    kept: list[dict[str, Any]] = []
    for s in briefing.get("notable_stocks", []):
        mc = s.get("marcap")
        if isinstance(mc, (int, float)) and mc == mc and mc < min_marcap:
            removed.append(str(s.get("name") or s.get("ticker")))
        else:
            kept.append(s)
    briefing["notable_stocks"] = kept
    return removed


def list_history_dates(config: Config) -> list[str]:
    """history 폴더의 날짜별 스냅샷 목록(최신순, 최대 history_keep 개)."""
    hdir = config.history_dir
    if not hdir.exists():
        return []
    dates = sorted((p.stem for p in hdir.glob("????-??-??.html")), reverse=True)
    return dates[: config.digest.history_keep]


def snapshot_dashboard(config: Config, dashboard: Path, as_of: str) -> Path:
    """최신 대시보드를 날짜별 스냅샷으로 복사한다(같은 날은 덮어씀)."""
    hdir = config.history_dir
    hdir.mkdir(parents=True, exist_ok=True)
    dest = hdir / f"{as_of}.html"
    shutil.copyfile(dashboard, dest)
    return dest


def render_dashboard(
    config: Config,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """저장된 데이터로 대시보드를 렌더하고 날짜별 스냅샷을 남긴다.

    Returns:
        {path, snapshot, has_briefing, briefing_check, dropped_small_caps, n_pairs} 요약.
    """
    # 캐시된 것 우선 사용(없으면 수집)
    try:
        market = fetch_market_snapshot(config)
    except Exception:  # noqa: BLE001
        market = None
    try:
        consensus = fetch_consensus(config)
    except Exception:  # noqa: BLE001
        consensus = None

    # LLM 이 직접 쓴 briefing_*.json 을 날짜별 사본으로도 보존
    try:
        archive_briefings(config)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 브리핑 아카이브 실패: {exc}")

    briefing = load_briefing(config, "KR")
    check = (validate_briefing(briefing) if briefing
             else {"ok": False, "errors": ["브리핑 없음"], "n_items": 0, "n_unsourced": 0})
    dropped: list[str] = []
    if briefing:
        briefing = filter_unsourced(briefing)          # 출처 없는 항목은 화면에 안 올림
        _enrich_picks_with_prices(config, briefing)
        dropped = drop_small_caps(briefing, config.digest.min_marcap_krw)

    pairs: list[dict[str, Any]] = []
    if config.features.pairs:
        from src.pipeline import load_analysis
        pairs = load_analysis(config)

    from src.data.archive import build_period_views, build_us_views
    try:
        report_views = build_period_views(config)
    except Exception:  # noqa: BLE001
        report_views = None

    us_views = us_consensus = us_briefing = None
    if config.features.us:
        try:
            us_views = build_us_views(config) or None
        except Exception:  # noqa: BLE001
            us_views = None
        try:
            cpath = config.cache_dir / "us_consensus.json"
            if cpath.exists():
                us_consensus = json.loads(cpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            us_consensus = None
        us_briefing = load_briefing(config, "US")
        if us_briefing:
            us_briefing = filter_unsourced(us_briefing)

    gen = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    as_of = gen[:10]
    # 오늘 스냅샷은 렌더 후 덮어쓰므로 목록에 미리 포함
    history = sorted(set(list_history_dates(config)) | {as_of}, reverse=True)
    path = generate_dashboard(
        config,
        briefing=briefing,
        market_snapshot=market,
        consensus=consensus,
        pairs=pairs,
        report_views=report_views,
        us_views=us_views,
        us_consensus=us_consensus,
        us_briefing=us_briefing,
        generated_at=gen,
        history_dates=history,
        history_dir=config.digest.history_dir,
    )
    snap = snapshot_dashboard(config, path, as_of)
    # 스냅샷 안의 history 링크는 같은 폴더의 형제 파일을 가리켜야 함
    _rewrite_history_links(snap, config.digest.history_dir)
    return {
        "path": str(path),
        "snapshot": str(snap),
        "has_briefing": briefing is not None,
        "briefing_check": check,
        "dropped_small_caps": dropped,
        "n_pairs": len([p for p in pairs if p.get("status") == "ok"]),
    }


def _rewrite_history_links(snapshot: Path, history_dir: str) -> None:
    """스냅샷 HTML 의 'history/DATE.html' 링크를 같은 폴더 상대경로 'DATE.html' 로 바꾼다."""
    text = snapshot.read_text(encoding="utf-8")
    text = text.replace(f'href="{history_dir}/', 'href="')
    snapshot.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="데일리 브리핑 대시보드")
    ap.add_argument("--collect", action="store_true", help="기계적 데이터 수집만")
    ap.add_argument("--render", action="store_true", help="렌더만(수집 생략)")
    ap.add_argument("--force", action="store_true", help="캐시 무시")
    args = ap.parse_args()

    cfg = load_config()
    if not args.render:
        print("[collect] 시장 스냅샷·한경 컨센서스 수집…")
        data = collect_market_data(cfg, force=args.force)
        if data["market"]:
            idx = data["market"].get("indices", {})
            print("  지수:", {k: round(v.get("change_pct", 0), 2) for k, v in idx.items()})
        if data["consensus"]:
            print(f"  컨센서스 리포트: {data['consensus'].get('fetched_n', 0)}건")
    if args.collect:
        print("[done] 수집 완료. 다음: /daily-brief 로 브리핑 작성 → --render")
        return

    summary = render_dashboard(cfg)
    print(f"[dashboard] {summary['path']}  (스냅샷 {summary['snapshot']})")
    if not summary["has_briefing"]:
        print("  ⚠️ 브리핑(briefing_kr.json) 없음 — /daily-brief 로 채우세요. (대시보드는 데이터만 표시)")
    else:
        chk = summary["briefing_check"]
        print(f"  브리핑 항목 {chk['n_items']}개, 출처누락 {chk['n_unsourced']}개, 검증 {'OK' if chk['ok'] else '경고'}")
        if summary["dropped_small_caps"]:
            print(f"  잡주 제외: {', '.join(summary['dropped_small_caps'])}")
    if cfg.features.pairs:
        print(f"  페어 {summary['n_pairs']}개")


if __name__ == "__main__":
    main()
