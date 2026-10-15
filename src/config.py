"""설정 로딩 — config.yaml 을 읽어 dataclass 로 노출한다.

설정값 하드코딩 금지 원칙에 따라 모든 파라미터는 이 모듈을 통해 접근한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class ScreeningConfig:
    min_correlation: float = 0.80
    coint_pvalue: float = 0.05
    min_overlap_days: int = 252
    max_statistical_pairs: int = 40


@dataclass(frozen=True)
class AnalysisConfig:
    zscore_window: int = 60
    band_sigmas: tuple[float, float] = (1.0, 2.0)
    seed_score_bonus: float = 0.30
    structural_bonus: float = 0.20
    bluechip_marcap: float = 3.0e12


@dataclass(frozen=True)
class CacheConfig:
    dir: str = "data"
    prices_file: str = "prices.parquet"
    ttl_hours: float = 12.0
    max_retries: int = 3
    backoff_seconds: float = 2.0


@dataclass(frozen=True)
class DigestConfig:
    """데일리 브리핑(메인 제품) 설정."""
    min_marcap_krw: float = 1.0e12
    min_marcap_usd: float = 1.0e10
    backfill_days: int = 7
    history_dir: str = "history"
    history_keep: int = 90


@dataclass(frozen=True)
class FeaturesConfig:
    """옵션 기능 토글."""
    pairs: bool = False
    us: bool = True


@dataclass(frozen=True)
class CurrencyConfig:
    """통화 표기 — 시장에 따라 결정(KR=원, US=달러)."""
    code: str = "KRW"
    symbol: str = "₩"
    unit: str = "원"        # 접미 표기용(한국)
    position: str = "suffix"  # "prefix"(미국 $) | "suffix"(한국 원)
    decimals: int = 0


_KRW = CurrencyConfig(code="KRW", symbol="₩", unit="원", position="suffix", decimals=0)
_USD = CurrencyConfig(code="USD", symbol="$", unit="", position="prefix", decimals=2)


@dataclass(frozen=True)
class Config:
    market: str = "KR"
    lookback_days: int = 504
    rolling_window: int = 60
    universe: str = "KOSPI200"
    watchlist_file: str = "watchlist.json"
    screening: ScreeningConfig = field(default_factory=ScreeningConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    digest: DigestConfig = field(default_factory=DigestConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    disclaimer: str = (
        "본 시스템은 참고용 통계 분석 도구이며 투자 자문이 아닙니다. "
        "모든 투자 판단과 손익의 책임은 사용자 본인에게 있습니다."
    )

    @property
    def currency(self) -> CurrencyConfig:
        """시장에 맞는 통화 설정."""
        return _USD if self.market.upper() == "US" else _KRW

    @property
    def cache_dir(self) -> Path:
        """캐시 디렉토리 절대 경로."""
        p = Path(self.cache.dir)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def prices_path(self) -> Path:
        """수정주가 parquet 캐시 경로."""
        return self.cache_dir / self.cache.prices_file

    @property
    def history_dir(self) -> Path:
        """날짜별 대시보드 스냅샷 폴더."""
        return self.cache_dir / self.digest.history_dir

    @property
    def watchlist_path(self) -> Path:
        """포커스 유니버스(워치리스트) 파일 경로."""
        return self.cache_dir / self.watchlist_file

    def format_price(self, value: float) -> str:
        """통화 규칙에 맞춰 가격 문자열을 만든다.

        Args:
            value: 가격 값.

        Returns:
            예) KR -> '70,000원', US -> '$123.45'.
        """
        cur = self.currency
        num = f"{value:,.{cur.decimals}f}"
        if cur.position == "prefix":
            return f"{cur.symbol}{num}"
        return f"{num}{cur.unit}"


def _coerce(raw: dict[str, Any]) -> Config:
    """raw dict -> Config 변환 (중첩 dataclass 포함)."""
    screening = ScreeningConfig(**(raw.get("screening") or {}))
    analysis_raw = dict(raw.get("analysis") or {})
    if "band_sigmas" in analysis_raw:
        analysis_raw["band_sigmas"] = tuple(analysis_raw["band_sigmas"])
    analysis = AnalysisConfig(**analysis_raw)
    cache = CacheConfig(**(raw.get("cache") or {}))
    digest = DigestConfig(**(raw.get("digest") or {}))
    features = FeaturesConfig(**(raw.get("features") or {}))
    return Config(
        market=raw.get("MARKET", "KR"),
        lookback_days=int(raw.get("LOOKBACK_DAYS", 504)),
        rolling_window=int(raw.get("ROLLING_WINDOW", 60)),
        universe=raw.get("UNIVERSE", "KOSPI200"),
        watchlist_file=raw.get("WATCHLIST_FILE", "watchlist.json"),
        screening=screening,
        analysis=analysis,
        cache=cache,
        digest=digest,
        features=features,
        disclaimer=raw.get("DISCLAIMER", Config.disclaimer),
    )


def load_config(path: str | Path | None = None) -> Config:
    """config.yaml 을 읽어 Config 를 반환한다.

    Args:
        path: 설정 파일 경로. None 이면 프로젝트 루트의 config.yaml.

    Returns:
        파싱된 Config 객체. 파일이 없으면 기본값 Config.
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    env_override = os.environ.get("PAIRSPREAD_CONFIG")
    if env_override:
        cfg_path = Path(env_override)
    if not cfg_path.exists():
        return Config()
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _coerce(raw)
