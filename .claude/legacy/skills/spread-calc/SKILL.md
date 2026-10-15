---
name: spread-calc
description: 관계유형별 괴리지표와 z-score, 반감기, 백분위를 계산한다. 괴리율 정량화가 필요할 때 사용.
---
# 괴리(Divergence) 계산 (spread-calc)

## 관계유형별 원지표
- `pref_common` → 우선주 할인율 `1 − P_pref/P_common`
- `holdco_sub`  → NAV 디스카운트 `1 − 지주사시총/(자회사시총×지분율 − 순부채)`
- 그 외          → OLS 스프레드: `logP_A = α + β·logP_B + ε`, spread = `logP_A − β·logP_B`

## 표준화 절차
1. 위 원지표 시계열 산출.
2. **룩어헤드 없는** 롤링 z-score:
   `z_t = (x_t − mean(x_{t-window..t-1})) / std(...)` — rolling 후 `shift(1)`.
3. 반감기: OU 회귀 `Δx_t = λ·x_{t-1} + c` 에서 `HL = −ln2 / ln(1+λ)` (λ<0 일 때).
4. 역사적 백분위: 현재값 이하 과거 관측 비율 × 100.

## 핵심 규칙 ★
- **룩어헤드 편향 금지**: 통계는 해당 시점 *이전* 데이터만. (shift(1) 필수)
- 미래 데이터를 제거해도 과거 신호가 동일해야 한다(단위테스트로 검증).

자세한 수식·엣지케이스는 reference/zscore_halflife.md 참조.
