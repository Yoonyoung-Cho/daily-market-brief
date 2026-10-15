# 📰 데일리 마켓 브리핑 — 초심자용 (한국 + 미국)

주식을 잘 모르는 사람이 **매일 5분**에 "오늘 무슨 일이 있었고 왜 중요한지"를 알 수 있게,
증권사 리포트(한경 컨센서스 본문)와 그날 뉴스를 쉬운 말로 정리한 대시보드입니다.
잡주는 다루지 않고, 모든 항목에 출처를 붙입니다. 언제 들어와도 **지난 날짜 브리핑**을 볼 수 있습니다.

> ⚠️ **투자 자문이 아닙니다.** 참고용 정보 요약이며 모든 투자 판단과 손익의 책임은 사용자 본인에게 있습니다.

- 사양: [SPEC.md](SPEC.md) · 왜 이렇게 바꿨나/다음 계획: [PLAN.md](PLAN.md)

## 설치
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 매일 쓰는 법 (셋 중 하나)

**A. Claude Code 한 줄 (권장)** — 수집 → 브리핑 작성 → 검증 → 렌더까지
```
/daily-brief
```

**B. LLM 없이 데이터만** — 지수·리포트 동향·컨센서스는 최신, 브리핑 글은 이전 것 유지
```bash
bash scripts/dash.sh
```

**C. 단계별**
```bash
bash scripts/collect.sh                       # 1) 수집(놓친 날 자동 백필)
#   → Claude Code 에서 brief-writer / fact-checker 실행(또는 /daily-brief)
.venv/bin/python -m src.dashboard_pipeline --render   # 3) 렌더 + 날짜별 스냅샷
open data/dashboard.html
```

결과물
- `data/dashboard.html` — 최신 브리핑(자기완결형 HTML, 서버 불필요)
- `data/history/YYYY-MM-DD.html` — 날짜별 스냅샷(헤더의 📅 지난 브리핑에서 이동)
- `data/briefs/{kr,us}/YYYY-MM-DD.json` — 브리핑 원본 보존

## 화면 구성
🔰 초심자 3줄 요약 → 📌 오늘의 한눈에 → 📰 오늘의 뉴스(무슨 일 / 왜 중요) → 📚 기간별 리포트 동향
(오늘·어제·1주·1달, 종목 검색) → 🔥 핫 섹터 → ⭐ 주목 종목(현재가 자동) → 🏦 증권사 뷰 →
📊 등락·시총 / 🎯 컨센서스 → 📖 오늘의 용어. 한국·미국 탭 동일 골격.

## 무인 운영 — 노트북이 꺼져 있어도 매일 갱신 (DB·서버 불필요)
1. 이 폴더를 GitHub 저장소로 올린다(PDF 원본은 .gitignore 로 제외됨).
2. 저장소 Settings → Pages → Source 를 **GitHub Actions** 로. `.github/workflows/pages.yml` 이
   `dashboard.html` + `history/` 를 배포한다 → 고정 URL 에서 언제든 열람.
3. Claude Code **예약 작업(routine)** 을 만들어 평일 08:30 KST 에 `/daily-brief` 를 실행하고
   `data/` 변경분을 커밋·푸시하게 한다. (Claude Code 에서 "매주 평일 8시 30분에 /daily-brief 실행하고 커밋해줘")
4. (로컬 대안) `scripts/com.dailybrief.collect.plist` — 노트북이 켜져 있을 때 LLM 없이 데이터만 갱신.

며칠 실행을 놓쳐도 다음 실행이 최근 `digest.backfill_days`(기본 7일)의 리포트를 다시 훑어 채웁니다.

## 데이터 소스
| 시장 | 소스 | 내용 |
|---|---|---|
| KR | FinanceDataReader(KRX) | 지수, 종목 시세·시총, 시총 기여(지수를 실제로 움직인 종목) |
| KR | 한경 컨센서스 | 증권사 리포트 메타 + PDF 본문 발췌(의견·목표가·논거) |
| US | yfinance | 애널리스트 등급변경·목표가·컨센서스, 종목 뉴스 |
| 공통 | 뉴스 보도 | 그날 화제 뉴스, 글로벌 IB 뷰(원문 유료 → 보도만) |

## 하네스 (Claude Code)
- 에이전트: `brief-writer`(작성) · `fact-checker`(검증) — `.claude/agents/`
- 스킬: `daily-brief`(한 번에 실행) · `digest-style`(글쓰기 규칙·형식·도메인 지식) — `.claude/skills/`
- 예전 페어 스프레드 분석용 에이전트 7개·스킬 6개는 `.claude/legacy/` 에 보존.

## 설정 (`config.yaml`)
```yaml
digest:
  min_marcap_krw: 1.0e+12   # 1조 미만은 픽에서 제외(잡주 차단)
  min_marcap_usd: 1.0e+10
  backfill_days: 7          # 놓친 날 자동 채움 범위
features:
  pairs: false              # 페어 분석 탭(옵션)
  us: true
```

## 옵션: 페어 스프레드 분석
예전 메인 기능. `features.pairs: true` 로 켜고 `PAIRS=1 bash scripts/dash.sh` 또는
`.venv/bin/python -m src.pipeline` 로 갱신하면 대시보드 하단에 표가 붙습니다.
계량 규칙(룩어헤드 금지·공적분 게이트)은 코드·테스트에 그대로 남아 있습니다.

## 테스트
```bash
.venv/bin/python -m pytest -q
```
네트워크 없이 브리핑 검증·출처 필터·잡주 제거·날짜별 저장·대시보드 렌더·컨센서스 파싱을 검증합니다.

## 디렉토리
```
.claude/agents|skills   brief-writer, fact-checker / daily-brief, digest-style
.claude/legacy/         페어 시대 하네스 보존
src/brief.py            브리핑 스키마·검증·저장(최신 + 날짜별)
src/dashboard_pipeline.py 렌더 + 스냅샷
src/data/               market · consensus · archive(백필) · us_analyst · reports · llm_summary
src/viz/dashboard.py    정적 HTML
src/screening, analysis, pipeline.py   (옵션) 페어 분석
scripts/                collect.sh · dash.sh · plist · summarize_prompt.txt
data/                   산출물(dashboard.html, history/, briefs/, *_archive.json …)
tests/
```
