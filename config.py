"""
Configuration for the IG (CFD US500) conversion.

Only the two strategies still under US500 validation keep a config dataclass
(Macro Core, Trend Breakdown). Crypto/Deribit strategy configs were removed in
the cleanup — see docs/IG_CONVERSION.md. Defaults still carry the crypto field
shape (symbol/instrument) but are irrelevant in backtest (the injected
HistoricalKlineProvider ignores the symbol); they will map to the IG epic when
the live adapter is built.
"""
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class StrategyConfig:
    """Base configuration for any strategy."""
    name: str
    enabled: bool = True


@dataclass
class TrendBreakdownConfig(StrategyConfig):
    """Two-sided, macro-gated trend strategy (48h-low breakdown shorts in macro
    bear; 7d-high breakout longs in macro bull). Under US500 validation with
    flow_confirm neutralised (US500 has no taker-flow gate)."""
    symbol: str = "US500"
    instrument: str = "IX.D.SPTRD.IFE.IP"
    lookback_h: int = 48
    lookback_long_h: int = 168
    sma_h: int = 48
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    rr_ratio: float = 2.0
    rr_long: float = 0.0          # 0 = no TP for longs (let winners run)
    max_hold_hours: int = 24
    max_hold_long_hours: int = 168
    flow_confirm: float = 0.50    # 1.0 in US500 backtest = gate disabled
    enable_long: bool = True
    enable_short: bool = True
    macro_sma_days: int = 200


@dataclass
class MacroCoreConfig(StrategyConfig):
    """Regime-following long core: long above SMA200d, chandelier exit at
    k*ATR20d. FAILED US500 validation (see docs/IG_CONVERSION.md) — kept for
    reference/experiments only."""
    symbol: str = "US500"
    instrument: str = "IX.D.SPTRD.IFE.IP"
    sma_days: int = 200
    atr_days: int = 20
    chandelier_k: float = 5.0
    disaster_sl_pct: float = 0.25
    exposure_fraction: float = 1.0
    vol_target: float = 0.30
    vol_lookback_days: int = 30
    expo_step: float = 0.25
    state_path: str = "data/macro_core_state.json"
    persist_state: bool = True


class Config:
    """Global IG configuration (populated from .env)."""

    IG_API_KEY: str = os.getenv("IG_API_KEY", "")
    IG_IDENTIFIER: str = os.getenv("IG_IDENTIFIER", "")
    IG_PASSWORD: str = os.getenv("IG_PASSWORD", "")
    IG_ACC_TYPE: str = os.getenv("IG_ACC_TYPE", "DEMO")
    IG_ACCOUNT_ID: Optional[str] = os.getenv("IG_ACCOUNT_ID") or None
    IG_EPIC: str = os.getenv("IG_EPIC", "IX.D.SPTRD.IFE.IP")

    INITIAL_EQUITY: float = float(os.getenv("INITIAL_EQUITY", 10000))
    BASE_RISK_PCT: float = float(os.getenv("BASE_RISK_PCT", 0.01))
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", 0.03))
    MAX_OPEN_TRADES: int = int(os.getenv("MAX_OPEN_TRADES", 3))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> bool:
        missing = [k for k in ("IG_API_KEY", "IG_IDENTIFIER", "IG_PASSWORD")
                   if not getattr(cls, k)]
        if missing:
            for k in missing:
                print(f"❌ Config error: {k} is required in .env")
            return False
        return True
