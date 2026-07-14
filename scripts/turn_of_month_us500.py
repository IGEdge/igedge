#!/usr/bin/env python3
"""
Turn-of-Month (ToM) seasonality on US500 (EDGES.md Strategy E).

Documented effect (Ariel 1987; Lakonishok & Smidt 1988): the last 2 trading days
of a month + the first 3 of the next concentrate a disproportionate share of
monthly equity returns. Few trades (~5/month) -> spread ok on CFD; intraday
(open->close each ToM day) -> flat overnight, no financing, no gap.

Rules (long-only):
  ToM day = one of {last 2 trading days of its month} ∪ {first 3 of its month}.
  ENTRY long at the daily open of each ToM day; EXIT at that day's close (intraday
  pure, flat overnight). Optional daily uptrend filter (close_{t-1} > SMA200).

Apparatus:
  - ToM vs non-ToM vs ALL: mean daily open->close return, WR, t-stat.
  - NULL TEST: does the ToM selection beat a RANDOM equal-size subset of days?
  - Also close-to-close (captures overnight) and the 5-day window-hold variant.
  - Net of costs (spread pts), IS/OOS split, per-year stability.

No lookahead: ToM membership is calendar-defined; the trend filter uses the prior
closed daily bar (shift 1). Data: data/research/us500_daily.csv (2007-2026).

Usage:
  python scripts/turn_of_month_us500.py
  python scripts/turn_of_month_us500.py --trend --from 2016-01-01
  python scripts/turn_of_month_us500.py --last 2 --first 3 --gross
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

CSV = "data/research/us500_daily.csv"


def _stats(r: pd.Series) -> dict:
    n = len(r)
    if n == 0:
        return dict(n=0, mean=float("nan"), wr=float("nan"), t=float("nan"))
    m = r.mean()
    sd = r.std(ddof=1) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return dict(n=n, mean=m, wr=(r > 0).mean() * 100, t=t)


def _fmt(label, s):
    return (f"  {label:22s} N={s['n']:5d}  WR={s['wr']:4.0f}%  "
            f"E[ret]={s['mean']*100:+.3f}%  t={s['t']:+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default=None)
    ap.add_argument("--to", dest="dto", default=None)
    ap.add_argument("--last", type=int, default=2, help="last N trading days of month")
    ap.add_argument("--first", type=int, default=3, help="first N trading days of month")
    ap.add_argument("--trend", action="store_true", help="require close_{t-1} > SMA200")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--gross", action="store_true")
    ap.add_argument("--perm", type=int, default=5000)
    ap.add_argument("--oos", default="2017-01-01", help="IS/OOS split date")
    args = ap.parse_args()

    if not os.path.exists(CSV):
        print(f"❌ {CSV} not found")
        return 1
    df = pd.read_csv(CSV)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df["sma200"] = df["close"].rolling(200).mean()
    df["uptrend"] = (df["close"] > df["sma200"]).shift(1)   # prior closed bar

    # within-calendar-month trading-day ranks
    ym = df.index.to_period("M")
    rank_asc = df.groupby(ym).cumcount() + 1
    grp_n = df.groupby(ym)["close"].transform("size").values
    rank_desc = grp_n - rank_asc.values + 1
    df["is_tom"] = (rank_asc.values <= args.first) | (rank_desc <= args.last)

    df["ret_oc"] = df["close"] / df["open"] - 1.0           # intraday open->close
    df["ret_cc"] = df["close"] / df["close"].shift(1) - 1.0  # close-to-close

    # restrict analysis window (keep SMA200 warmup by slicing after indicators)
    full = df.copy()
    if args.dfrom:
        df = df[df.index >= pd.Timestamp(args.dfrom, tz="UTC")]
    if args.dto:
        df = df[df.index <= pd.Timestamp(args.dto, tz="UTC")]
    df = df.dropna(subset=["ret_oc"])
    df = df[df.index >= full.index[200]]                    # need SMA200 defined

    cost = 0.0 if args.gross else args.spread_pts
    df["cost"] = 0.0 if args.gross else cost / df["open"]
    df["net_oc"] = df["ret_oc"] - df["cost"]

    tom = df[df["is_tom"]]
    if args.trend:
        tom = tom[tom["uptrend"] == True]
    non = df[~df["is_tom"]]

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt)"
    print(f"US500 TURN-OF-MONTH  (last {args.last} + first {args.first} = "
          f"~{args.last+args.first} gg/mese)  {'+ uptrend' if args.trend else ''}  {tag}")
    print(f"  {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} trading days)")

    print("\n=== 1) ToM vs NON-ToM vs TUTTI (intraday open→close, gross) ===")
    print(_fmt("ToM", _stats(tom["ret_oc"])))
    print(_fmt("non-ToM", _stats(non["ret_oc"])))
    print(_fmt("tutti", _stats(df["ret_oc"])))
    print(_fmt("ToM (NET costi)", _stats(tom["net_oc"])))

    print("\n=== 2) confronto close-to-close (cattura anche overnight) ===")
    print(_fmt("ToM  (cc)", _stats(tom["ret_cc"])))
    print(_fmt("non-ToM (cc)", _stats(non["ret_cc"])))

    # 3) NULL TEST: ToM selection vs random equal-size subset of days
    k = len(tom)
    pool = df["ret_oc"].values
    if 20 <= k < len(pool):
        rng = np.random.default_rng(0)
        real = tom["ret_oc"].mean()
        null = np.array([rng.choice(pool, size=k, replace=False).mean()
                         for _ in range(args.perm)])
        pct = (null < real).mean() * 100
        z = (real - null.mean()) / null.std() if null.std() > 0 else float("nan")
        verdict = ("STRUTTURA ✓" if pct >= 95 else "debole" if pct >= 80 else "no-edge")
        print(f"\n=== 3) TEST DEL NULLA (ToM vs {args.perm} subset random di {k} giorni) ===")
        print(f"  E[ret] ToM {real*100:+.3f}%  vs  null {null.mean()*100:+.3f}%  "
              f"→ batte {pct:.0f}% random  z={z:+.2f}  → {verdict}")

    # 4) IS / OOS (net intraday)
    split = pd.Timestamp(args.oos, tz="UTC")
    is_ = tom[tom.index < split]
    oos = tom[tom.index >= split]
    print(f"\n=== 4) IN-SAMPLE / OUT-OF-SAMPLE (split {split.date()}) — net intraday ===")
    print(_fmt(f"IS  (<{split.date()})", _stats(is_["net_oc"])))
    print(_fmt(f"OOS (≥{split.date()})", _stats(oos["net_oc"])))

    # 5) per-year (net intraday) + compounding
    print("\n=== 5) STABILITÀ ANNUALE (net intraday) ===")
    for y, s in tom.groupby(tom.index.year):
        st = _stats(s["net_oc"])
        print(f"   {y}: N={st['n']:3d}  WR={st['wr']:3.0f}%  E[ret]={st['mean']*100:+.3f}%  "
              f"somma={s['net_oc'].sum()*100:+.1f}%")
    tot = (1 + tom["net_oc"]).prod() - 1
    eq = (1 + tom["net_oc"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    yrs = max((tom.index[-1] - tom.index[0]).days / 365.25, 0.5)
    cagr = ((1 + tot) ** (1 / yrs) - 1) * 100 if tot > -1 else -100
    print(f"\n  Compounding 1x (full notional/ToM-day): return {tot*100:+.1f}%  "
          f"CAGR {cagr:+.1f}%/yr  maxDD {mdd:.1f}%  ({len(tom)} trade, ~{len(tom)/yrs:.0f}/anno)")

    # 6) window-hold variant: open of first ToM day -> close of last ToM day
    #    (multi-day: has overnight + financing; reported gross for comparison)
    print("\n=== 6) VARIANTE HOLD-FINESTRA (open primo ToM → close ultimo ToM, gross) ===")
    win_rets = []
    d2 = df[df["is_tom"]]
    block = (~d2.index.to_series().diff().le(pd.Timedelta(days=5))).cumsum()
    for _, b in d2.groupby(block.values):
        if len(b) >= 2:
            win_rets.append(b["close"].iloc[-1] / b["open"].iloc[0] - 1)
    wr = pd.Series(win_rets)
    if len(wr):
        st = _stats(wr)
        print(_fmt("finestra ToM", st) + f"   (hold {len(wr)} finestre)")
    print("\n  Promosso solo se: batte il nulla E netto costi positivo E stabile E regge OOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
