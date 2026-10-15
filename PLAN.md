# 기획 검토 & 개편안 — "초심자용 데일리 마켓 브리핑"

> 2026-09-22 기획 검토. 이 문서는 **왜 이렇게 바꿨는지**와 **다음에 무엇을 할지**를 남긴다.
> 현재 사양은 [SPEC.md](SPEC.md), 사용법은 [README.md](README.md).

## 1. 진단 — 예전 프로젝트의 문제

| 문제 | 원인 | 조치 |
|---|---|---|
| 서브에이전트가 너무 많다(9개) | 페어 스프레드 시대의 파이프라인 단계마다 에이전트를 둠. 그중 6개는 LLM 판단이 필요 없는 **파이썬 코드 실행자**였다 | LLM 판단이 필요한 2개만 남김(`brief-writer`, `fact-checker`). 나머지는 `.claude/legacy/` 로 이동(삭제 아님) |
| 매일 안 돌리면 리포트에 구멍 | 한경 컨센서스 **메인 페이지(당일분)** 만 읽었다 | 매 실행 시 최근 7일 날짜검색으로 자동 백필(`digest.backfill_days`). 하루 빠져도 다음 실행이 채운다 |
| 이전 브리핑을 다시 볼 수 없다 | `dashboard.html` 한 파일을 덮어썼다 | 렌더마다 `data/history/YYYY-MM-DD.html` 스냅샷 + 헤더에 날짜 링크. 브리핑 JSON 도 `data/briefs/{kr,us}/날짜.json` 으로 보존 |
| 목표가 바뀌었는데 문서·하네스는 옛것 | 페어 분석 → 브리핑으로 방향이 바뀌었지만 CLAUDE.md·README·스킬이 페어 기준 | 제품 정의를 "초심자용 데일리 브리핑"으로 재정의. 페어는 옵션 기능(`features.pairs`, 기본 꺼짐) |
| 초심자가 읽기 어렵다 | 화면이 지수·z-score·리포트 메타 중심 | 새 섹션: 🔰 초심자 3줄 요약 · 📰 오늘의 뉴스(무슨 일/왜 중요) · 📖 오늘의 용어. 글쓰기 규칙을 `digest-style` 스킬로 고정 |
| 잡주가 섞인다 | 픽 선정 기준이 없었다 | 시총 하한(`digest.min_marcap_*`) + 증권사 커버리지 요구. 렌더 단계에서도 시총 미달 픽을 자동 제거 |

## 2. DB·서버가 필요한가? → **아니오**

- 데이터 양이 작다(리포트 아카이브 1.2MB, 하루 HTML 1MB). 파일 + git 이 곧 DB 다.
- "언제 들어가도 볼 수 있게"는 두 가지가 충족되면 된다.
  1. **실행이 내 노트북에 묶이지 않는다** → Claude Code **클라우드 예약 작업**(routine)이 매일 `/daily-brief` 를 돌려 결과를 커밋. 노트북 꺼져 있어도 된다.
  2. **결과가 항상 열리는 주소에 있다** → GitHub Pages(정적 호스팅, 무료). `.github/workflows/pages.yml` 이 `dashboard.html` + `history/` 를 배포.
- 필요한 준비: 이 프로젝트를 GitHub 저장소로 올리기(비공개 저장소도 Pages 가능, 유료 플랜 필요. 공개 저장소면 무료 — 단 PDF 원본은 .gitignore 로 제외했다).
- 스트림릿 앱(`app/`)은 유지하되 메인이 아니다. 인터랙티브가 필요할 때만.

## 3. 새 하네스 (2 에이전트 + 2 스킬)

```
/daily-brief (스킬, 오케스트레이션)
  1. scripts/collect.sh          파이썬: KR 지수·컨센서스(7일 백필)·US 애널리스트·뉴스
  2. brief-writer (에이전트)     초심자용 브리핑 KR·US 작성 (digest-style 규칙)
  3. fact-checker (에이전트)     출처·수치·도메인 논리·잡주·가독성 검증 → 교정
  4. src.dashboard_pipeline --render   렌더 + 날짜별 스냅샷
```

- `digest-style` 스킬 = 글쓰기 규칙 + JSON 형식 + 소스 티어 + 도메인 지식(지수 주도=시총 기여 등).
- 페어 관련 에이전트 7개·스킬 6개는 `.claude/legacy/` 에 보존. 다시 쓰려면 폴더만 옮기면 된다.

## 4. 데이터 흐름 (모두 파일)

```
market_kr.json ─┐
report_archive.json (7일 백필) ─┤→ brief-writer → briefing_kr.json ─┐
us_archive.json / us_consensus.json ─┘                 briefing_us.json ─┤→ fact-checker
                                                                        ↓
                                dashboard.html + history/YYYY-MM-DD.html + briefs/{kr,us}/날짜.json
```

## 5. 로드맵

### Phase 1 (이번 개편, 완료)
- 하네스 2+2 로 축소, 문서 재정의, 자동 백필, 날짜별 스냅샷, 초심자 섹션, 잡주 필터, Pages 워크플로.

### Phase 2 — 무인 운영
- [ ] GitHub 저장소 생성 + 첫 커밋 + Pages 활성화(Settings → Pages → Source: GitHub Actions).
- [ ] Claude Code 클라우드 예약 작업: 평일 08:30 KST `/daily-brief` 실행 후 `data/` 변경분 커밋·푸시.
      (로컬 대안: `scripts/com.dailybrief.collect.plist` — LLM 없이 데이터만 갱신)
- [ ] 알림: 브리핑 완료 시 초심자 3줄 요약을 슬랙/메일로 푸시(선택).

### Phase 3 — 월간 픽 (사용자 요청: "매달 1일 어떤 주식이 좋은지")
- [ ] `monthly_picks` 섹션: 매달 1일, 증권사들의 **월간 추천종목·전략 리포트**를 모아
      "이달에 증권사들이 많이 고른 종목"을 초심자 말로 정리. 출처 필수, 매수 지시어 금지.
- [ ] **스코어카드**: 지난달 픽이 실제로 어떻게 됐는지(등락률) 다음 달 1일에 함께 보여줌.
      초심자에게 가장 교육적인 기능. 데이터는 이미 있는 FinanceDataReader/yfinance 로 계산.
- [ ] 사용자가 보던 "IBM 롱숏 리포트"가 정확히 어느 기관의 어떤 리포트인지 확인 필요(§7).

### Phase 4 — 품질
- [ ] 한경 컨센서스 HTML 구조 변경 감지(파싱 0건이면 경고 + 스냅샷 보존).
- [ ] 뉴스 소스를 RSS 로 기계 수집(현재는 brief-writer 의 웹검색 의존).
- [ ] 리포트 한 줄 요약을 `claude -p` 대신 API 호출로 전환(무인 환경에서 안정).

## 6. 비용·시간 가늠

- 수집(파이썬): 1~3분, 무료.
- 브리핑 작성+검증(LLM): 하루 1회, 웹검색 포함 5~10분 상당의 토큰.
- 호스팅: GitHub Pages 무료. 저장소 용량은 하루 ~1MB 증가 → 1년 300MB 수준. 필요하면 history 를 90일로 정리.

## 7. 확인이 필요한 것 (사용자에게)

1. **"IBM 롱숏 리포트"** — IBK투자증권? IM증권? 다른 곳? 어느 기관·리포트명인지 알려주면 Phase 3 월간 픽의 1차 소스로 연결한다.
2. GitHub 저장소를 **공개/비공개** 중 어느 쪽으로 할지(비공개 Pages 는 유료 플랜).
3. 미국 관심 종목(`data/watchlist_us.json`, 현재 M7+AI반도체 15개)을 그대로 둘지, 산업별로 넓힐지.
