#!/usr/bin/env python3
"""
First-Hour Momentum Filter on US500 (INDICE-EDGE.md Strategy D) — NOT an ORB.

The classic Opening-Range Breakout is already falsified (coin flip). This is
different: use the FIRST HOUR only as a DIRECTIONAL FILTER, then enter long on a
pullback (Gao/Han/Li/Zhou 2018: first half-hour predicts the rest of the day,
esp. in high vol). Long-only (index long-biased); structural stop/target.

Rules (no lookahead):
  FIRST HOUR = 09:30-10:30 ET (first 4×15m bars). fh_high/fh_low/fh_ret defined.
  FILTER: "bullish" if fh_ret > +thr ; daily ATR(14) > historical median (regime).
  ENTRY (long): after 10:30, on a pullback to fh_high - 0.5*fh_range (limit fill).
  EXIT: target = fh_high | stop = fh_low (structural, wide) | RTH session end.

NOTE: intraday long on US500 is a known HEADWIND — tested for completeness.

NULL TEST: the same pullback-entry mechanic on ALL days vs. the bullish-filtered
subset — does the first-hour filter add anything over a random day?

Data: us500_1m.pkl (15m RTH) + us500_daily.csv (ATR regime). 2022-2026.

Usage:
  python scripts/first_hour_us500.py
  python scripts/first_hour_us500.py --thr 0.25 --no-regime --gross
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
from intraday_mr_us500 import build_15m_rth, _stats

DAILY_CSV = "data/research/us500_daily.csv"
ET = "America/New_York"


def build_daily_regime(atr_period: int = 14) -> pd.Series:
    """date(ET) -> was ATR(14) above its historical median as of the prior close?
    (shift 1, no lookahead)."""
    d = pd.read_csv(DAILY_CSV)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    d = d.set_index("ts").sort_index()
    pc = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - pc).abs(),
                    (d["low"] - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    med = atr.expanding(min_periods=100).median()      # historical median so far
    hi = (atr > med).shift(1)
    hi.index = hi.index.tz_convert(ET).normalize().date
    return hi


def day_trade(day, thr, pullback, entry_bars=None):
    """One long trade per day if first-hour is bullish and a pullback fills.
    entry_bars (for null): if given, ignore the bullish filter (force candidacy).
    Returns (gross_ret, 'win'|'loss'|'eod', is_bullish) or None."""
    o = day["open"].values
    h = day["high"].values
    lo = day["low"].values
    c = day["close"].values
    n = len(day)
    if n < 6:                                          # need 1st hour + room
        return None
    fh_high = h[:4].max()
    fh_low = lo[:4].min()
    fh_ret = c[3] / o[0] - 1.0
    rng = fh_high - fh_low
    if rng <= 0:
        return None
    bullish = fh_ret > thr / 100.0
    if entry_bars is None and not bullish:
        return None
    level = fh_high - pullback * rng                   # 50% pullback by default
    # find pullback fill after the first hour
    for i in range(4, n):
        if lo[i] <= level:                             # limit fills at the level
            entry = level
            # simulate target/stop/eod from the NEXT bar
            for j in range(i + 1, n):
                if h[j] >= fh_high:
                    return (fh_high / entry - 1.0, "win", bullish)
                if lo[j] <= fh_low:
                    return (fh_low / entry - 1.0, "loss", bullish)
            return (c[-1] / entry - 1.0, "eod", bullish)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--thr", type=float, default=0.15, help="bullish if fh_ret > thr%%")
    ap.add_argument("--pullback", type=float, default=0.5, help="entry = fh_high - pb*range")
    ap.add_argument("--no-regime", action="store_true", help="disable ATR>median filter")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--perm", type=int, default=2000)
    ap.add_argument("--oos", default="2024-07-01")
    args = ap.parse_args()

    print(f"Loading 1m bars {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    if len(m1) == 0:
        print("❌ no cached bars"); return 1
    bars = build_15m_rth(m1)
    regime = build_daily_regime()
    use_regime = not args.no_regime
    spread = 0.0 if args.gross else args.spread_pts

    rows = []           # real signal trades (bullish [+regime])
    allday = []         # every day with a valid pullback fill (for the null)
    day_groups = list(bars.groupby("date"))
    for date, day in day_groups:
        d = date.date()
        if use_regime and (d not in regime.index or not bool(regime.get(d, False))):
            # regime gate applies to the real signal; for the null pool we still
            # want a comparable universe, so also gate the pool by regime.
            continue
        # null pool: force candidacy (ignore bullish) to get the mechanic's base rate
        base = day_trade(day, args.thr, args.pullback, entry_bars=True)
        if base is not None:
            allday.append({"date": d, "year": date.year, "gross": base[0]})
        real = day_trade(day, args.thr, args.pullback)
        if real is not None:
            rows.append({"date": d, "year": date.year, "gross": real[0],
                         "outcome": real[1], "entry": day["close"].values[0]})
    if not rows:
        print("❌ no trades"); return 1
    t = pd.DataFrame(rows)
    pool = pd.DataFrame(allday)
    px = t["entry"].mean()
    t["net"] = t["gross"] - (0.0 if args.gross else spread / px)

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    print(f"\nUS500 FIRST-HOUR FILTER 15m  bullish>+{args.thr}%  pullback {args.pullback:.0%}  "
          f"{'ATR>med' if use_regime else 'regime OFF'}  {tag}")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)")

    st_n = _stats(t["net"].values); st_g = _stats(t["gross"].values)
    wins = (t["outcome"] == "win").sum(); losses = (t["outcome"] == "loss").sum()
    eod = (t["outcome"] == "eod").sum()
    print("\n=== 1) RISULTATO SEGNALE ===")
    print(f"  segnale (net)   N={st_n['n']:5d}  WR={st_n['wr']:4.0f}%  E[ret]={st_n['mean']*100:+.3f}%  t={st_n['t']:+.2f}")
    print(f"  segnale (gross) N={st_g['n']:5d}  WR={st_g['wr']:4.0f}%  E[ret]={st_g['mean']*100:+.3f}%  t={st_g['t']:+.2f}")
    print(f"  esiti: target {wins}  stop {losses}  fine-sessione {eod}")

    # NULL: bullish-filtered mean vs random equal-size subset of the pull-back pool
    k = len(t)
    pv = pool["gross"].values
    if 20 <= k < len(pv):
        rng = np.random.default_rng(0)
        real_mean = t["gross"].mean()
        null = np.array([rng.choice(pv, size=k, replace=False).mean() for _ in range(args.perm)])
        pct = (null < real_mean).mean() * 100
        z = (real_mean - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n=== 2) TEST DEL NULLA (filtro bullish vs pullback su giorni random) ===")
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
