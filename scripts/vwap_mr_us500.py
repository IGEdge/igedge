#!/usr/bin/env python3
"""
VWAP Mean-Reversion on US500 (EDGES.md Strategy C) — intraday, flat overnight.

Thesis: intraday VWAP is the "fair value" desks trade around; large deviations
below it revert. Long when price is > k*sigma below the session VWAP; target =
back to VWAP; wide catastrophe stop at VWAP - k_stop*sigma; exit at session end.

Long-only (index long-biased). NOTE: intraday long on US500 is a known HEADWIND
(the equity premium accrues overnight) — this is tested for completeness.

Rules (no lookahead — signal on a CLOSED 15m bar, enter at its close):
  SETUP: RTH 15m bars; per-day VWAP; sigma = expanding std of (close-VWAP) in day.
  ENTRY: bar_in_day >= min_bar (>=1h) AND daily uptrend AND close < VWAP - k*sigma.
  EXIT (first of): close >= VWAP (revert) | close <= VWAP - k_stop*sigma (stop) |
                   RTH session end (forced, flat overnight).

Apparatus: net of spread, NULL TEST (VWAP-dev signal vs random entry bar in the
same uptrend day, same exit), IS/OOS, per-year. Data: us500_1m.pkl + daily CSV.

Usage:
  python scripts/vwap_mr_us500.py
  python scripts/vwap_mr_us500.py --k 2.0 --k-stop 3.0 --no-trend --gross
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
from intraday_mr_us500 import build_15m_rth, build_daily_uptrend, _stats  # reuse


def simulate_day(day, k, k_stop, min_bar, entry_bars=None):
    """Walk one day's 15m bars. VWAP-deviation entries (or forced entry_bars for
    the null). z = (close-vwap)/expanding_std(close-vwap). Non-overlapping."""
    c = day["close"].values
    vw = day["vwap"].values
    dist = c - vw
    # expanding std of the deviation within the day (needs a few bars)
    sd = pd.Series(dist).expanding(min_periods=min_bar).std(ddof=1).values
    n = len(day)
    out = []
    i = min_bar
    while i < n - 1:
        sig_ok = (sd[i] is not None and not np.isnan(sd[i]) and sd[i] > 0)
        if entry_bars is None:
            sig = sig_ok and (c[i] < vw[i] - k * sd[i])
        else:
            sig = i in entry_bars and sig_ok
        if not sig:
            i += 1
            continue
        entry = c[i]
        sig_i = sd[i]
        exit_j = n - 1
        for j in range(i + 1, n):
            if c[j] >= vw[j]:                       # reverted to VWAP (target)
                exit_j = j; break
            if c[j] <= vw[j] - k_stop * sig_i:      # catastrophe stop (wide)
                exit_j = j; break
        out.append((c[exit_j] / entry - 1.0, exit_j - i))
        i = exit_j + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--k", type=float, default=1.5, help="entry: close < VWAP - k*sigma")
    ap.add_argument("--k-stop", type=float, default=2.5, help="stop: VWAP - k_stop*sigma")
    ap.add_argument("--min-bar", type=int, default=4, help="min bars from open (4=1h)")
    ap.add_argument("--no-trend", action="store_true")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--perm", type=int, default=1000)
    ap.add_argument("--oos", default="2024-07-01")
    args = ap.parse_args()

    print(f"Loading 1m bars {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    if len(m1) == 0:
        print("❌ no cached bars"); return 1
    bars = build_15m_rth(m1)
    uptrend = build_daily_uptrend()
    use_trend = not args.no_trend
    spread = 0.0 if args.gross else args.spread_pts

    rows = []
    day_groups = list(bars.groupby("date"))
    for date, day in day_groups:
        d = date.date()
        if use_trend and (d not in uptrend.index or not bool(uptrend.get(d, False))):
            continue
        for gret, hold in simulate_day(day, args.k, args.k_stop, args.min_bar):
            rows.append({"date": d, "year": date.year, "gross": gret,
                         "hold": hold, "entry": day["close"].values[0]})
    if not rows:
        print("❌ no trades"); return 1
    t = pd.DataFrame(rows)
    px = t["entry"].mean()
    t["net"] = t["gross"] - (0.0 if args.gross else spread / px)

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    print(f"\nUS500 VWAP-MR 15m  entry<VWAP-{args.k}σ  stop<VWAP-{args.k_stop}σ  "
          f"{'uptrend' if use_trend else 'trend OFF'}  {tag}")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)")

    st_n = _stats(t["net"].values); st_g = _stats(t["gross"].values)
    print("\n=== 1) RISULTATO SEGNALE ===")
    print(f"  segnale (net)   N={st_n['n']:5d}  WR={st_n['wr']:4.0f}%  E[ret]={st_n['mean']*100:+.3f}%  "
          f"t={st_n['t']:+.2f}  hold medio {t['hold'].mean():.1f} bar")
    print(f"  segnale (gross) N={st_g['n']:5d}  WR={st_g['wr']:4.0f}%  E[ret]={st_g['mean']*100:+.3f}%  t={st_g['t']:+.2f}")

    # NULL: random entry bars, same per-day count, same exit
    rng = np.random.default_rng(0)
    real_mean = t["gross"].mean()
    per_day = t.groupby("date").size().to_dict()
    null = []
    for _ in range(args.perm):
        gs = []
        for date, day in day_groups:
            kk = per_day.get(date.date(), 0)
            if kk == 0:
                continue
            n = len(day)
            cand = np.arange(args.min_bar, n - 1)
            if len(cand) == 0:
                continue
            pick = set(rng.choice(cand, size=min(kk, len(cand)), replace=False).tolist())
            gs.extend(g for g, _ in simulate_day(day, args.k, args.k_stop, args.min_bar, entry_bars=pick))
        if gs:
            null.append(float(np.mean(gs)))
    null = np.array(null)
    if len(null):
        pct = (null < real_mean).mean() * 100
        z = (real_mean - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n=== 2) TEST DEL NULLA (dev-VWAP vs entry random stessi giorni uptrend) ===")
        print(f"  E[ret] reale {real_mean*100:+.3f}%  vs  null {null.mean()*100:+.3f}%  "
              f"→ batte {pct:.0f}% random  z={z:+.2f}  → {verdict}")

    split = pd.Timestamp(args.oos).date()
    for lab, sub in [("IS", t[t["date"] < split]), ("OOS", t[t["date"] >= split])]:
        s = _stats(sub["net"].values)
        print(f"  {lab:3s} N={s['n']:5d}  WR={s['wr']:4.0f}%  E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}")

    print("\n=== STABILITÀ ANNUALE (net) ===")
    for y, sub in t.groupby("year"):
        s = _stats(sub["net"].values)
        print(f"   {y}: N={s['n']:4d}  WR={s['wr']:3.0f}%  E[ret]={s['mean']*100:+.3f}%  somma={sub['net'].sum()*100:+.1f}%")
    tot = (1 + t["net"]).prod() - 1
    eq = (1 + t["net"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    print(f"\n  Compounding 1x: return {tot*100:+.1f}%  maxDD {mdd:.1f}%  ({len(t)} trade)")
    print("  Promosso solo se: batte il nulla E netto costi positivo E stabile E regge OOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
