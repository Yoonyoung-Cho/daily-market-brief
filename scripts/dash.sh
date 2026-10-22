#!/usr/bin/env bash
# 한 줄 실행(LLM 브리핑 없이): 수집 + (있으면) 리포트 한 줄 요약 + 대시보드 렌더 + 열기.
#   사용: bash scripts/dash.sh
# 브리핑 본문(초심자 3줄·뉴스·주목 종목)은 LLM 단계라 Claude Code 의 /daily-brief 로 채운다.
# 이 스크립트는 "데이터만이라도 최신으로" 볼 때, 또는 cron/launchd 무인 실행용.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"   # venv 없으면(클라우드) 시스템 파이썬
DASH="$ROOT/data/dashboard.html"

bash "$ROOT/scripts/collect.sh"

# 페어 분석은 옵션(config features.pairs). PAIRS=1 로 강제 실행 가능.
if [ "${PAIRS:-0}" = "1" ]; then
  echo "[opt] 페어 분석 갱신…"
  "$PY" -m src.pipeline --force || echo "  ⚠️ 페어 갱신 실패 — 계속"
fi

echo "[llm] 리포트 한 줄 요약 (헤드리스 claude, 있으면)…"
if command -v claude >/dev/null 2>&1; then
  N="$("$PY" -m src.data.llm_summary prep 2>/dev/null | tail -1)"
  if [ "${N:-0}" -gt 0 ] 2>/dev/null; then
    echo "  요약 대상 ${N}건 → claude 생성 중…"
    claude -p "$(cat "$ROOT/scripts/summarize_prompt.txt")" --permission-mode acceptEdits >/dev/null 2>&1 \
      && "$PY" -m src.data.llm_summary apply \
      || echo "  ⚠️ LLM 요약 실패 — 휴리스틱 본문 요약으로 대체(정상 동작)"
  else
    echo "  새로 요약할 리포트 없음"
  fi
else
  echo "  claude CLI 없음 → 휴리스틱 본문 요약 사용"
fi

echo "[render] 대시보드 렌더 + 날짜별 스냅샷…"
"$PY" -m src.dashboard_pipeline --render || { echo "  ❌ 대시보드 렌더 실패"; exit 1; }

if [ "${NO_OPEN:-0}" != "1" ]; then
  if command -v open >/dev/null 2>&1; then open "$DASH"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$DASH"
  else echo "  브라우저로 직접 여세요: $DASH"; fi
fi
echo "✅ 완료 → $DASH"
