# 데일리 마켓 브리핑 (KR + US) — 프로젝트 규약

주식 초심자를 위해 매일 한국·미국 시장 소식을 **알아듣기 쉬운 말로** 요약하는 시스템.
증권사 리포트(한경 컨센서스 본문)와 그날 뉴스를 출처와 함께 정리하고, 잡주는 다루지 않는다.
**투자 자문이 아니다 — 모든 출력에 디스클레이머를 표시한다.**
사양: [SPEC.md](SPEC.md) · 개편 배경/로드맵: [PLAN.md](PLAN.md)

## 실행
```bash
pip install -r requirements.txt
bash scripts/collect.sh                          # 데이터 수집(놓친 날 자동 백필)
/daily-brief                                     # Claude Code: 수집→작성→검증→렌더 한 번에
python -m src.dashboard_pipeline --render        # 렌더만(브리핑 JSON 이 있을 때)
bash scripts/dash.sh                             # LLM 없이 데이터만 갱신 + 열기
pytest -q                                        # 테스트
```
산출물: `data/dashboard.html`(최신), `data/history/YYYY-MM-DD.html`(날짜별), `data/briefs/`.

## 하네스 (의도적으로 작게)
- 에이전트 2개: `brief-writer`(브리핑 작성) · `fact-checker`(검증). 파이썬으로 되는 일은 에이전트를 만들지 않는다.
- 스킬 2개: `daily-brief`(오케스트레이션) · `digest-style`(글쓰기 규칙·형식·도메인 지식).
- 페어 스프레드 시대의 에이전트·스킬은 `.claude/legacy/` 에 보존. 코드(`src/screening`, `src/analysis`, `src/pipeline.py`)는 `features.pairs` 옵션으로만 사용.

## 디렉토리 계약
- `src/data/`  — 수집·캐싱·아카이브 (경계 계층의 I/O). market·consensus·archive·us_analyst
- `src/brief.py` — 브리핑 스키마·검증·저장(최신 + 날짜별)
- `src/dashboard_pipeline.py` — 렌더 오케스트레이션 + 스냅샷
- `src/viz/dashboard.py` — 정적 HTML 렌더(서버·DB 없음)
- `app/` — (보조) Streamlit
- `data/` — 모든 산출물. `history/`·`briefs/`·`*_archive.json` 은 **git 으로 추적**(이것이 히스토리다). PDF 원본은 제외.

## 코드 스타일
- 함수/변수 `snake_case`, 클래스 `PascalCase`. 타입 힌트 필수, Google 스타일 docstring.
- 순수 함수 우선. 파일·네트워크 I/O 는 `src/data`·`dashboard_pipeline`·`app` 에 격리.
- 설정값 하드코딩 금지 — `config.yaml`(`digest.*`, `features.*`).

## 절대 규칙 (신뢰성)
- **출처 없는 항목은 화면에 올리지 않는다.** 수치는 수집 데이터·출처에 있는 값만.
- **잡주 취급 금지**: `digest.min_marcap_*` 미달, 증권사 커버리지 없는 종목은 픽·핫섹터에 넣지 않는다.
- **지수 '주도'는 시총 기여(`index_drivers`) 기준.** % 등락 상위 소형주를 지수 주도로 쓰지 않는다.
- 초심자 문장: 용어는 첫 등장 시 풀어 쓰고, 매수/매도 지시어 대신 "리포트에 따르면".
- (페어 옵션 사용 시) 룩어헤드 편향 금지, 공적분 미검증 쌍 추천 금지.
