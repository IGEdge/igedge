#!/usr/bin/env python3
"""
Intraday mean-reversion on US500 (EDGES.md Strategy B) — the sub-daily extension
of the VALIDATED Edge #1 (daily RSI2 dip-buy). Same family, faster timeframe.

Thesis: on a liquid index, short-term oversold extremes on 15m bars revert (market
makers pull price back to fair value). If daily RSI2<10 dip-buy works, 15m RSI2<5
in an intraday uptrend SHOULD carry the same bias — cross-validation of the edge.

Rules (long-only, no lookahead — signal on a CLOSED 15m bar, enter at its close):
  SETUP: RTH 15m bars (09:30-16:00 ET); daily uptrend (close_{t-1} > SMA200).
  ENTRY: RSI(2,15m) < entry_rsi.  Optional VWAP gate (--vwap above|below|off).
  EXIT (first of): RSI(2) > exit_rsi | back to VWAP (if entered below) |
                   max_hold bars | RTH session end (forced, flat overnight).
  No tight stop (same lesson as Edge #1). Intraday -> no financing, no gap.

Apparatus: net of spread, NULL TEST (does the RSI2 signal beat a RANDOM entry bar
in the same uptrend day with the same exit?), IS/OOS split, per-year stability.

Data: data/research/us500_1m.pkl (Dukascopy 1m 2022-2026) -> resampled 15m RTH,
plus us500_daily.csv for the SMA200 daily uptrend filter.

Usage:
  python scripts/intraday_mr_us500.py
  python scripts/intraday_mr_us500.py --entry-rsi 5 --vwap below
  python scripts/intraday_mr_us500.py --no-trend --gross
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

DAILY_CSV = "data/research/us500_daily.csv"
ET = "America/New_York"


def rsi(close: pd.Series, period: int = 2) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def build_15m_rth(m1: pd.DataFrame) -> pd.DataFrame:
    """1m -> 15m bars restricted to RTH (09:30-16:00 ET), with per-day VWAP and
    RSI(2) computed within each day. Returns a DataFrame with a 'date' column."""
    et = m1.tz_convert(ET)
    mod = et.index.hour * 60 + et.index.minute
    rth = et[(mod >= 9 * 60 + 30) & (mod < 16 * 60)]
    bars = rth.resample("15min").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna()
    bars["date"] = bars.index.normalize()
    # per-day VWAP (typical price weighted) and RSI(2)
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    pv = tp * bars["volume"]
    g = bars.groupby("date")
    bars["vwap"] = pv.groupby(bars["date"]).cumsum() / \
        bars["volume"].groupby(bars["date"]).cumsum().replace(0, np.nan)
    bars["rsi2"] = g["close"].transform(lambda s: rsi(s, 2))
    bars["bar_in_day"] = g.cumcount()
    return bars


def build_daily_uptrend(sma_period: int = 200) -> pd.Series:
    d = pd.read_csv(DAILY_CSV)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    d = d.set_index("ts").sort_index()
    up = (d["close"] > d["close"].rolling(sma_period).mean()).shift(1)
    up.index = up.index.tz_convert(ET).normalize().date
    return up


def simulate_day(day: pd.DataFrame, entry_rsi, exit_rsi, vwap_mode, max_hold,
                 min_bar, entry_bars=None):
    """Walk one day's 15m bars. If entry_bars is None, take REAL signals
    (RSI2<entry_rsi + vwap gate); else force entries at the given bar indices
    (for the null). Non-overlapping. Returns list of (gross_ret, hold_bars)."""
    c = day["close"].values
    r2 = day["rsi2"].values
    vw = day["vwap"].values
    n = len(day)
    out = []
    i = min_bar
    while i < n - 1:
        if entry_bars is None:
            sig = r2[i] < entry_rsi
            if vwap_mode == "above":
                sig = sig and c[i] > vw[i]
            elif vwap_mode == "below":
                sig = sig and c[i] < vw[i]
        else:
            sig = i in entry_bars
        if not sig:
            i += 1
            continue
        entry = c[i]
        entered_below = c[i] < vw[i]
        exit_j = n - 1
        for j in range(i + 1, n):
            if r2[j] > exit_rsi:
                exit_j = j; break
            if entered_below and c[j] >= vw[j]:      # reverted to fair value
                exit_j = j; break
            if j - i >= max_hold:
                exit_j = j; break
        out.append((c[exit_j] / entry - 1.0, exit_j - i))
        i = exit_j + 1                                # no overlap
    return out


def _stats(r: np.ndarray) -> dict:
    n = len(r)
    if n == 0:
        return dict(n=0, mean=float("nan"), wr=float("nan"), t=float("nan"))
    m = float(np.mean(r))
    sd = float(np.std(r, ddof=1)) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return dict(n=n, mean=m, wr=float(np.mean(np.array(r) > 0)) * 100, t=t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--entry-rsi", type=float, default=5.0)
    ap.add_argument("--exit-rsi", type=float, default=70.0)
    ap.add_argument("--vwap", choices=["off", "above", "below"], default="off",
                    help="VWAP gate at entry (Strat B says 'above'; 'below'=MR-sensible)")
    ap.add_argument("--max-hold", type=int, default=12, help="max 15m bars held (12=3h)")
    ap.add_argument("--min-bar", type=int, default=3, help="skip first bars (RSI warmup)")
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
    rows = []               # (date, year, gross, hold, entry_price)
    null_means = []         # per-permutation mean gross (for null test)
    rng = np.random.default_rng(0)

    day_groups = list(bars.groupby("date"))
    # precompute per-day arrays for the null (random entries in uptrend days)
    for date, day in day_groups:
        d = date.date()
        if use_trend:
            if d not in uptrend.index or not bool(uptrend.get(d, False)):
                continue
        trades = simulate_day(day, args.entry_rsi, args.exit_rsi, args.vwap,
                              args.max_hold, args.min_bar)
        ep = day["close"].values
        for gret, hold in trades:
            rows.append({"date": d, "year": date.year, "gross": gret,
                         "hold": hold, "entry": ep[0]})

    if not rows:
        print("❌ no trades"); return 1
    t = pd.DataFrame(rows)
    # net: spread as return fraction on entry price (approx mean index level)
    px = t["entry"].mean()
    t["net"] = t["gross"] - (0.0 if args.gross else spread / px)

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    print(f"\nUS500 INTRADAY MR 15m  RSI2<{args.entry_rsi:.0f}  exit RSI2>{args.exit_rsi:.0f}"
          f"  vwap={args.vwap}  maxhold={args.max_hold}b  "
          f"{'uptrend' if use_trend else 'trend OFF'}  {tag}")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade "
          f"(~{len(t)/max((pd.Timestamp(t['date'].iloc[-1])-pd.Timestamp(t['date'].iloc[0])).days/365.25,0.5):.0f}/anno)")

    print("\n=== 1) RISULTATO SEGNALE ===")
    st_n = _stats(t["net"].values); st_g = _stats(t["gross"].values)
    print(f"  segnale (net)   N={st_n['n']:5d}  WR={st_n['wr']:4.0f}%  "
          f"E[ret]={st_n['mean']*100:+.3f}%  t={st_n['t']:+.2f}  hold medio {t['hold'].mean():.1f} bar")
    print(f"  segnale (gross) N={st_g['n']:5d}  WR={st_g['wr']:4.0f}%  "
          f"E[ret]={st_g['mean']*100:+.3f}%  t={st_g['t']:+.2f}")

    # 2) NULL TEST: random entry bars in the SAME uptrend days, same exit logic.
    #    Same number of entries per day as the real signal produced.
    real_mean = t["gross"].mean()
    per_day_counts = t.groupby("date").size().to_dict()
    for _ in range(args.perm):
        gs = []
        for date, day in day_groups:
            d = date.date()
            kk = per_day_counts.get(d, 0)
            if kk == 0:
                continue
            n = len(day)
            if n - 1 - args.min_bar <= 0:
                continue
            cand = np.arange(args.min_bar, n - 1)
            if len(cand) == 0:
                continue
            pick = set(rng.choice(cand, size=min(kk, len(cand)), replace=False).tolist())
            tr = simulate_day(day, args.entry_rsi, args.exit_rsi, args.vwap,
                              args.max_hold, args.min_bar, entry_bars=pick)
            gs.extend(g for g, _ in tr)
        if gs:
            null_means.append(float(np.mean(gs)))
    null = np.array(null_means)
    if len(null):
        pct = (null < real_mean).mean() * 100
        z = (real_mean - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n=== 2) TEST DEL NULLA (RSI2 vs entry random negli stessi giorni uptrend) ===")
        print(f"  E[ret] reale {real_mean*100:+.3f}%  vs  null {null.mean()*100:+.3f}%  "
              f"→ batte {pct:.0f}% random  z={z:+.2f}  → {verdict}")

    # 3) IS/OOS
    split = pd.Timestamp(args.oos).date()
    is_ = t[t["date"] < split]; oos = t[t["date"] >= split]
    print(f"\n=== 3) IN-SAMPLE / OUT-OF-SAMPLE (split {split}) — net ===")
    s = _stats(is_["net"].values); print(f"  IS  N={s['n']:5d}  WR={s['wr']:4.0f}%  E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}")
    s = _stats(oos["net"].values); print(f"  OOS N={s['n']:5d}  WR={s['wr']:4.0f}%  E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}")

    # 4) per-year + compounding
    print("\n=== 4) STABILITÀ ANNUALE (net) ===")
    for y, sub in t.groupby("year"):
        s = _stats(sub["net"].values)
        print(f"   {y}: N={s['n']:4d}  WR={s['wr']:3.0f}%  E[ret]={s['mean']*100:+.3f}%  "
              f"somma={sub['net'].sum()*100:+.1f}%")
    tot = (1 + t["net"]).prod() - 1
    eq = (1 + t["net"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    print(f"\n  Compounding 1x: return {tot*100:+.1f}%  maxDD {mdd:.1f}%  ({len(t)} trade)")
    print("  Promosso solo se: batte il nulla E netto costi positivo E stabile E regge OOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
