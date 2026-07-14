#!/usr/bin/env python3
"""
Volatility Risk Premium (VRP) probe — is there an options edge worth pursuing?

The VRP is the systematic gap between IMPLIED vol (VIX, what options price in) and
the REALIZED vol that follows (what actually happens). If implied > realized on
average, SELLING options (defined-risk: put/call spreads, iron condors) harvests
an insurance premium. This is NON-directional -> it sidesteps the intraday/overnight
question entirely, and it's the most documented options edge.

This measures the premium (a market fact, broker-independent). It does NOT yet
model IG's option spreads — that's the demo paper-trade step. If the premium here
is small or unstable, the options route isn't worth the infra; if it's large and
steady (with a known tail), it is.

VRP_t = VIX_t − RV_{[t+1, t+21]}   (vol points, annualised %)
  RV = sqrt(252 · mean(daily log-ret²)) over the next 21 trading days.
This is exactly the P&L (in vol points) of shorting 1M vol at t. No lookahead as a
MEASUREMENT (the position opened at t realises over the forward window).

Data: data/research/vix_daily.csv (CBOE) + us500_daily.csv (S&P proxy).

Usage:
  python scripts/vrp_probe_us500.py
  python scripts/vrp_probe_us500.py --horizon 21
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

VIX_CSV = "data/research/vix_daily.csv"
US500_CSV = "data/research/us500_daily.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=21, help="forward RV window (trading days)")
    ap.add_argument("--from", dest="dfrom", default="2007-01-01")
    args = ap.parse_args()

    if not (os.path.exists(VIX_CSV) and os.path.exists(US500_CSV)):
        print("❌ manca vix_daily.csv o us500_daily.csv"); return 1

    vix = pd.read_csv(VIX_CSV)
    vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")

    spx = pd.read_csv(US500_CSV)
    spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")

    df = pd.concat([vix, spx], axis=1).dropna()
    df = df[df.index >= pd.Timestamp(args.dfrom)]
    df["ret"] = np.log(df["spx"]).diff()

    H = args.horizon
    # forward realized vol over the NEXT H days (annualised %), aligned to t
    r2 = df["ret"] ** 2
    fwd_var = r2.shift(-1).rolling(H).sum().shift(-(H - 1))   # sum of next-H squared rets at t
    df["rv_fwd"] = np.sqrt(252.0 / H * fwd_var) * 100.0
    df["vrp"] = df["vix"] - df["rv_fwd"]                      # short-vol P&L, vol points
    d = df.dropna(subset=["vrp"])

    n = len(d)
    vrp = d["vrp"]
    t = vrp.mean() / (vrp.std(ddof=1) / np.sqrt(n))
    print(f"VRP probe — VIX vs realized {H}d  |  {d.index[0].date()} → {d.index[-1].date()}  (N={n})")
    print(f"\n  VIX medio       {d['vix'].mean():5.2f}   RV{H}d medio {d['rv_fwd'].mean():5.2f}")
    print(f"  VRP medio       {vrp.mean():+5.2f} punti vol   (mediana {vrp.median():+.2f})")
    print(f"  VRP > 0         {(vrp > 0).mean()*100:.0f}% del tempo    t-stat {t:+.1f}")
    print(f"  VIX/RV medio    {(d['vix']/d['rv_fwd']).replace([np.inf,-np.inf],np.nan).median():.2f}x (mediano)")

    # tail: when short-vol LOSES big (RV spikes above VIX)
    worst = vrp.nsmallest(5)
    print(f"\n  Coda sinistra (peggiori giorni per chi VENDE vol, VRP più negativo):")
    for ts, v in worst.items():
        print(f"    {ts.date()}: VRP {v:+.1f}  (VIX {d.loc[ts,'vix']:.0f} → RV {d.loc[ts,'rv_fwd']:.0f})")

    print(f"\n  VRP medio per anno (punti vol):")
    for y, s in vrp.groupby(vrp.index.year):
        neg = (s < 0).mean() * 100
        print(f"   {y}: {s.mean():+5.2f}   (negativo {neg:3.0f}% dei giorni, min {s.min():+.0f})")

    # crude short-vol "equity": cumulative sum of monthly-sampled VRP (non-overlap)
    monthly = vrp.iloc[::H]
    cum = monthly.cumsum()
    dd = (cum.cummax() - cum)
    print(f"\n  Short-vol grezzo (VRP campionato ogni {H}g, non sovrapposto, {len(monthly)} 'mesi'):")
    print(f"    somma {cum.iloc[-1]:+.0f} punti vol   media/mese {monthly.mean():+.2f}   "
          f"WR {(monthly>0).mean()*100:.0f}%   maxDD {dd.max():.0f} punti")
    print(f"    ⚠️ è LORDO e SENZA spread opzioni IG: misura solo se il premio ESISTE.")
    print(f"       Prossimo: modellare put-spread + costo reale IG (catena) per la tradeabilità.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
