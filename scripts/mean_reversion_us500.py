#!/usr/bin/env python3
"""
Daily mean-reversion ("buy-the-dip") on US500 — the one candidate that FITS the
CFD cost structure: few trades (~10-20/yr) and short holds (days), so spread is
negligible and financing tiny. Documented edge in equity indices (short-term
mean-reversion on top of the upward drift; Connors RSI(2)).

Rules (long-only, no lookahead — signal on closed daily bar, fill next open):
  ENTRY: close > SMA200 (only buy dips in an uptrend) AND trigger fires
  EXIT : close > SMA(exit_ma)  OR  RSI(2) > exit_thr  OR  held >= max_hold days
Costs: spread points per round-trip + financing per day held (small).

TRIGGERS (C1 "MR Ensemble", docs/EDGE-candidati-da-testare.md — soglie standard
di letteratura, NON ottimizzate):
  t1  RSI(2) < entry_thr                      (baseline VALIDATO, default)
  t2  3+ chiusure consecutive in ribasso
  t3  %b Bollinger(20,2) < 0.05
  t4  VIX stretch: VIX > 1.05 × MA10(VIX)     (richiede vix_daily.csv)
  t5  RSI(2) cumulato 2gg < 35
  t6  SHORT: RSI(2) > 95 AND close < SMA200   (exit RSI2<30 / close<SMA / 7gg)
  union  = t1|t2|t3|t4|t5 (long)
Analisi marginale: --exclude-t1 tiene solo i giorni NON già coperti da t1.
Test del nulla: --null N = N run con giorni di entry casuali (stesso regime,
stesso numero, stesse exit) → percentile del reale.

Data: data/research/us500_daily.csv (IG daily, 2007-2026).

Usage:
  python scripts/mean_reversion_us500.py
  python scripts/mean_reversion_us500.py --trigger t2 --exclude-t1 --null 200
  python scripts/mean_reversion_us500.py --trigger t6 --max-hold 7
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
VIX_CSV = "data/research/vix_daily.csv"


def rsi(close: pd.Series, period: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def build_signals(df, args):
    """Boolean arrays per trigger. Tutti su barra CHIUSA (no lookahead)."""
    c = df["close"]
    up = c > df["sma200"]
    dn3 = (c.diff() < 0).rolling(3).sum() >= 3
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    pctb = (c - (mid - 2 * sd)) / (4 * sd)
    sig = {
        "t1": up & (df["rsi2"] < args.entry_thr),
        "t2": up & dn3,
        "t3": up & (pctb < 0.05),
        "t5": up & ((df["rsi2"] + df["rsi2"].shift(1)) < 35),
        "t6": (~up) & (df["rsi2"] > 95),          # SHORT
    }
    if "vix" in df.columns:
        sig["t4"] = up & (df["vix"] > 1.05 * df["vix"].rolling(10).mean())
    longs = [k for k in ("t1", "t2", "t3", "t4", "t5") if k in sig]
    sig["union"] = np.logical_or.reduce([sig[k].values for k in longs])
    sig["union"] = pd.Series(sig["union"], index=df.index)
    return {k: v.fillna(False).values for k, v in sig.items()}


def run_engine(sig, direction, df, args, spread, fin):
    """Il motore trade (identico al validato per il long): segnale su barra i →
    fill open i+1; exit su SMA/RSI/time; scale-in solo long."""
    o = df["open"].values
    c = df["close"].values
    sma_ex = df["sma_exit"].values
    r2 = df["rsi2"].values
    idx = df.index
    n = len(df)
    from_ts = pd.Timestamp(args.dfrom, tz="UTC") if args.dfrom else None
    to_ts = pd.Timestamp(args.dto, tz="UTC") if args.dto else None

    trades = []
    i = 200
    while i < n - 1:
        if to_ts is not None and idx[i] >= to_ts:
            break
        in_window = (from_ts is None or idx[i] >= from_ts)
        if in_window and sig[i]:
            units = [(i + 1, o[i + 1])]
            j = i + 1
            exit_i = None
            while j < n - 1:
                held = j - units[0][0]
                if args.stop_pct > 0 and direction > 0 and \
                        c[j] <= units[0][1] * (1 - args.stop_pct / 100.0):
                    exit_i = j + 1
                    break
                if direction > 0:
                    done = (c[j] > sma_ex[j]) or (r2[j] > args.exit_thr)
                else:   # short: reverted down / oversold again
                    done = (c[j] < sma_ex[j]) or (r2[j] < 100 - args.exit_thr)
                if done or held >= args.max_hold:
                    exit_i = j + 1
                    break
                if (direction > 0 and args.scale_in > 0 and len(units) <= args.scale_in
                        and r2[j] < args.add_thr and o[j + 1] < units[-1][1]):
                    units.append((j + 1, o[j + 1]))
                j += 1
            if exit_i is None:
                exit_i = n - 1
            exit_ = o[exit_i]
            per_net, per_gross = [], []
            for ei, ep in units:
                if args.intraday:
                    ndays = exit_i - ei
                    gr = 1.0
                    for d in range(ei, exit_i):
                        gr *= 1.0 + direction * (c[d] / o[d] - 1.0)
                    g = gr - 1.0
                    cst = spread / ep * ndays
                else:
                    dd = (idx[exit_i] - idx[ei]).days
                    g = direction * (exit_ / ep - 1)
                    cst = spread / ep + fin / 360.0 * max(dd, 1)
                per_gross.append(g)
                per_net.append(g - cst)
            trades.append({"entry_ts": idx[units[0][0]], "exit_ts": idx[exit_i],
                           "entry_i": units[0][0] - 1,
                           "year": idx[units[0][0]].year,
                           "days": (idx[exit_i] - idx[units[0][0]]).days,
                           "units": len(units), "entry_px": float(units[0][1]),
                           "gross": float(np.mean(per_gross)),
                           "net": float(np.mean(per_net))})
            i = exit_i
        else:
            i += 1
    return pd.DataFrame(trades)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", default="t1",
                    choices=["t1", "t2", "t3", "t4", "t5", "t6", "union"])
    ap.add_argument("--exclude-t1", action="store_true",
                    help="solo i giorni NON coperti da t1 (contributo marginale)")
    ap.add_argument("--null", type=int, default=0,
                    help="N run con entry random stesso regime (test del nulla)")
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
    ap.add_argument("--dump-trades", default=None,
                    help="scrive i trade in CSV (per i report grafici)")
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
    if os.path.exists(VIX_CSV):
        vx = pd.read_csv(VIX_CSV)
        vx["ts"] = pd.to_datetime(vx["ts"]).dt.tz_localize("UTC").dt.normalize()
        vx = vx.set_index("ts")["close"].rename("vix")
        df["vix"] = vx.reindex(df.index.normalize()).values
        df["vix"] = df["vix"].ffill()
    elif args.trigger in ("t4",):
        print(f"❌ trigger t4 richiede {VIX_CSV}")
        return 1

    sigs = build_signals(df, args)
    sig = sigs[args.trigger].copy()
    if args.exclude_t1:
        sig = sig & ~sigs["t1"]
    direction = -1 if args.trigger == "t6" else 1

    spread = 0.0 if args.gross else args.spread_pts
    fin = 0.0 if args.gross else args.fin_annual

    t = run_engine(sig, direction, df, args, spread, fin)
    if len(t) == 0:
        print("no trades")
        return 0
    if args.dump_trades:
        t.to_csv(args.dump_trades, index=False)
        print(f"[dump] {len(t)} trade → {args.dump_trades}")

    # equity + maxDD (per-trade compounding)
    eq = (1 + t["net"]).cumprod()
    mdd = ((eq.cummax() - eq) / eq.cummax()).max() * 100
    span_days = max((t["exit_ts"].iloc[-1] - t["entry_ts"].iloc[0]).days, 180)
    yrs = span_days / 365.25
    total = eq.iloc[-1] - 1
    cagr = ((1 + total) ** (1 / yrs) - 1) * 100
    m = (df.index >= t["entry_ts"].iloc[0]) & (df.index <= t["exit_ts"].iloc[-1])
    cw = df["close"][m].values
    bh = cw[-1] / cw[0] - 1 if len(cw) > 1 else float("nan")
    days_in = t["days"].clip(lower=1).sum()
    expo = days_in / span_days * 100

    name = {"t1": f"RSI2<{args.entry_thr:.0f}", "t2": "3 down closes",
            "t3": "%b<0.05", "t4": "VIX stretch", "t5": "cumRSI2<35",
            "t6": "SHORT RSI2>95 bear", "union": "UNION t1-t5"}[args.trigger]
    extra = " ESCLUSI giorni t1" if args.exclude_t1 else ""
    tag = "GROSS" if args.gross else f"NET (spread {args.spread_pts}pt, fin {args.fin_annual:.1%})"
    print(f"US500 daily {df.index[200].date()} → {df.index[-1].date()}")
    print(f"\n=== {'BUY-THE-DIP' if direction > 0 else 'FADE-THE-RIP'} "
          f"[{args.trigger}: {name}{extra}] — {tag} ===")
    print(f"  Trades:   {len(t)}   (~{len(t)/yrs:.0f}/anno)  esposizione {expo:.0f}% dei giorni")
    print(f"  Return:   {total*100:+.1f}%   CAGR {cagr:+.1f}%/yr   (buy&hold {bh*100:+.1f}%)")
    print(f"  maxDD:    {mdd:.1f}%")
    print(f"  WR:       {(t['net']>0).mean()*100:.0f}%   avg/trade {t['net'].mean()*100:+.2f}%   "
          f"avg hold {t['days'].mean():.1f}gg")
    print(f"  gross avg/trade {t['gross'].mean()*100:+.2f}%")
    yr = t.groupby("year")
    print("  per anno (net%): " + "  ".join(
        f"{y}:{(( 1+s['net']).prod()-1)*100:+.0f}" for y, s in yr))

    # ---- test del NULLA: entry random nello stesso regime, stesse exit ----
    if args.null > 0:
        rng = np.random.default_rng(42)
        c = df["close"].values
        s200 = df["sma200"].values
        up = (c > s200) if direction > 0 else (c < s200)
        eligible = np.where(up & ~np.isnan(s200))[0]
        eligible = eligible[(eligible >= 200) & (eligible < len(df) - 2)]
        k = len(t)
        null_means = []
        for _ in range(args.null):
            pick = rng.choice(eligible, size=min(k * 2, len(eligible)), replace=False)
            nsig = np.zeros(len(df), dtype=bool)
            nsig[pick] = True
            nt = run_engine(nsig, direction, df, args, spread, fin)
            if len(nt):
                null_means.append(nt["net"].mean())
        null_means = np.array(null_means)
        beat = (t["net"].mean() > null_means).mean() * 100
        print(f"\n  NULLA ({args.null} run, entry random stesso regime): "
              f"avg null {null_means.mean()*100:+.2f}%/trade  "
              f"reale {t['net'].mean()*100:+.2f}%  → batte {beat:.0f}% dei random"
              f"  {'✅' if beat >= 95 else '⚠️' if beat >= 80 else '❌'}")

    # Leverage sensitivity (only meaningful if positive edge)
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
