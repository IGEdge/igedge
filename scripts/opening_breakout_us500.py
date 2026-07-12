#!/usr/bin/env python3
"""
Opening Range Breakout (ORB) on US500 — the intraday-open edge, tested with the
cost lesson in mind.

Why this is different from the (falsified) session-H/L sweep, and why it can
survive costs where the fade could not: volatility is highest at the major
opens (the intraday 'U'), so the OPENING RANGE is wide (~10-30 pts). Using that
range as the stop distance makes the spread a SMALL fraction of risk — unlike
the fade's 3.2-pt stops where spread was 0.62 R.

Setup (per open, per day):
  - opening range = high/low of the first OR_MIN minutes after the open;
  - trade the first breakout of that range (long above / short below);
  - stop = opposite side of the range (risk = range), target = R x range,
    time-exit after HOLD_MIN.
NULL: the identical ORB on a DEAD hour (03:00 UTC). If the opens don't beat the
dead hour, the 'open' carries no edge — just intraday volatility.

Data: 1-minute US500 via the Dukascopy 1m cache (fast).

Usage:
  python scripts/opening_breakout_us500.py
  python scripts/opening_breakout_us500.py --or-min 15 -R 2 --spread-pts 1.0
  python scripts/opening_breakout_us500.py --gross
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

from src.data.dukascopy_cache import load_1m_cached

# UTC anchors (DST approximated — first-pass caveat)
OPENS = {"US_open(13:30)": (13, 30), "London_open(07:00)": (7, 0),
         "NULL_dead(03:00)": (3, 0)}


def orb_day(day_bars, h, m, or_min, hold_min, R):
    """One ORB trade for a given open anchor. Returns (gross_R, risk_pts) or None."""
    day = day_bars.index[0].normalize()
    t0 = day + pd.Timedelta(hours=h, minutes=m)
    orb = day_bars[(day_bars.index >= t0) & (day_bars.index < t0 + pd.Timedelta(minutes=or_min))]
    if len(orb) < 5:
        return None
    or_hi, or_lo = orb["high"].max(), orb["low"].min()
    rng = or_hi - or_lo
    if rng <= 0:
        return None
    tw = day_bars[(day_bars.index >= t0 + pd.Timedelta(minutes=or_min)) &
                  (day_bars.index < t0 + pd.Timedelta(minutes=or_min + hold_min))]
    if len(tw) < 5:
        return None
    highs, lows, closes = tw["high"].values, tw["low"].values, tw["close"].values

    # first breakout of the range
    long_ = None
    start = 0
    for i in range(len(tw)):
        if highs[i] >= or_hi:
            long_, start = True, i; break
        if lows[i] <= or_lo:
            long_, start = False, i; break
    if long_ is None:
        return None

    if long_:
        entry, stop = or_hi, or_lo
        target = entry + R * rng
        for i in range(start, len(tw)):
            if lows[i] <= stop:
                return -1.0, rng
            if highs[i] >= target:
                return R, rng
        return (closes[-1] - entry) / rng, rng
    else:
        entry, stop = or_lo, or_hi
        target = entry - R * rng
        for i in range(start, len(tw)):
            if highs[i] >= stop:
                return -1.0, rng
            if lows[i] <= target:
                return R, rng
        return (entry - closes[-1]) / rng, rng


def run_open(m1, h, m, or_min, hold_min, R, spread_pts):
    rows = []
    for day, db in m1.groupby(m1.index.normalize()):
        res = orb_day(db, h, m, or_min, hold_min, R)
        if res is None:
            continue
        gross, risk = res
        net = gross - (spread_pts / risk if risk > 0 else 0)
        rows.append({"year": day.year, "R": gross, "net": net, "risk": risk})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--or-min", type=int, default=30, help="opening-range minutes")
    ap.add_argument("--hold-min", type=int, default=240, help="max hold minutes")
    ap.add_argument("-R", type=float, default=1.0, help="target as multiple of range")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--gross", action="store_true")
    args = ap.parse_args()

    print(f"Loading 1m {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    print(f"  {len(m1):,} 1m bars | OR={args.or_min}m hold={args.hold_min}m "
          f"R={args.R} | {'GROSS' if args.gross else f'spread {args.spread_pts}pt'}")
    spread = 0.0 if args.gross else args.spread_pts

    for label, (h, m) in OPENS.items():
        t = run_open(m1, h, m, args.or_min, args.hold_min, args.R, spread)
        if len(t) < 20:
            print(f"\n{label}: N={len(t)} (pochi)")
            continue
        wr = (t["net"] > 0).mean() * 100
        exp = t["net"].mean()
        print(f"\n=== {label} ===")
        print(f"  N={len(t)}  WR={wr:.0f}%  E[R]_net={exp:+.3f}  "
              f"gross={t['R'].mean():+.3f}  range medio={t['risk'].mean():.1f}pt  "
              f"sum_net={t['net'].sum():+.1f}R")
        yr = t.groupby("year")
        print("  per anno (net): " + "  ".join(
            f"{y}:{s['net'].mean():+.2f}" for y, s in yr))
    print("\n  L'apertura ha edge solo se batte NULL_dead(03:00) e resta "
          "\n  positiva netto costi ogni anno. Range largo = costi piccoli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
