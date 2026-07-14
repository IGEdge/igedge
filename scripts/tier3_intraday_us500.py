#!/usr/bin/env python3
"""
Tier-3 speculative intraday ideas on US500 (EDGES.md G & H) — tested for
completeness now that Tier 1-2 are exhausted. Both are intraday long-only, so the
known intraday-long HEADWIND (see EDGES.md "Lezione #2") is expected to bite.

  G  volatility-squeeze breakout: after a Bollinger(20,2) bandwidth squeeze
     (bw < 10th pct of last 50), long the up-breakout above VWAP; target = entry
     + tgt×(squeeze band width); exit at session end. Flat overnight.
  H  accumulation: over a lookback, up-bar volume > down-bar volume while price
     is down and below VWAP -> long; exit back to VWAP or session end.

Apparatus: net of spread, NULL TEST (signal vs random entry bar in same uptrend
day + same exit), IS/OOS, per-year. Data: us500_1m.pkl (15m RTH) + daily CSV.

Usage:
  python scripts/tier3_intraday_us500.py --strat squeeze
  python scripts/tier3_intraday_us500.py --strat accdist --no-trend
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
from intraday_mr_us500 import build_15m_rth, build_daily_uptrend, _stats


def add_indicators(bars, bb_n=20, bb_k=2.0, acc_lb=6):
    """Rolling Bollinger bandwidth + squeeze flag; per-day up/down volume sums."""
    c = bars["close"]
    ma = c.rolling(bb_n).mean()
    sd = c.rolling(bb_n).std(ddof=0)
    bars["bb_up"] = ma + bb_k * sd
    bars["bb_dn"] = ma - bb_k * sd
    bars["bw"] = (bars["bb_up"] - bars["bb_dn"])
    bwpct = bars["bw"].rolling(50).apply(lambda w: (w[-1] <= np.nanpercentile(w, 10)) * 1.0, raw=True)
    bars["squeeze"] = bwpct.fillna(0.0)
    # accumulation features over a rolling lookback
    up = (bars["close"] > bars["open"]) * bars["volume"]
    dn = (bars["close"] <= bars["open"]) * bars["volume"]
    bars["upvol"] = up.rolling(acc_lb).sum()
    bars["dnvol"] = dn.rolling(acc_lb).sum()
    bars["ret_lb"] = bars["close"] / bars["close"].shift(acc_lb) - 1.0
    return bars


def simulate_day(day, strat, tgt, entry_bars=None):
    """Long-only intraday sim. entry_bars=None -> real signal; else forced (null).
    Non-overlapping. Returns list of (gross_ret, hold_bars)."""
    c = day["close"].values
    vw = day["vwap"].values
    sq = day["squeeze"].values
    up = day["bb_up"].values
    bw = day["bw"].values
    upvol = day["upvol"].values
    dnvol = day["dnvol"].values
    retlb = day["ret_lb"].values
    n = len(day)
    out = []
    i = 3
    while i < n - 1:
        if entry_bars is None:
            if strat == "squeeze":
                sig = (i > 0 and sq[i - 1] > 0 and c[i] > up[i] and c[i] > vw[i]
                       and np.isfinite(bw[i]))
            else:  # accdist
                sig = (np.isfinite(upvol[i]) and upvol[i] > dnvol[i]
                       and retlb[i] < 0 and c[i] < vw[i])
        else:
            sig = i in entry_bars
        if not sig:
            i += 1
            continue
        entry = c[i]
        target = entry + tgt * bw[i] if (strat == "squeeze" and np.isfinite(bw[i])) else None
        exit_j = n - 1
        for j in range(i + 1, n):
            if strat == "squeeze":
                if target is not None and c[j] >= target:
                    exit_j = j; break
            else:  # accdist -> revert to VWAP
                if c[j] >= vw[j]:
                    exit_j = j; break
        out.append((c[exit_j] / entry - 1.0, exit_j - i))
        i = exit_j + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strat", choices=["squeeze", "accdist"], required=True)
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--tgt", type=float, default=2.0, help="squeeze target = tgt×bandwidth")
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
    bars = add_indicators(build_15m_rth(m1))
    uptrend = build_daily_uptrend()
    use_trend = not args.no_trend
    spread = 0.0 if args.gross else args.spread_pts

    rows = []
    day_groups = list(bars.groupby("date"))
    for date, day in day_groups:
        d = date.date()
        if use_trend and (d not in uptrend.index or not bool(uptrend.get(d, False))):
            continue
        for gret, hold in simulate_day(day, args.strat, args.tgt):
            rows.append({"date": d, "year": date.year, "gross": gret,
                         "hold": hold, "entry": day["close"].values[0]})
    if not rows:
        print("❌ no trades"); return 1
    t = pd.DataFrame(rows)
    px = t["entry"].mean()
    t["net"] = t["gross"] - (0.0 if args.gross else spread / px)

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    name = {"squeeze": "VOLATILITY SQUEEZE (G)", "accdist": "ACCUMULATION/DISTRIBUTION (H)"}[args.strat]
    print(f"\nUS500 {name} 15m  {'uptrend' if use_trend else 'trend OFF'}  {tag}")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)  "
          f"hold medio {t['hold'].mean():.1f} bar")

    st_n = _stats(t["net"].values); st_g = _stats(t["gross"].values)
    print(f"\n  segnale (net)   N={st_n['n']:5d}  WR={st_n['wr']:4.0f}%  E[ret]={st_n['mean']*100:+.3f}%  t={st_n['t']:+.2f}")
    print(f"  segnale (gross) N={st_g['n']:5d}  WR={st_g['wr']:4.0f}%  E[ret]={st_g['mean']*100:+.3f}%  t={st_g['t']:+.2f}")

    # NULL: random entries, same per-day count, same exit
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
            cand = np.arange(3, n - 1)
            if len(cand) == 0:
                continue
            pick = set(rng.choice(cand, size=min(kk, len(cand)), replace=False).tolist())
            gs.extend(g for g, _ in simulate_day(day, args.strat, args.tgt, entry_bars=pick))
        if gs:
            null.append(float(np.mean(gs)))
    null = np.array(null)
    if len(null):
        pct = (null < real_mean).mean() * 100
        z = (real_mean - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n  TEST DEL NULLA: E[ret] reale {real_mean*100:+.3f}%  vs null {null.mean()*100:+.3f}%  "
              f"→ batte {pct:.0f}% random  z={z:+.2f}  → {verdict}")

    split = pd.Timestamp(args.oos).date()
    for lab, sub in [("IS", t[t["date"] < split]), ("OOS", t[t["date"] >= split])]:
        s = _stats(sub["net"].values)
        print(f"  {lab:3s} N={s['n']:5d}  WR={s['wr']:4.0f}%  E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}")
    tot = (1 + t["net"]).prod() - 1
    print(f"\n  Compounding 1x: return {tot*100:+.1f}%  ({len(t)} trade)")
    print("  Promosso solo se: batte il nulla E netto costi positivo E stabile E regge OOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
