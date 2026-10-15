# 명세 v2 — 초심자용 데일리 마켓 브리핑 (KR + US)

> 본 시스템은 참고용 정보 요약 도구이며 **투자 자문이 아니다.** 모든 화면에 디스클레이머 표시.
> 개편 배경·로드맵은 [PLAN.md](PLAN.md).

## 1. 제품 정의
주식을 잘 모르는 사용자가 **매일 5분** 안에 "오늘 무슨 일이 있었고 왜 중요한지"를 알 수 있는
브리핑. 한국·미국 두 탭. 증권사 리포트(한경 컨센서스 본문)와 그날 화제 뉴스를 초심자 말로 풀고,
잡주는 다루지 않는다. 언제 들어와도 **지난 날짜 브리핑**을 볼 수 있다.

## 2. 사용자 흐름
- **매일(무인)**: 예약 작업이 `/daily-brief` 실행 → 커밋 → GitHub Pages 갱신.
- **수동**: Claude Code 에서 `/daily-brief` 한 줄. 또는 LLM 없이 `bash scripts/dash.sh`.
- **열람**: `data/dashboard.html`(최신) / `data/history/YYYY-MM-DD.html`(과거) / Pages URL.

## 3. 화면 (탭별 동일 골격)
1. 지수 바(KR) · 🔰 **초심자 3줄 요약** (지수 / 리포트·섹터 / ⚠️주의)
2. 📌 오늘의 한눈에(지수 실데이터 + 리서치 코멘트)
3. 📰 **오늘의 뉴스** — 무슨 일 / 💡 왜 중요 / 출처
4. 📚 기간별 리포트 동향(오늘·어제·1주·1달) + 종목 검색
5. 🔥 핫 섹터 · ⭐ 주목 종목(시총·커버리지 기준 통과분만, 현재가 자동 부착)
6. 🏦 증권사 뷰 · 📊 등락·시총(KR) / 🎯 컨센서스(US)
7. 📖 **오늘의 용어**
8. (옵션 `features.pairs`) 🔗 페어 분석
헤더: 📅 지난 브리핑 날짜 링크.

## 4. 데이터 계약 (파일)
| 파일 | 생성자 | 내용 |
|---|---|---|
| `data/market_kr.json` | `src/data/market.py` | 지수·시총 기여(index_drivers)·등락·시총 상위 |
| `data/consensus_kr.json` | `src/data/consensus.py` | 한경 컨센서스 당일 메타 |
| `data/report_archive.json` | `src/data/archive.py` | 리포트 누적(본문 발췌·의견·목표가). **최근 `backfill_days` 자동 백필** |
| `data/us_archive.json`, `us_consensus.json` | `src/data/us_analyst.py` | yfinance 애널리스트 액션·뉴스·컨센서스 |
| `data/briefing_{kr,us}.json` | **brief-writer** (LLM) | `src/brief.py:BRIEFING_SCHEMA` |
| `data/briefs/{kr,us}/DATE.json` | `src/brief.py` | 브리핑 날짜별 사본 |
| `data/dashboard.html` | `src/viz/dashboard.py` | 최신 대시보드 |
| `data/history/DATE.html` | `src/dashboard_pipeline.py` | 날짜별 스냅샷 |

브리핑 스키마 주요 섹션: `plain_summary[3]`, `market_tone`, `news[]`, `hot_sectors[]`,
`notable_stocks[]`(ticker 필수), `key_reports[]`, `broker_views[]`, `glossary[]`.
출처 필수 섹션: news·hot_sectors·notable_stocks·broker_views·key_reports.

## 5. 하네스
- 에이전트: `brief-writer`(작성), `fact-checker`(검증). `.claude/agents/`
- 스킬: `daily-brief`(오케스트레이션), `digest-style`(규칙·형식·도메인 지식). `.claude/skills/`
- 페어 시대 에이전트·스킬은 `.claude/legacy/` 보존.

## 6. 신뢰성 요건
- 출처 URL 없는 항목은 저장돼도 **렌더가 표시하지 않는다**(`filter_unsourced`).
- 수치는 수집 데이터·출처에 있는 값만. LLM 생성 숫자 금지.
- 지수 등락 '주도' 표현은 시총 기여(`index_drivers`) 근거로만.
- 잡주 차단: `digest.min_marcap_krw/usd` 미달 픽은 렌더에서 제거(`drop_small_caps`).
- IB 원문은 유료 → 뉴스 보도 뷰만, '원문 아님' 명시. 매수/매도 지시어 금지.
- 티어 배지: consensus · market_data · analyst_data · ib_news · news · llm.

## 7. 설정 (`config.yaml`)
`digest.{min_marcap_krw, min_marcap_usd, backfill_days, history_dir, history_keep}`,
`features.{pairs, us}`. 페어 관련 값은 옵션 기능용으로 유지.

## 8. 테스트
- 네트워크 없이: 브리핑 검증·출처 필터·잡주 제거·날짜별 저장·스냅샷 목록·대시보드 섹션 렌더
  (`tests/test_digest.py`), 컨센서스 파싱·시장 집계(`tests/test_dashboard.py`), 아카이브 파서·집계.
- 회귀: 페어 테스트 유지(옵션 기능).

## 9. 한계 & 다음
- 브리핑 본문은 LLM 단계 → 무인화는 클라우드 예약 작업으로(PLAN §5 Phase 2).
- 뉴스 수집은 현재 brief-writer 의 웹검색 의존(Phase 4 에서 RSS 기계 수집).
- 월간 픽·스코어카드는 Phase 3.
