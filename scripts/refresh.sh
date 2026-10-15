#!/usr/bin/env bash
# 매일(평일 장 마감 후) 파이프라인을 재실행해 report.html 을 최신 데이터로 갱신한다.
# launchd 또는 cron 에서 호출. 로그는 data/refresh.log 에 남긴다.
set -euo pipefail

# 이 스크립트(scripts/)의 상위 = 프로젝트 루트
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
LOG="$ROOT/data/refresh.log"

mkdir -p "$ROOT/data"
echo "===== refresh $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"

if [ ! -x "$PY" ]; then
  echo "venv 파이썬을 찾을 수 없습니다: $PY" >> "$LOG"
  exit 1
fi

# --force: 캐시 무시하고 당일 최신 데이터로 재수집·재생성
"$PY" -m src.pipeline --force >> "$LOG" 2>&1
echo "done $(date '+%H:%M:%S')" >> "$LOG"
