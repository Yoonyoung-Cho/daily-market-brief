# z-score / 반감기 / 백분위 레퍼런스

## 룩어헤드 없는 롤링 z-score
pandas `rolling()` 은 **현재 관측치를 포함**한다. 그대로 쓰면 오늘의 값이
오늘을 표준화하는 통계에 들어가 미래 정보 누수(look-ahead)가 된다.

해결:
```python
roll = metric.rolling(window, min_periods=window)
mean = roll.mean().shift(1)   # 어제까지의 평균
std  = roll.std(ddof=0).shift(1)
z    = (metric - mean) / std
```
- `shift(1)` 로 "직전 window 구간(현재 제외)의 통계"를 사용.
- 앞쪽 `window` 구간은 NaN (정상).

### 검증 (단위테스트)
- 시계열을 t 시점까지 잘라 계산한 z_t 가, 전체 시계열로 계산한 z_t 와 동일해야 함.
- 즉 z_t 는 t 이후 데이터에 의존하지 않는다.

## 반감기 (Ornstein-Uhlenbeck)
평균회귀 속도. 회귀:
```
Δx_t = λ·x_{t-1} + c + e_t
HL = −ln(2) / ln(1 + λ)     # λ < 0 일 때만 유한
```
- λ ≥ 0 → 평균회귀 안 함 → HL = ∞ (랭킹에서 불리).
- HL 이 짧을수록 괴리가 빨리 되돌아옴 → 추천 가산.

## 역사적 백분위
```
percentile = mean(history <= current_value) * 100
```
- 현재 괴리가 역사적으로 얼마나 극단인지. z>0 이면 "상위 (100−pct)%" 로 해석.

## 경제적 해석 문장 예
"우선주 할인율 평소 22% → 현재 31%, z-score +2.4 (상위 3% 수준)으로
평소 대비 매우 크게 벌어짐. 평균회귀 반감기 약 18거래일."

## 엣지 케이스
- std=0 (변동 없음) → z = NaN (0 나눗셈 방지).
- 표본 < window → z 산출 불가, 해석에 "표본 부족" 명시.
- holdco_sub 에서 시총 미가용 시 가격 프록시 사용(상대 변동만 의미).
