#!/usr/bin/env python3
"""
Candidato: COMPRARE call (o call spread) su US500 IG SOLO post-panico.

Tesi: (1) su IG le CALL sono A SCONTO (smile misurato: ATM 0.77×VIX, +1σ
0.61×VIX) → comprarle costa poco; (2) dopo il panico (VIX≥20 in raffreddamento,
term structure rientrata) il mercato tende a rimbalzare → compri economico un
movimento probabile. Rischio DEFINITO = premio pagato (perfetto capitale piccolo),
niente overnight. È il "dip-buy in opzioni" fatto SOLO nel momento giusto.

Pricing REALE (smile IG misurato): iv_call(nσ) = VIX × max(0.77 − 0.16·n, 0.03);
compri all'ask (mid + spread/2), vendi (se spread) al bid. Hold a scadenza.
Test del nulla: stessa struttura in giorni RANDOM (il timing aggiunge?).

  python scripts/postpanic_call_us500.py                        # call spread ATM/+1σ
  python scripts/postpanic_call_us500.py --struct call          # call secca ATM
  python scripts/postpanic_call_us500.py --no-ts                # senza filtro VIX3M
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
from scipy.stats import norm

VIX_CSV = "data/research/vix_daily.csv"
VIX3M_CSV = "data/research/vix3m_daily.csv"
US500_CSV = "data/research/us500_daily.csv"
USD2EUR = 0.93


def bs_call(S, K, T, sig):
    if T <= 0 or sig <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


def _stats(r):
    n = len(r)
    m = float(np.mean(r)) if n else float("nan")
    sd = float(np.std(r, ddof=1)) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return n, m, float(np.mean(np.array(r) > 0)) * 100 if n else float("nan"), t


def run(df, sig_bool, args):
    S = df["spx"].values
    V = df["vix"].values
    idx = df.index
    n = len(df)
    H = args.horizon
    rows = []
    i = 0
    while i + H < n:
        if not sig_bool[i]:
            i += 1
            continue
        s0, vix = S[i], V[i] / 100.0
        T = max((idx[i + H] - idx[i]).days, 1) / 365.0
        sT = vix * np.sqrt(T)
        K1 = s0 * (1 + args.m1 * sT)
        iv1 = vix * max(args.atm - args.cskew * args.m1, 0.03)
        debit = bs_call(s0, K1, T, iv1) + args.spread / 2.0          # compri all'ask
        cap = None
        if args.struct == "spread":
            K2 = s0 * (1 + args.m2 * sT)
            iv2 = vix * max(args.atm - args.cskew * args.m2, 0.03)
            debit -= bs_call(s0, K2, T, iv2) - args.spread / 2.0     # vendi al bid
            cap = K2 - K1
        if debit <= 0:
            i += 1
            continue
        s_exp = S[i + H]
        pay = max(s_exp - K1, 0.0)
        if cap is not None:
            pay = min(pay, cap)
        rows.append({"date": idx[i].date(), "year": idx[i].year, "vix": V[i],
                     "debit": debit, "ret": (pay - debit) / debit,
                     "move": s_exp / s0 - 1})
        i += H          # una posizione per volta
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--struct", choices=["spread", "call"], default="spread")
    ap.add_argument("--m1", type=float, default=0.0, help="strike comprato (σ OTM)")
    ap.add_argument("--m2", type=float, default=1.0, help="strike venduto (σ OTM, solo spread)")
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--atm", type=float, default=0.77, help="IV_ATM/VIX (misurato)")
    ap.add_argument("--cskew", type=float, default=0.16, help="pendenza call per σ")
    ap.add_argument("--spread", type=float, default=1.5, help="bid/ask per gamba (pt)")
    ap.add_argument("--spike-min", type=float, default=20.0)
    ap.add_argument("--cool", type=float, default=0.90)
    ap.add_argument("--spike-window", type=int, default=10)
    ap.add_argument("--no-ts", action="store_true", help="senza filtro VIX/VIX3M<=1")
    ap.add_argument("--uptrend", action="store_true",
                    help="compra SOLO se close>SMA200 (filtro trend famiglia validata)")
    ap.add_argument("--null", type=int, default=200)
    ap.add_argument("--from", dest="dfrom", default="2009-10-01")
    ap.add_argument("--to", dest="dto", default=None, help="fine periodo (IS/OOS split)")
    args = ap.parse_args()

    vix = pd.read_csv(VIX_CSV)
    vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")
    spx = pd.read_csv(US500_CSV)
    spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")
    df = pd.concat([vix, spx], axis=1).dropna()
    v3 = pd.read_csv(VIX3M_CSV)
    v3["ts"] = pd.to_datetime(v3["ts"]).dt.tz_localize(None).dt.normalize()
    df["ratio"] = df["vix"] / v3.set_index("ts")["close"].reindex(df.index)
    df["sma200"] = df["spx"].rolling(200).mean()   # PRIMA del taglio date (warmup)
    df = df[df.index >= pd.Timestamp(args.dfrom)]
    if args.dto:
        df = df[df.index < pd.Timestamp(args.dto)]

    vmax = df["vix"].rolling(args.spike_window).max()
    sig = (df["vix"] >= args.spike_min) & (df["vix"] < args.cool * vmax)
    if not args.no_ts:
        sig = sig & (df["ratio"] <= 1.0)
    if args.uptrend:
        sig = sig & (df["spx"] > df["sma200"])
    sig = sig.fillna(False).values

    t = run(df, sig, args)
    if len(t) == 0:
        print("no trades")
        return 0
    yrs = max((pd.Timestamp(t["date"].iloc[-1]) - pd.Timestamp(t["date"].iloc[0])).days / 365.25, 0.5)
    n, m, wr, tstat = _stats(t["ret"].values)
    name = (f"call spread {args.m1:g}σ/{args.m2:g}σ" if args.struct == "spread"
            else f"call secca {args.m1:g}σ")
    print(f"US500 POST-PANICO COMPRA {name}  {args.horizon}gg  "
          f"(VIX≥{args.spike_min:.0f} raffredd. {args.cool}"
          f"{', TS≤1' if not args.no_ts else ''})  smile reale, spread {args.spread}pt/gamba")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {n} trade (~{n/yrs:.0f}/anno)   "
          f"debito medio ${t['debit'].mean():.0f}")
    print(f"  WR {wr:.0f}%   ret/trade {m*100:+.0f}% del premio   t={tstat:+.2f}")

    # test del NULLA: stessa struttura, giorni random (timing aggiunge?)
    rng = np.random.default_rng(42)
    nm = []
    for _ in range(args.null):
        pick = rng.choice(len(df) - args.horizon - 1, size=n * 2, replace=False)
        nb = np.zeros(len(df), dtype=bool)
        nb[pick] = True
        nt = run(df, nb, args)
        if len(nt):
            nm.append(nt["ret"].mean())
    nm = np.array(nm)
    beat = (m > nm).mean() * 100
    print(f"  NULLA ({args.null} run, giorni random): ret medio {nm.mean()*100:+.0f}%  "
          f"→ il timing batte {beat:.0f}% dei random  "
          f"{'✅' if beat >= 95 else '⚠️' if beat >= 80 else '❌'}")

    # € reali: contratti interi ($1/pt), su €1.000 e €10.000 — con maxDD
    for cap0, ncon in [(1000, 1), (10000, 10)]:
        eq, peak, mdd = float(cap0), float(cap0), 0.0
        for r in t.itertuples():
            k = min(ncon, max(1, int(eq // (cap0 / ncon))))
            eq += k * r.debit * r.ret * USD2EUR
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak)
        print(f"  €{cap0:,}: {ncon} contratto/i → finale €{eq:,.0f}  "
              f"({(eq/cap0-1)*100:+.0f}% in {yrs:.0f} anni, ~€{(eq-cap0)/yrs:,.0f}/anno)"
              f"   maxDD {mdd*100:.0f}%".replace(",", "."))
    print("\n  per anno (ret medio % del premio):")
    for y, s in t.groupby("year"):
        print(f"   {y}: N={len(s):2d}  WR={(s['ret']>0).mean()*100:3.0f}%  "
              f"ret {s['ret'].mean()*100:+5.0f}%  move medio S&P {s['move'].mean()*100:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
