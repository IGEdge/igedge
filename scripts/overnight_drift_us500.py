#!/usr/bin/env python3
"""
Overnight drift test on US500, executable-as-on-IG.

Documented anomaly: almost all of an equity index's long-run return accrues
OVERNIGHT (RTH close -> next RTH open); the intraday session (open -> close) is
roughly flat. On the IG "US 500 Cash" CFD (trades ~23h) you CAN capture the
overnight move by holding from the RTH close to the RTH open — BUT you pay:
  - overnight FINANCING every night held (~5-6%/yr on notional), and
  - the SPREAD on one round-trip per day (~250/yr).
This measures whether the gross overnight drift survives BOTH — the real
question for trading it on IG.

RTH anchors (UTC, DST approximated with fixed hours — first-pass caveat):
  RTH open  ~ open of the 14:00 UTC bar   (US cash open 09:30 ET)
  RTH close ~ close of the 20:00 UTC bar  (US cash close 16:00 ET)

Data: hourly US500 from Dukascopy (data/research/us500_h1.csv).

Usage:
  python scripts/overnight_drift_us500.py
  python scripts/overnight_drift_us500.py --spread-pts 1.0 --fin-annual 0.05
  python scripts/overnight_drift_us500.py --gross
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import pandas as pd

H1 = "data/research/us500_h1.csv"
OPEN_HOUR = 14    # RTH open anchor (UTC)
CLOSE_HOUR = 20   # RTH close anchor (UTC)


def build_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Per-date RTH open (open@14:00 UTC) and close (close@20:00 UTC)."""
    df = df.copy()
    df["date"] = df.index.normalize()
    df["hour"] = df.index.hour
    opens = (df[df["hour"] == OPEN_HOUR].groupby("date")["open"].first()
             .rename("rth_open"))
    closes = (df[df["hour"] == CLOSE_HOUR].groupby("date")["close"].last()
              .rename("rth_close"))
    rth = pd.concat([opens, closes], axis=1).dropna()
    rth = rth[rth["rth_open"] > 0]
    return rth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread-pts", type=float, default=1.0,
                    help="round-trip spread+slippage in index points")
    ap.add_argument("--fin-annual", type=float, default=0.055,
                    help="overnight financing, annual fraction on notional")
    ap.add_argument("--gross", action="store_true", help="disable costs")
    args = ap.parse_args()

    if not os.path.exists(H1):
        print(f"❌ {H1} not found")
        return 1

    df = pd.read_csv(H1)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    rth = build_rth(df)
    if len(rth) < 100:
        print(f"❌ only {len(rth)} RTH days")
        return 1

    o = rth["rth_open"].values
    c = rth["rth_close"].values
    dates = rth.index
    nights = np.r_[1, (dates[1:] - dates[:-1]).days].astype(float)  # incl weekends

    intraday = c / o - 1.0                       # RTH open -> RTH close
    overnight = np.r_[np.nan, o[1:] / c[:-1] - 1.0]   # prev close -> open

    spread = 0.0 if args.gross else args.spread_pts
    fin = 0.0 if args.gross else args.fin_annual
    # overnight NET: minus 1 round-trip spread and financing for the nights held
    on_cost = spread / o + fin / 360.0 * nights
    overnight_net = overnight - on_cost

    df_r = pd.DataFrame({"intraday": intraday, "overnight": overnight,
                         "overnight_net": overnight_net}, index=dates).dropna()

    def cagr(rets):
        eq = (1 + rets).prod()
        yrs = (df_r.index[-1] - df_r.index[0]).days / 365.25
        return (eq ** (1 / yrs) - 1) * 100 if yrs > 0 and eq > 0 else float("nan"), \
               (eq - 1) * 100

    bh = c[-1] / c[0] - 1
    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt, fin {args.fin_annual:.1%}/yr)"
    print(f"US500 RTH days: {df_r.index[0].date()} → {df_r.index[-1].date()}  "
          f"({len(df_r)})")
    print(f"\n=== OVERNIGHT DRIFT — {tag} ===")
    for name in ["intraday", "overnight", "overnight_net"]:
        cg, tot = cagr(df_r[name])
        wr = (df_r[name] > 0).mean() * 100
        print(f"  {name:14s}  tot {tot:+7.1f}%  CAGR {cg:+5.1f}%/yr  "
              f"WR {wr:3.0f}%  media/gg {df_r[name].mean()*1e4:+5.1f}bps")
    print(f"  {'buy&hold(RTHc)':14s}  tot {bh*100:+7.1f}%")

    print("\n  per anno (overnight gross → net):")
    yr = df_r.groupby(df_r.index.year)
    for y, sub in yr:
        g = (1 + sub["overnight"]).prod() - 1
        nt = (1 + sub["overnight_net"]).prod() - 1
        print(f"   {y}: N={len(sub):3d}  gross {g*100:+6.1f}%  net {nt*100:+6.1f}%")

    print("\n  Se 'overnight_net' non batte comodamente buy&hold e non è positivo "
          "\n  ogni anno, il drift overnight NON è tradeable su CFD IG (costi).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
