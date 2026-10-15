# 큐레이션된 시드 페어 목록

`data/seed_pairs.json` 의 사람이 읽는 버전. 변경 시 양쪽을 함께 갱신한다.

| ticker_a | name_a | ticker_b | name_b | relationship_type | mechanism |
|---|---|---|---|---|---|
| 005930 | 삼성전자 | 005935 | 삼성전자우 | pref_common | 의결권 없는 우선주 할인 |
| 005380 | 현대차 | 005385 | 현대차우 | pref_common | 의결권 없는 우선주 할인 |
| 051910 | LG화학 | 051915 | LG화학우 | pref_common | 의결권 없는 우선주 할인 |
| 034730 | SK | 402340 | SK스퀘어 | holdco_sub | 지주사 NAV 디스카운트 |
| 402340 | SK스퀘어 | 000660 | SK하이닉스 | holdco_sub | 지주사 NAV 디스카운트 |
| 003550 | LG | 066570 | LG전자 | holdco_sub | 지주사 NAV 디스카운트 |
| 005380 | 현대차 | 000270 | 기아 | group_chain | 그룹 완성차 밸류체인 |
| 000660 | SK하이닉스 | 005930 | 삼성전자 | industry_peer | 메모리 반도체 사이클 |
| 035420 | NAVER | 035720 | 카카오 | industry_peer | 국내 플랫폼 동조 |

## 갱신 체크리스트
- [ ] holdco_sub 의 `stake_pct`, `net_debt` 를 최신 공시로 채웠는가?
- [ ] 합병/지주사 전환/지분 매각으로 끊긴 관계는 제거/강등했는가?
- [ ] pref_common 의 ticker 순서(보통주→우선주)가 맞는가?
- [ ] placeholder/미검증 항목을 남기지 않았는가? (로더가 자동 배제)
