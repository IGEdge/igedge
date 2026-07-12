#!/usr/bin/env python3
"""
Daily mean-reversion ("buy-the-dip") on US500 — the one candidate that FITS the
CFD cost structure: few trades (~10-20/yr) and short holds (days), so spread is
negligible and financing tiny. Documented edge in equity indices (short-term
mean-reversion on top of the upward drift; Connors RSI(2)).

Rules (long-only, no lookahead — signal on closed daily bar, fill next open):
  ENTRY: close > SMA200 (only buy dips in an uptrend) AND RSI(2) < entry_thr
  EXIT : close > SMA(exit_ma)  OR  RSI(2) > exit_thr  OR  held >= max_hold days
Costs: spread points per round-trip + financing per day held (small).

Data: data/research/us500_daily.csv (IG daily, 2007-2026).

Usage:
  python scripts/mean_reversion_us500.py
  python scripts/mean_reversion_us500.py --entry-thr 5 --exit-ma 5
  python scripts/mean_reversion_us500.py --gross
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


def rsi(close: pd.Series, period: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-thr", type=float, default=10.0, help="RSI(2) entry below")
    ap.add_argument("--exit-thr", type=float, default=70.0, help="RSI(2) exit above")
    ap.add_argument("--exit-ma", type=int, default=5, help="exit if close > SMA(this)")
    ap.add_argument("--max-hold", type=int, default=10, help="max days held")
    ap.add_argument("--spread-pts", type=float, default=1.0)
    ap.add_argument("--fin-annual", type=float, default=0.055)
    ap.add_argument("--from", dest="dfrom", default=None, help="restrict ENTRIES from")
    ap.add_argument("--to", dest="dto", default=None, help="restrict ENTRIES to")
    ap.add_argument("--scale-in", type=int, default=0,
                    help="max EXTRA units added on deeper dips (0=off)")
    ap.add_argument("--add-thr", type=float, default=5.0,
                    help="RSI(2) below which to add a unit (scale-in)")
    ap.add_argument("--stop-pct", type=float, default=0.0,
                    help="catastrophe stop %% below first entry (0=off; demo: it HURTS)")
    ap.add_argument("--intraday", action="store_true",
                    help="hold only open→close each day, flat overnight (no gap/fin, +spread/day)")
    ap.add_argument("--gross", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(CSV):
        print(f"❌ {CSV} not found")
        return 1
    df = pd.read_csv(CSV)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df["sma200"] = df["close"].rolling(200).mean()
    df["sma_exit"] = df["close"].rolling(args.exit_ma).mean()
    df["rsi2"] = rsi(df["close"], 2)

    o = df["open"].values
    c = df["close"].values
    sma200 = df["sma200"].values
    sma_ex = df["sma_exit"].values
    r2 = df["rsi2"].values
    idx = df.index
    n = len(df)

    spread = 0.0 if args.gross else args.spread_pts
    fin = 0.0 if args.gross else args.fin_annual

    # indicators use FULL history; entries restricted to [from, to]
    from_ts = pd.Timestamp(args.dfrom, tz="UTC") if args.dfrom else None
    to_ts = pd.Timestamp(args.dto, tz="UTC") if args.dto else None

    trades = []
    i = 200
    while i < n - 1:
        if to_ts is not None and idx[i] >= to_ts:
            break
        in_window = (from_ts is None or idx[i] >= from_ts)
        # signal on closed bar i -> act next open (i+1)
        if in_window and not np.isnan(sma200[i]) and c[i] > sma200[i] and r2[i] < args.entry_thr:
            units = [(i + 1, o[i + 1])]        # (entry_idx, entry_price)
            j = i + 1
            exit_i = None
            while j < n - 1:
                held = j - units[0][0]
                # catastrophe stop on close below FIRST entry (demo: hurts MR)
                if args.stop_pct > 0 and c[j] <= units[0][1] * (1 - args.stop_pct / 100.0):
                    exit_i = j + 1
                    break
                if (c[j] > sma_ex[j]) or (r2[j] > args.exit_thr) or (held >= args.max_hold):
                    exit_i = j + 1
                    break
                # scale in: add a unit on a DEEPER dip (lower price + oversold)
                if (args.scale_in > 0 and len(units) <= args.scale_in
                        and r2[j] < args.add_thr and o[j + 1] < units[-1][1]):
                    units.append((j + 1, o[j + 1]))
                j += 1
            if exit_i is None:
                exit_i = n - 1
            exit_ = o[exit_i]
            # equal-weight units; net = mean per-unit return net of costs
            per_net, per_gross = [], []
            for ei, ep in units:
                if args.intraday:
                    # capture only RTH (open→close) each day, flat overnight:
                    # no overnight move, no financing, but spread every day
                    ndays = exit_i - ei
                    gr = 1.0
                    for d in range(ei, exit_i):
                        gr *= c[d] / o[d]
                    g = gr - 1.0
                    cst = spread / ep * ndays
                else:
                    dd = (idx[exit_i] - idx[ei]).days
                    g = exit_ / ep - 1
                    cst = spread / ep + fin / 360.0 * max(dd, 1)
                per_gross.append(g)
                per_net.append(g - cst)
            trades.append({"entry_ts": idx[units[0][0]], "exit_ts": idx[exit_i],
                           "year": idx[units[0][0]].year,
                           "days": (idx[exit_i] - idx[units[0][0]]).days,
                           "units": len(units),
                           "gross": float(np.mean(per_gross)),
                           "net": float(np.mean(per_net))})
            i = exit_i  # no overlap
        else:
            i += 1

    t = pd.DataFrame(trades)
    if len(t) == 0:
        print("no trades")
        return 0

    # equity + maxDD (per-trade compounding)
    eq = (1 + t["net"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    span_days = max((t["exit_ts"].iloc[-1] - t["entry_ts"].iloc[0]).days, 180)
    yrs = span_days / 365.25
    total = eq.iloc[-1] - 1
    cagr = ((1 + total) ** (1 / yrs) - 1) * 100
    # buy&hold over the same span
    m = (df.index >= t["entry_ts"].iloc[0]) & (df.index <= t["exit_ts"].iloc[-1])
    cw = df["close"][m].values
    bh = cw[-1] / cw[0] - 1 if len(cw) > 1 else float("nan")
    days_in = t["days"].clip(lower=1).sum()
    expo = days_in / span_days * 100

    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt, fin {args.fin_annual:.1%})"
    print(f"US500 daily {df.index[200].date()} → {df.index[-1].date()}")
    print(f"\n=== BUY-THE-DIP (RSI2<{args.entry_thr:.0f}, uptrend) — {tag} ===")
    print(f"  Trades:   {len(t)}   (~{len(t)/yrs:.0f}/anno)  esposizione {expo:.0f}% dei giorni")
    print(f"  Return:   {total*100:+.1f}%   CAGR {cagr:+.1f}%/yr   (buy&hold {bh*100:+.1f}%)")
    print(f"  maxDD:    {mdd:.1f}%")
    print(f"  WR:       {(t['net']>0).mean()*100:.0f}%   avg/trade {t['net'].mean()*100:+.2f}%   "
          f"avg hold {t['days'].mean():.1f}gg")
    print(f"  gross avg/trade {t['gross'].mean()*100:+.2f}%")
    yr = t.groupby("year")
    print("  per anno (net%): " + "  ".join(
        f"{y}:{(( 1+s['net']).prod()-1)*100:+.0f}" for y, s in yr))

    # Leverage sensitivity: same trades, equity levered Lx (position = L*equity).
    # Financing is already in `net` and is proportional to notional -> leverage-
    # neutral. The real limit is DRAWDOWN / worst single trade (gap risk).
    print("\n  Leva (stessi trade, equity con posizione Lx):")
    worst1 = t["net"].min() * 100
    for L in (1, 2, 3, 5):
        eqL = (1 + L * t["net"]).cumprod()
        mddL = ((eqL.cummax() - eqL) / eqL.cummax()).max() * 100
        totL = eqL.iloc[-1] - 1
        cagrL = ((1 + totL) ** (1 / yrs) - 1) * 100 if totL > -1 else -100.0
        print(f"   {L}x: CAGR {cagrL:+5.1f}%/yr  maxDD {mddL:4.0f}%  "
              f"peggior trade {worst1 * L:+5.1f}%")
    print(f"  (peggior singolo trade a 1x: {worst1:+.1f}% → il rischio gap "
          f"notturno scala con la leva)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
