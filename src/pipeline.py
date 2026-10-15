"""오케스트레이터 — 서브에이전트 파이프라인의 코드 구현.

단계별 산출물을 파일로 넘겨 컨텍스트 오염을 방지하는 하네스 구조를 코드로 재현:
  1. data-collector     -> data/prices.parquet
  2. domain-curator     -> data/seed_pairs.json   (이미 큐레이션됨, 로드)
  3. pair-screener      -> data/candidate_pairs.json
  4. divergence-analyst -> data/pair_analysis.json
  5. reporter           -> Streamlit (app/main.py)

CLI:
    python -m src.pipeline [--limit N] [--force]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.analysis.divergence import analyze_pair
from src.analysis.ranking import rank_pairs
from src.config import Config, load_config
from src.data.collector import (
    collect_fundamentals,
    collect_prices,
    load_watchlist,
    market_cap_panel,
    watchlist_names,
)
from src.screening.screener import screen_pairs
from src.screening.seeds import load_seed_pairs
from src.viz.report import generate_report

_CATEGORY = {
    "pref_common": "structural",
    "holdco_sub": "structural",
    "group_chain": "industry",
    "industry_peer": "industry",
    "statistical": "statistical",
}


def _attach_fundamentals(
    analysis: dict[str, Any], fundamentals: dict[str, dict[str, Any]]
) -> None:
    """분석 결과에 두 종목의 시총·PER·우량주 여부·탭 카테고리를 붙인다."""
    fa = fundamentals.get(str(analysis["ticker_a"]), {})
    fb = fundamentals.get(str(analysis["ticker_b"]), {})
    analysis["fund_a"] = fa
    analysis["fund_b"] = fb
    # 두 종목 모두 대형주여야 페어 자체를 '우량주 페어'로 본다
    analysis["is_bluechip"] = bool(fa.get("is_bluechip") and fb.get("is_bluechip"))
    analysis["category"] = _CATEGORY.get(analysis["relationship_type"], "statistical")


def _write_json(path: Path, obj: Any) -> None:
    """JSON 직렬화 후 저장 (NaN 안전)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, default=_json_default)


def _json_default(o: Any) -> Any:
    import numpy as np

    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)


def run_pipeline(
    config: Config | None = None,
    *,
    universe_limit: int | None = None,
    force: bool = False,
    prices: pd.DataFrame | None = None,
    provider: Any = None,
    generated_at_override: str = "",
) -> dict[str, Any]:
    """전체 파이프라인을 실행하고 산출물 경로/요약을 반환한다.

    Args:
        config: Config. None 이면 load_config().
        universe_limit: 유니버스 종목 제한(개발/속도).
        force: 캐시 무시 재수집.
        prices: 가격 패널 주입(테스트용). 주어지면 수집 단계 생략.

    Returns:
        {'n_pairs', 'paths', 'top': [...]} 요약 dict.
    """
    cfg = config or load_config()
    data_dir = cfg.cache_dir
    name_map = watchlist_names(cfg)

    # 1) 수집
    prices_was_collected = prices is None
    if prices is None:
        prices = collect_prices(cfg, provider=provider,
                                universe_limit=universe_limit, force=force)

    # 1b) 펀더멘털(시총·PER) + 시총 시계열 패널.
    #     가격을 외부 주입했고 provider 도 없으면 네트워크를 피해 생략.
    fundamentals: dict[str, Any] = {}
    if provider is not None or prices_was_collected:
        try:
            fundamentals = collect_fundamentals(
                cfg, [str(c) for c in prices.columns],
                provider=provider, force=force,
            )
        except Exception:  # noqa: BLE001 - 펀더멘털 실패는 비치명적
            fundamentals = {}
    cap_panel = market_cap_panel(prices, fundamentals) if fundamentals else None

    # 2) 시드 로드 (domain-curator 산출물)
    seeds = load_seed_pairs()

    # 3) 스크리닝
    candidates = screen_pairs(prices, seeds, cfg)
    _write_json(data_dir / "candidate_pairs.json", candidates)

    # 4) 괴리 분석 (+ 분석가 해석 + 펀더멘털 태깅)
    analyses: list[dict[str, Any]] = []
    for pair in candidates:
        try:
            res = analyze_pair(pair, prices, cfg, market_cap=cap_panel, name_map=name_map)
            _attach_fundamentals(res, fundamentals)
            analyses.append(res)
        except Exception as exc:  # noqa: BLE001 - 개별 쌍 실패는 건너뜀
            analyses.append({**pair, "status": "error", "error": str(exc)})

    ranked = rank_pairs(
        [a for a in analyses if a.get("status") == "ok"],
        seed_bonus=cfg.analysis.seed_score_bonus,
        structural_bonus=cfg.analysis.structural_bonus,
    )
    _write_json(data_dir / "pair_analysis.json", ranked)

    # 5) HTML 리포트 (reporter/designer 산출물)
    generated_at = (generated_at_override
                    or datetime.now().strftime("%Y-%m-%d %H:%M"))
    report_path = generate_report(
        ranked, cfg,
        watchlist=load_watchlist(cfg),
        generated_at=generated_at,
    )

    return {
        "n_candidates": len(candidates),
        "n_analyzed": len(ranked),
        "paths": {
            "prices": str(cfg.prices_path),
            "candidates": str(data_dir / "candidate_pairs.json"),
            "analysis": str(data_dir / "pair_analysis.json"),
            "report": str(report_path),
        },
        "top": [
            {
                "pair": f"{r.get('name_a', r['ticker_a'])}/{r.get('name_b', r['ticker_b'])}",
                "relationship_type": r["relationship_type"],
                "score": round(r["score"], 3),
                "current_zscore": round(r.get("current_zscore", float("nan")), 2),
                "interpretation": r.get("interpretation", ""),
            }
            for r in ranked[:10]
        ],
    }


def load_analysis(config: Config | None = None) -> list[dict[str, Any]]:
    """저장된 pair_analysis.json 을 로드 (Streamlit 등에서 사용).

    Args:
        config: Config.

    Returns:
        랭킹된 분석 리스트. 파일 없으면 빈 리스트.
    """
    cfg = config or load_config()
    path = cfg.cache_dir / "pair_analysis.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    """CLI 진입점."""
    ap = argparse.ArgumentParser(description="페어 스프레드 분석 파이프라인")
    ap.add_argument("--limit", type=int, default=None, help="유니버스 종목 수 제한")
    ap.add_argument("--force", action="store_true", help="캐시 무시 재수집")
    args = ap.parse_args()

    cfg = load_config()
    print(f"[config] MARKET={cfg.market} UNIVERSE={cfg.universe} "
          f"LOOKBACK={cfg.lookback_days} WINDOW={cfg.rolling_window}")
    summary = run_pipeline(cfg, universe_limit=args.limit, force=args.force)
    print(f"[done] 후보 {summary['n_candidates']}쌍, 분석 {summary['n_analyzed']}쌍")
    print(f"[report] {summary['paths']['report']}  (브라우저로 열어보세요)")
    print(f"[paths] {summary['paths']}")
    print("\n[상위 추천]")
    for i, t in enumerate(summary["top"], 1):
        print(f" {i:>2}. {t['pair']} ({t['relationship_type']}) "
              f"score={t['score']} z={t['current_zscore']}")
        print(f"     {t['interpretation']}")
    print(f"\n※ {cfg.disclaimer}")


if __name__ == "__main__":
    main()
