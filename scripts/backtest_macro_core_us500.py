#!/usr/bin/env python3
"""
Event-driven backtest of the REAL MacroCoreStrategy on US500 DAILY data from
IG, driving scan() + manage_positions() (chandelier exit) through the injected
HistoricalKlineProvider — the same "run the real code, not a reimplementation"
principle as the BTC harness, adapted to daily-only data.

Why daily-native (not the 1m BTC harness): Macro Core is a hold-for-months
trend follower; intrabar precision within a day is irrelevant. Entries/exits
fill at the NEXT daily open; the disaster stop is checked on the daily low.

CFD COST MODEL (this is where IG differs from Deribit — no inverse funding,
but a bid/ask spread in index points AND overnight financing on the long):
  net = gross_return  -  spread_pts/entry  -  financing_bps_per_day * days_held
Defaults are conservative IG-ish values; tune with the CLI flags and watch how
much of the gross edge survives.

Usage:
  python scripts/backtest_macro_core_us500.py
  python scripts/backtest_macro_core_us500.py --spread-pts 1.0 --fin-bps-day 1.5
  python scripts/backtest_macro_core_us500.py --gross        # costs off
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
from src.strategies.macro_core import MacroCoreStrategy
from config import MacroCoreConfig

DAY_MS = 86_400_000
CSV = "data/research/us500_daily.csv"


def load_us500_daily(path=CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df.rename(columns={"volume": "vol"})
    # US500 has no taker buy volume; Macro Core never reads these anyway
    df["buy_vol"] = 0.0
    df["buy_ratio"] = 0.5
    return df[["open", "high", "low", "close", "vol", "buy_vol", "buy_ratio"]]


class FakeExecClient:
    """Records the chandelier exit issued by the real strategy code."""
    def __init__(self):
        self.exit_requested = False

    def sell(self, *a, **k):
        if k.get("label") == "mc_exit":
            self.exit_requested = True
        return {"order_id": "sim"}

    def buy(self, *a, **k):
        return {"order_id": "sim"}


def run(d1: pd.DataFrame, spread_pts: float, fin_bps_day: float,
        vol_target: float = 0.0):
    d1_candles = build_candles(d1, DAY_MS)
    provider = HistoricalKlineProvider(
        [], d1_candles, pd.Series([0.0], index=[d1.index[0]]))

    cfg = MacroCoreConfig(name="Macro Core", persist_state=False,
                          vol_target=vol_target)
    deps = {k: None for k in ["order_manager", "position_monitor",
                              "risk_manager", "orderflow_engine",
                              "regime_detector", "scoring_engine", "signal_log"]}
    deps["kline_provider"] = provider
    fake = FakeExecClient()
    strat = MacroCoreStrategy(client=fake, config=cfg, dependencies=deps)

    ts = d1.index.values.astype("int64") // 10**6
    opens, highs = d1["open"].values, d1["high"].values
    lows, closes = d1["low"].values, d1["close"].values
    n = len(d1)

    fin = fin_bps_day / 10_000.0
    open_tr = None
    pending = None          # "enter" | "exit"
    pending_sig = None
    trades = []
    equity = 1.0
    eq_curve = []

    def close_trade(exit_mid, exit_ms, reason):
        nonlocal equity, open_tr
        gross = (exit_mid - open_tr["entry"]) / open_tr["entry"]
        days = max(0.0, (exit_ms - open_tr["entry_ms"]) / DAY_MS)
        cost = spread_pts / open_tr["entry"] + fin * days
        net = gross - cost
        equity *= (1 + net)
        trades.append({
            "entry_ts": pd.Timestamp(open_tr["entry_ms"], unit="ms", tz="UTC"),
            "exit_ts": pd.Timestamp(exit_ms, unit="ms", tz="UTC"),
            "entry": open_tr["entry"], "exit": exit_mid,
            "gross_pct": gross * 100, "net_pct": net * 100,
            "days": days, "reason": reason,
        })
        open_tr = None

    for i in range(n):
        bar_close = int(ts[i]) + DAY_MS
        provider.current_ms = bar_close

        # ---- execute pending action at this bar's open ----
        if pending == "enter":
            open_tr = {"entry": opens[i], "entry_ms": int(ts[i]),
                       "sl": pending_sig["stop_loss"],
                       "bar_ts_ms": pending_sig["bar_ts_ms"]}
            strat._open_trade = {
                "entry_ts_ms": int(ts[i]),
                "entry_bar_ts_ms": pending_sig["bar_ts_ms"],
                "direction": "buy", "quantity": 10, "entry_price": opens[i]}
            pending = pending_sig = None
        elif pending == "exit" and open_tr is not None:
            close_trade(opens[i], int(ts[i]), "chandelier")
            pending = None

        # ---- disaster SL intrabar (daily low) ----
        if open_tr is not None and lows[i] <= open_tr["sl"]:
            close_trade(open_tr["sl"], bar_close, "disaster_sl")
            strat._open_trade = None

        # ---- daily boundary: drive the real strategy ----
        mtm = equity * (closes[i] / open_tr["entry"]) if open_tr else equity
        eq_curve.append((bar_close, mtm))

        if open_tr is not None:
            fake.exit_requested = False
            stats = strat.manage_positions()
            if fake.exit_requested or stats.get("exits"):
                pending = "exit"
        else:
            signals = strat.scan()
            if signals:
                pending_sig = signals[0]
                pending = "enter"

    if open_tr is not None:
        close_trade(closes[-1], int(ts[-1]) + DAY_MS, "end_of_data")

    t = pd.DataFrame(trades)
    eq = pd.Series([e for _, e in eq_curve],
                   index=pd.to_datetime([ts for ts, _ in eq_curve],
                                        unit="ms", utc=True))
    return t, eq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread-pts", type=float, default=1.0,
                    help="round-trip bid/ask spread in index points (IG US500)")
    ap.add_argument("--fin-bps-day", type=float, default=1.5,
                    help="overnight financing on the long, bps/day (~5.5%/yr)")
    ap.add_argument("--gross", action="store_true", help="disable all costs")
    ap.add_argument("--vol-target", type=float, default=0.0,
                    help="MacroCore vol-target (0=fixed full exposure)")
    args = ap.parse_args()

    if not os.path.exists(CSV):
        print(f"❌ {CSV} not found — run scripts/download_us500_ig.py first")
        return 1

    d1 = load_us500_daily()
    print(f"US500 daily: {d1.index[0].date()} → {d1.index[-1].date()}  "
          f"({len(d1)} bars)")
    if len(d1) < 201:
        print(f"⚠️  only {len(d1)} bars — Macro Core needs ≥201 (SMA200). "
              f"This is just a plumbing smoke test; re-run after full download.")

    spread = 0.0 if args.gross else args.spread_pts
    fin = 0.0 if args.gross else args.fin_bps_day
    t, eq = run(d1, spread, fin, vol_target=args.vol_target)

    bh = d1["close"].iloc[-1] / d1["close"].iloc[0] - 1
    years = (d1.index[-1] - d1.index[0]).days / 365.25
    equity = (1 + t["net_pct"] / 100).prod() if len(t) else 1.0
    peak = eq.cummax()
    mdd = ((peak - eq) / peak).max() * 100 if len(eq) else 0.0
    cagr = (equity ** (1 / years) - 1) * 100 if years > 0 and equity > 0 else 0.0

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt, fin {args.fin_bps_day}bps/d)"
    print(f"\n=== MACRO CORE — US500 daily, real strategy code — {tag} ===")
    print(f"  Trades:   {len(t)}")
    print(f"  Return:   {(equity-1)*100:+.1f}%   (buy&hold {bh*100:+.1f}%)")
    print(f"  CAGR:     {cagr:+.1f}%/yr over {years:.1f}y")
    print(f"  maxDD:    {mdd:.1f}%  (daily mark-to-market)")
    if len(t):
        wr = (t["net_pct"] > 0).mean() * 100
        print(f"  WR:       {wr:.0f}%   avg/trade: {t['net_pct'].mean():+.2f}%  "
              f"(gross {t['gross_pct'].mean():+.2f}%)")
        print(f"  avg hold: {t['days'].mean():.0f} days")
        print(f"  exits:    {t['reason'].value_counts().to_dict()}")
        yearly = eq.resample("YE").last() / eq.resample("YE").first() - 1
        print("  per year: " + "  ".join(f"{idx.year}:{v*100:+.0f}%"
                                         for idx, v in yearly.items()))
        print("\n  Trades:")
        for _, r in t.iterrows():
            print(f"    {r['entry_ts']:%Y-%m-%d} → {r['exit_ts']:%Y-%m-%d}  "
                  f"{r['net_pct']:+7.2f}%  ({int(r['days'])}d, {r['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
