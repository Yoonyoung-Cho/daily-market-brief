"""LLM 한 줄 요약 자동화 (헤드리스 claude 연동).

흐름(파이프라인, dash.sh/daily-brief 에서 호출):
  1. prep  : llm_summary 가 없는 최근 리포트를 골라 data/summarize_input.json 작성
  2. claude -p : 그 입력을 읽고 종목별 한 줄 요약을 data/summarize_output.json 에 작성
  3. apply : 출력을 report_archive.json / us_archive.json 의 llm_summary 에 반영

prep/apply 는 순수 파일 I/O 라 테스트 가능. LLM 호출(2단계)만 외부.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import Config, load_config

_ARCHIVES = ("report_archive.json", "us_archive.json")
INPUT_NAME = "summarize_input.json"
OUTPUT_NAME = "summarize_output.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def prep(config: Config, *, days: int = 31, max_items: int = 40,
         min_excerpt: int = 120) -> int:
    """요약이 필요한 최근 리포트를 골라 입력 JSON 작성.

    조건: 최근 `days` 일 · 본문 추출됨 · llm_summary 없음 · 본문 길이 충분.
    비용 제한을 위해 max_items 로 상한.

    Returns:
        선정된 리포트 수.
    """
    cutoff = (datetime.now().date() - timedelta(days=days)).strftime("%Y-%m-%d")
    items: list[dict[str, Any]] = []
    excerpts = _load(config.cache_dir / "report_excerpts.json")  # 본문 발췌(로컬 전용)
    for name in _ARCHIVES:
        arc = _load(config.cache_dir / name)
        for idx, r in arc.items():
            if r.get("llm_summary"):
                continue
            if not r.get("extracted") or not r.get("ticker"):
                continue  # 카드에 노출되는 종목 리포트만(산업·마켓 리포트 제외)
            if (r.get("date") or "") < cutoff:
                continue
            txt = excerpts.get(idx) or r.get("text_excerpt") or ""
            if len(txt) < min_excerpt:
                continue
            items.append({
                "report_idx": idx,
                "name": r.get("name", ""),
                "broker": r.get("broker", ""),
                "excerpt": txt[:1000],
            })
    # 최신 우선 정렬 후 상한
    items.sort(key=lambda x: x["report_idx"], reverse=True)
    items = items[:max_items]
    out = config.cache_dir / INPUT_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    # 이전 출력 제거(스테일 방지)
    (config.cache_dir / OUTPUT_NAME).unlink(missing_ok=True)
    return len(items)


def apply(config: Config) -> int:
    """LLM 출력(summarize_output.json)을 아카이브 llm_summary 에 반영.

    Returns:
        갱신된 리포트 수.
    """
    out = _load(config.cache_dir / OUTPUT_NAME)
    if not out:
        return 0
    updated = 0
    for name in _ARCHIVES:
        path = config.cache_dir / name
        arc = _load(path)
        changed = False
        for idx, summ in out.items():
            if idx in arc and isinstance(summ, str) and summ.strip():
                arc[idx]["llm_summary"] = summ.strip()[:180]
                changed = True
                updated += 1
        if changed:
            with path.open("w", encoding="utf-8") as fh:
                json.dump(arc, fh, ensure_ascii=False, indent=2)
    # 임시 파일 정리
    (config.cache_dir / INPUT_NAME).unlink(missing_ok=True)
    (config.cache_dir / OUTPUT_NAME).unlink(missing_ok=True)
    return updated


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 한 줄 요약 prep/apply")
    ap.add_argument("cmd", choices=["prep", "apply"])
    args = ap.parse_args()
    cfg = load_config()
    if args.cmd == "prep":
        n = prep(cfg)
        print(n)  # dash.sh 가 개수로 분기
    else:
        print(f"[llm_summary] {apply(cfg)}건 반영")


if __name__ == "__main__":
    main()
