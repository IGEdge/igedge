#!/usr/bin/env python3
"""
Late-Day Drift on US500 (EDGES.md Strategy A) — intraday, flat overnight.

Thesis: the US cash close (16:00 ET) is dominated by institutional flow (MOC
orders, rebalancing). Two documented effects: a drift into the close, stronger
on down days (late-day mean-reversion), and continuation on strongly directional
days. We test the mean-reversion version: on a day that is DOWN from the RTH open
(and in a daily uptrend), go long in the last hour(s) and exit at the RTH close.

Fits the CFD cost structure: 1-2h hold, flat overnight -> no financing, no gap,
spread paid once. Long-only (index long-biased). No tight stop (exit at close).

Apparatus (same rigor as the rest of the project):
  - UNCONDITIONAL baseline: is there ANY entry->close drift on all days?
  - CONDITIONAL signal: does "day down [+ uptrend]" beat the baseline?
  - NULL TEST: does the down-day selection beat a RANDOM selection of the same
    number of days in the same window? (permutation)
  - NET of costs (spread points, round-trip), IS/OOS split, per-year stability.

No lookahead: entry uses the price AT entry time (bar close); the daily uptrend
filter uses the PREVIOUS closed daily bar (shift 1).

Data: data/research/us500_1m.pkl (Dukascopy 1m, 2022-2026) + us500_daily.csv.

Usage:
  python scripts/late_day_drift_us500.py
  python scripts/late_day_drift_us500.py --entry-et 14:00 --dip-thr -0.5
  python scripts/late_day_drift_us500.py --no-trend --gross
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


def _price_at(day_et: pd.DataFrame, hh: int, mm: int, tol_min: int = 5):
    """Price at HH:MM ET within a day's ET-indexed 1m frame: the bar whose
    minute-of-day matches, else the nearest earlier bar within tol_min. Returns
    (close_price, open_price) of that bar, or (None, None)."""
    mod = day_et.index.hour * 60 + day_et.index.minute
    target = hh * 60 + mm
    exact = day_et[mod == target]
    if len(exact):
        return float(exact["close"].iloc[0]), float(exact["open"].iloc[0])
    earlier = day_et[(mod <= target) & (mod >= target - tol_min)]
    if len(earlier):
        return float(earlier["close"].iloc[-1]), float(earlier["open"].iloc[-1])
    return None, None


def build_daily_uptrend(sma_period: int = 200) -> pd.Series:
    """date(ET) -> was the last CLOSED daily bar above its SMA200? (shift 1, no
    lookahead). Indexed by the RTH date the flag applies to."""
    d = pd.read_csv(DAILY_CSV)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    d = d.set_index("ts").sort_index()
    sma = d["close"].rolling(sma_period).mean()
    up = (d["close"] > sma).shift(1)          # known only from prior close
    up.index = up.index.tz_convert(ET).normalize().date
    return up


def build_trades(m1: pd.DataFrame, entry_hm, open_hm, close_hm,
                 uptrend: pd.Series, use_trend: bool):
    """One row per trading day with the entry->close move and the day's context.
    Long-only late-day trade; also records the unconditional move for the null."""
    et = m1.tz_convert(ET)
    oh, om = open_hm
    eh, em = entry_hm
    ch, cm = close_hm
    rows = []
    for day, g in et.groupby(et.index.normalize()):
        date = day.date()
        o_close, o_open = _price_at(g, oh, om)
        e_close, _ = _price_at(g, eh, em)
        # exit = last bar at/just before the close time
        mod = g.index.hour * 60 + g.index.minute
        cbar = g[(mod <= ch * 60 + cm) & (mod >= eh * 60 + em)]
        if o_open is None or e_close is None or len(cbar) == 0:
            continue
        x_close = float(cbar["close"].iloc[-1])
        day_ret = e_close / o_open - 1.0            # RTH open -> entry
        late_ret = x_close / e_close - 1.0          # entry -> RTH close (the trade)
        up = bool(uptrend.get(date, False)) if use_trend else True
        has_up = (date in uptrend.index) if use_trend else True
        rows.append({
            "date": date, "year": day.year,
            "day_ret": day_ret, "late_ret": late_ret,
            "uptrend": up, "has_up": has_up,
            "entry": e_close,
        })
    return pd.DataFrame(rows)


def _stats(r: pd.Series):
    """mean, WR, t-stat of a return series (per-trade)."""
    n = len(r)
    if n == 0:
        return dict(n=0, mean=float("nan"), wr=float("nan"), t=float("nan"))
    m = r.mean()
    sd = r.std(ddof=1) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return dict(n=n, mean=m, wr=(r > 0).mean() * 100, t=t)


def _fmt(label, s, extra=""):
    return (f"  {label:26s} N={s['n']:5d}  WR={s['wr']:4.0f}%  "
            f"E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}{extra}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--open-et", default="09:30", help="RTH open time ET")
    ap.add_argument("--entry-et", default="15:00", help="entry time ET (power hour=15:00)")
    ap.add_argument("--close-et", default="16:00", help="RTH close time ET")
    ap.add_argument("--dip-thr", type=float, default=0.0,
                    help="go long only if day_ret < this %% (0=any down day; -0.5=aggressive)")
    ap.add_argument("--no-trend", action="store_true", help="disable SMA200 daily uptrend filter")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--perm", type=int, default=2000, help="null permutations")
    ap.add_argument("--oos", default="2024-07-01", help="IS/OOS split date")
    args = ap.parse_args()

    open_hm = tuple(int(x) for x in args.open_et.split(":"))
    entry_hm = tuple(int(x) for x in args.entry_et.split(":"))
    close_hm = tuple(int(x) for x in args.close_et.split(":"))
    use_trend = not args.no_trend

    print(f"Loading 1m bars {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    if len(m1) == 0:
        print("❌ no cached bars in range")
        return 1
    uptrend = build_daily_uptrend()
    t = build_trades(m1, entry_hm, open_hm, close_hm, uptrend, use_trend)
    if len(t) == 0:
        print("❌ no trading days built")
        return 1

    # cost in return terms: spread points / entry price, paid once (round-trip
    # spread ~= spread_pts total on a one-directional intraday hold)
    cost = 0.0 if args.gross else args.spread_pts
    t["cost"] = 0.0 if args.gross else cost / t["entry"]
    t["net"] = t["late_ret"] - t["cost"]

    trend_txt = f"uptrend SMA200 ON" if use_trend else "trend OFF"
    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    print(f"\nUS500 LATE-DAY DRIFT  entry {args.entry_et}ET → close {args.close_et}ET  "
          f"(open ref {args.open_et}ET)")
    print(f"  filtro: day_ret < {args.dip_thr:+.2f}%  |  {trend_txt}  |  {tag}")
    print(f"  {len(t)} trading days  {t['date'].iloc[0]} → {t['date'].iloc[-1]}")

    # 1) UNCONDITIONAL baseline: late-day drift on ALL days (gross)
    print("\n=== 1) BASELINE INCONDIZIONATA (drift entry→close, tutti i giorni, gross) ===")
    print(_fmt("tutti i giorni", _stats(t["late_ret"])))

    # 2) CONDITIONAL signal
    sig = t[t["day_ret"] < args.dip_thr / 100.0]
    if use_trend:
        sig = sig[sig["uptrend"] & sig["has_up"]]
    print(f"\n=== 2) SEGNALE CONDIZIONATO (day down < {args.dip_thr:+.2f}%"
          f"{' + uptrend' if use_trend else ''}) — {tag} ===")
    print(_fmt("segnale (net)", _stats(sig["net"])))
    print(_fmt("segnale (gross)", _stats(sig["late_ret"])))

    # 3) NULL TEST: does the down-day selection beat a RANDOM selection of the
    #    same size drawn from the same day pool? (structure vs. just being in-market)
    k = len(sig)
    pool = t["late_ret"].values
    if 20 <= k < len(pool):
        rng = np.random.default_rng(0)
        real_mean = sig["late_ret"].mean()
        null = np.array([rng.choice(pool, size=k, replace=False).mean()
                         for _ in range(args.perm)])
        pct = (null < real_mean).mean() * 100
        z = (real_mean - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n=== 3) TEST DEL NULLA (selezione down-day vs {args.perm} selezioni random di {k} giorni) ===")
        print(f"  E[ret] reale {real_mean*100:+.3f}%  vs  null {null.mean()*100:+.3f}%  "
              f"→ batte {pct:.0f}% random  z={z:+.2f}  → {verdict}")
    else:
        print(f"\n=== 3) TEST DEL NULLA — saltato (k={k}, servono ≥20 e < tutti) ===")

    # 4) IS / OOS
    split = pd.Timestamp(args.oos).date()
    is_ = sig[sig["date"] < split]
    oos = sig[sig["date"] >= split]
    print(f"\n=== 4) IN-SAMPLE / OUT-OF-SAMPLE (split {split}) — net ===")
    print(_fmt(f"IS  (<{split})", _stats(is_["net"])))
    print(_fmt(f"OOS (≥{split})", _stats(oos["net"])))

    # 5) per-year stability (net) + equity/DD assuming full-notional each trade
    print("\n=== 5) STABILITÀ ANNUALE (net) ===")
    for y, s in sig.groupby("year"):
        st = _stats(s["net"])
        print(f"   {y}: N={st['n']:4d}  WR={st['wr']:3.0f}%  E[ret]={st['mean']*100:+.3f}%  "
              f"somma={s['net'].sum()*100:+.1f}%  t={st['t']:+.2f}")

    tot = (1 + sig["net"]).prod() - 1
    eq = (1 + sig["net"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    yrs = max((sig["date"].iloc[-1] - sig["date"].iloc[0]).days / 365.25, 0.5)
    cagr = ((1 + tot) ** (1 / yrs) - 1) * 100 if tot > -1 else -100
    print(f"\n  Compounding 1x (full notional/trade): return {tot*100:+.1f}%  "
          f"CAGR {cagr:+.1f}%/yr  maxDD {mdd:.1f}%  ({len(sig)} trade)")
    print("  Promosso solo se: batte il nulla E netto costi positivo E stabile ogni anno E regge OOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
