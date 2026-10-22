#!/usr/bin/env bash
# 데이터 수집(기계적, LLM 없음). 하루 몇 번 돌려도 안전하다(증분·덮어쓰기).
#   - KR: 지수·시총 기여 종목, 한경 컨센서스(최근 N일 자동 백필 → 놓친 날이 채워짐)
#   - US: 애널리스트 등급변경·목표가·컨센서스 + 종목 뉴스(yfinance)
# 이어서 Claude Code 에서 /daily-brief 를 실행하면 브리핑 작성·검증·렌더까지 끝난다.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"   # venv 없으면(클라우드) 시스템 파이썬
LOG="$ROOT/data/collect.log"
mkdir -p "$ROOT/data"

echo "===== collect $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
if [ ! -x "$PY" ]; then echo "파이썬 없음"; exit 1; fi

echo "[1/3] KR 시장 스냅샷 + 한경 컨센서스…"
"$PY" -m src.dashboard_pipeline --collect --force 2>&1 | tee -a "$LOG" || echo "  ⚠️ KR 스냅샷 일부 실패 — 계속"

echo "[2/3] KR 리포트 아카이브 증분 + 최근 며칠 백필…"
"$PY" -m src.data.archive ingest 2>&1 | tee -a "$LOG" || echo "  ⚠️ 아카이브 일부 실패 — 계속"

echo "[3/3] US 애널리스트 액션·컨센서스·뉴스…"
"$PY" -m src.data.us_analyst 2>&1 | tee -a "$LOG" || echo "  ⚠️ US 수집 실패 — 계속"

echo "[collect.sh] 수집 완료. 다음: Claude Code 에서 /daily-brief" | tee -a "$LOG"
