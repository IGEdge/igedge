"""
Neutral backtest harness helpers for the US500/IG work — a historical kline
provider + candle builder, decoupled from any crypto (Deribit/Binance) code so
the US500 backtests stand on their own.

HistoricalKlineProvider serves closed 1h/1d bars as of an advancing simulation
clock, matching the live KlineProvider interface (get_klines/now_ms) so the
REAL strategy classes run identically live and in backtest.
"""
import numpy as np
import pandas as pd


class HistoricalKlineProvider:
    """Serves closed bars per interval as of `current_ms` (data-driven clock)."""

    def __init__(self, h1_candles, d1_candles, funding: pd.Series = None):
        self.frames = {"1h": h1_candles, "1d": d1_candles}
        self.close_ts = {
            k: np.array([c["close_ts_ms"] for c in v]) if v else np.array([])
            for k, v in self.frames.items()
        }
        if funding is None or len(funding) == 0:
            self.funding_ts = np.array([0])
            self.funding_rates = np.array([0.0])
        else:
            self.funding_ts = funding.index.view("int64") // 10**6
            self.funding_rates = funding.values
        self.current_ms = 0

    def get_klines(self, symbol, interval="1h", limit=60):
        frame = self.frames.get(interval)
        if not frame:
            return []
        i = int(np.searchsorted(self.close_ts[interval], self.current_ms, side="right"))
        return frame[max(0, i - limit):i]

    def get_funding_rate(self, symbol):
        i = int(np.searchsorted(self.funding_ts, self.current_ms, side="right"))
        return float(self.funding_rates[i - 1]) if i > 0 else None

    def now_ms(self):
        return self.current_ms


def build_candles(frame: pd.DataFrame, interval_ms: int):
    """DataFrame(open/high/low/close/vol[/buy_vol/buy_ratio]) -> candle dicts."""
    candles = []
    for ts, row in frame.iterrows():
        ts_ms = int(ts.value // 10**6)
        candles.append({
            "ts_ms": ts_ms,
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"],
            "volume": row.get("vol", 0.0),
            "buy_volume": row.get("buy_vol", 0.0),
            "buy_ratio": row.get("buy_ratio", 0.5),
            "close_ts_ms": ts_ms + interval_ms,
        })
    return candles
