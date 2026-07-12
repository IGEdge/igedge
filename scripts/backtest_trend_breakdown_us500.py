#!/usr/bin/env python3
"""
Event-driven backtest of the REAL TrendBreakdownStrategy on US500, driving the
actual src/strategies/trend_breakdown.py through the injected
HistoricalKlineProvider — hourly entries + daily macro gate.

Data:
  - HOURLY bars from Dukascopy  (data/research/us500_h1.csv)  → entries/exits
  - DAILY bars from IG          (data/research/us500_daily.csv) → SMA200 macro
    gate (IG daily spans 2007+, so the gate is valid from the very first
    hourly bar; both feeds are the same S&P 500 index at the same scale)

FLOW GATE DISABLED: TB's `buy_ratio < flow_confirm` gate uses Binance taker
volume, which US500 has no equivalent of. We set flow_confirm=1.0 so both
sides' flow conditions always pass (buy_ratio is a constant 0.5) — i.e. we test
the pure breakout+macro logic, as the idea doc prescribes.

CFD cost model (short holds → financing is small but modelled):
  net = d*gross - spread_pts/entry - financing_bps_day * days_held

Usage:
  python scripts/backtest_trend_breakdown_us500.py
  python scripts/backtest_trend_breakdown_us500.py --gross
  python scripts/backtest_trend_breakdown_us500.py --spread-pts 1.0 --fin-bps-day 1.5
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd

from _us500_lib import HistoricalKlineProvider, build_candles
from src.strategies.trend_breakdown import TrendBreakdownStrategy
from config import TrendBreakdownConfig

H1_CSV = "data/research/us500_h1.csv"
D1_CSV = "data/research/us500_daily.csv"
HOUR_MS = 3_600_000
DAY_MS = 86_400_000


def _load(path):
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df.rename(columns={"volume": "vol"})
    df["buy_vol"] = 0.0
    df["buy_ratio"] = 0.5
    return df[["open", "high", "low", "close", "vol", "buy_vol", "buy_ratio"]]


class FakeClient:
    """TB only calls client.sell/buy for reduce-only time exits; we handle
    exits in the harness, so these are inert."""
    def sell(self, *a, **k):
        return {"order_id": "sim"}

    def buy(self, *a, **k):
        return {"order_id": "sim"}


def run(h1, d1, spread_pts, fin_bps_day):
    provider = HistoricalKlineProvider(
        build_candles(h1, HOUR_MS), build_candles(d1, DAY_MS),
        pd.Series([0.0], index=[h1.index[0]]))

    # flow_confirm=1.0 neutralises the taker-flow gate (no US500 equivalent)
    cfg = TrendBreakdownConfig(name="Trend Breakdown", flow_confirm=1.0)
    deps = {k: None for k in ["order_manager", "position_monitor",
                              "risk_manager", "orderflow_engine",
                              "regime_detector", "scoring_engine", "signal_log"]}
    deps["kline_provider"] = provider
    strat = TrendBreakdownStrategy(client=FakeClient(), config=cfg, dependencies=deps)

    ts = h1.index.values.astype("int64") // 10**6
    opens, highs = h1["open"].values, h1["high"].values
    lows, closes = h1["low"].values, h1["close"].values
    n = len(h1)
    fin = fin_bps_day / 10_000.0

    open_tr = None
    trades = []

    for i in range(n):
        provider.current_ms = int(ts[i]) + HOUR_MS  # this hour has closed

        # ---- manage open trade intrabar (SL priority over TP) ----
        if open_tr is not None:
            d = open_tr["d"]
            exit_px, reason = None, None
            if d < 0:   # short
                if highs[i] >= open_tr["sl"]:
                    exit_px, reason = open_tr["sl"], "sl"
                elif open_tr["tp"] > 0 and lows[i] <= open_tr["tp"]:
                    exit_px, reason = open_tr["tp"], "tp"
            else:       # long
                if lows[i] <= open_tr["sl"]:
                    exit_px, reason = open_tr["sl"], "sl"
                elif open_tr["tp"] > 0 and highs[i] >= open_tr["tp"]:
                    exit_px, reason = open_tr["tp"], "tp"
            if exit_px is None and (int(ts[i]) + HOUR_MS - open_tr["entry_ms"]) \
                    >= open_tr["max_hold_min"] * 60_000:
                exit_px, reason = closes[i], "time"
            if exit_px is not None:
                days = (int(ts[i]) + HOUR_MS - open_tr["entry_ms"]) / DAY_MS
                gross = d * (exit_px - open_tr["entry"]) / open_tr["entry"]
                net = gross - spread_pts / open_tr["entry"] - fin * days
                risk = abs(open_tr["entry"] - open_tr["sl"])
                trades.append({
                    "entry_ts": pd.Timestamp(open_tr["entry_ms"], unit="ms", tz="UTC"),
                    "exit_ts": pd.Timestamp(int(ts[i]) + HOUR_MS, unit="ms", tz="UTC"),
                    "side": "LONG" if d > 0 else "SHORT",
                    "entry": open_tr["entry"], "exit": exit_px, "reason": reason,
                    "gross_pct": gross * 100, "net_pct": net * 100,
                    "r": (d * (exit_px - open_tr["entry"]) / risk) if risk > 0 else 0,
                    "days": days,
                })
                open_tr = None
                strat._open_trade = None

        # ---- scan once per closed hourly bar; enter next bar open ----
        if open_tr is None and i + 1 < n:
            signals = strat.scan()
            if signals:
                sig = signals[0]
                d = -1 if sig["direction"] == "SELL" else 1
                entry = opens[i + 1]
                entry_ms = int(ts[i + 1])
                open_tr = {"d": d, "entry": entry, "entry_ms": entry_ms,
                           "sl": sig["stop_loss"], "tp": sig.get("take_profit") or 0,
                           "max_hold_min": sig.get("max_hold_min", 24 * 60)}
                strat._open_trade = {
                    "entry_ts_ms": entry_ms, "quantity": 10,
                    "direction": "sell" if d < 0 else "buy", "entry_price": entry,
                    "max_hold_min": open_tr["max_hold_min"]}
                strat._last_signal_bar_ts = sig["bar_ts_ms"]

    return pd.DataFrame(trades)


def _pf(net):
    up, dn = net[net > 0].sum(), abs(net[net < 0].sum())
    return up / dn if dn > 0 else float("inf")


def report(t, side_filter=None):
    sub = t if side_filter is None else t[t["side"] == side_filter]
    if len(sub) == 0:
        return f"N=0"
    net = sub["net_pct"]
    return (f"N={len(sub):4d}  WR={(net > 0).mean() * 100:4.0f}%  "
            f"avg={net.mean() * 100:+6.1f}bps  PF={_pf(net):4.2f}  "
            f"sum={net.sum():+7.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--fin-bps-day", type=float, default=1.5)
    ap.add_argument("--gross", action="store_true")
    args = ap.parse_args()

    for p in (H1_CSV, D1_CSV):
        if not os.path.exists(p):
            print(f"❌ {p} not found")
            return 1

    h1, d1 = _load(H1_CSV), _load(D1_CSV)
    print(f"US500 hourly: {h1.index[0]} → {h1.index[-1]}  ({len(h1):,} bars)")
    print(f"US500 daily : {d1.index[0].date()} → {d1.index[-1].date()}  "
          f"({len(d1):,} bars, macro gate)")

    spread = 0.0 if args.gross else args.spread_pts
    fin = 0.0 if args.gross else args.fin_bps_day
    t = run(h1, d1, spread, fin)

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt, fin {args.fin_bps_day}bps/d)"
    print(f"\n=== TREND BREAKDOWN — US500 hourly, real code, flow-gate OFF — {tag} ===")
    if len(t) == 0:
        print("  no trades")
        return 0
    equity = (1 + t["net_pct"] / 100).prod()
    print(f"  ALL  : {report(t)}")
    print(f"  LONG : {report(t, 'LONG')}")
    print(f"  SHORT: {report(t, 'SHORT')}")
    print(f"  Compounded: {(equity - 1) * 100:+.1f}%   avg hold {t['days'].mean():.1f}d")
    print(f"  exits: {t['reason'].value_counts().to_dict()}")
    yr = t.groupby(t['entry_ts'].dt.year)['net_pct'].agg(['count', 'sum'])
    print("  years: " + "  ".join(f"{y}:{int(c)}tr/{s:+.0f}%"
                                  for y, (c, s) in yr.iterrows()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
