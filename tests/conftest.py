"""테스트용 합성 데이터 픽스처."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng() -> np.random.Generator:
    """결정적 난수 생성기."""
    return np.random.default_rng(42)


@pytest.fixture
def dates() -> pd.DatetimeIndex:
    """504 거래일 인덱스."""
    return pd.bdate_range("2022-01-03", periods=504)


@pytest.fixture
def cointegrated_prices(rng: np.random.Generator, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """알려진 공적분 쌍 (A, B) + 무관한 종목 C.

    logA = α + β·logB + 정상 잔차(OU) 가 되도록 구성.
    """
    n = len(dates)
    # B: 기하 브라운 운동
    log_b = np.cumsum(rng.normal(0, 0.012, n)) + np.log(100)
    # 정상(평균회귀) 잔차 — 노이즈를 작게 두어 로그수익률 상관도 높게 유지
    # (공적분이면서 동시에 return correlation >= 0.8 인 현실적 페어)
    resid = np.zeros(n)
    for t in range(1, n):
        resid[t] = 0.80 * resid[t - 1] + rng.normal(0, 0.003)
    alpha, beta = 0.5, 0.95
    log_a = alpha + beta * log_b + resid
    # C: B 와 무관 + 독립 드리프트 -> 스프레드가 추세를 가져 비정상(비공적분)
    log_c = np.cumsum(rng.normal(0.0008, 0.015, n)) + np.log(50)
    return pd.DataFrame(
        {
            "AAA": np.exp(log_a),
            "BBB": np.exp(log_b),
            "CCC": np.exp(log_c),
        },
        index=dates,
    )


@pytest.fixture
def pref_common_prices(rng: np.random.Generator, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """보통주/우선주 모사: 우선주가 보통주의 약 80% 수준 + 노이즈."""
    n = len(dates)
    common = np.exp(np.cumsum(rng.normal(0.0002, 0.013, n)) + np.log(70000))
    discount = 0.20 + 0.03 * np.sin(np.linspace(0, 6, n)) + rng.normal(0, 0.005, n)
    pref = common * (1 - discount)
    return pd.DataFrame({"005930": common, "005935": pref}, index=dates)
