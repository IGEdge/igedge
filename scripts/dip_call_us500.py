#!/usr/bin/env python3
"""
EDGE #1 (dip-buy) espresso COMPRANDO call scontate di IG — non il CFD.

Tesi: il dip-buy (RSI2<10 daily in uptrend, close>SMA200) è validato (WR 86% sul
prezzo). Su IG le CALL sono a SCONTO (IV ~0.6-0.77×VIX, misurato 14 lug 2026) →
comprarle è a buon mercato. Vantaggi vs CFD: rischio DEFINITO (max perdita = premio,
niente gap-risk che limitava la leva), NIENTE financing overnight (le opzioni non
lo pagano → cattura il drift overnight gratis), leva intrinseca.

Regole (no lookahead — segnale su barra daily chiusa):
  SEGNALE: RSI(2) < entry AND close > SMA200 (identico all'edge #1).
  AZIONE: compra una CALL (ATM o OTM), scadenza ~H giorni, tenuta a scadenza.
  Pricing REALE IG: IV della call = VIX × (atm_ratio − call_skew·moneyness_σ),
  comprata all'ASK (mid + spread/2). Payoff = max(S_exp − K, 0) − premio.

Confronto NULLA: stessa call comprata in giorni RANDOM (il dip aggiunge?).
Dati: us500_daily.csv + vix_daily.csv (2007-2026).

Usage:
  python scripts/dip_call_us500.py
  python scripts/dip_call_us500.py --moneyness 0.5 --horizon 8
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
US500_CSV = "data/research/us500_daily.csv"


def bs_call(S, K, T, sig):
    if T <= 0 or sig <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


def _rsi(close, period=2):
    d = close.diff(); up = d.clip(lower=0.0); dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _stats(r):
    n = len(r)
    if n == 0:
        return dict(n=0, mean=float("nan"), wr=float("nan"), t=float("nan"))
    m = float(np.mean(r)); sd = float(np.std(r, ddof=1)) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return dict(n=n, mean=m, wr=float(np.mean(np.array(r) > 0)) * 100, t=t)


def run(df, sig_pos, args):
    S = df["spx"].values; V = df["vix"].values; idx = df.index
    n = len(df); H = args.horizon
    rows = []
    i = 0
    sig_set = set(sig_pos)
    while i + H < n:
        if i in sig_set:
            s0 = S[i]; vix = V[i] / 100.0
            T = max((idx[i + H] - idx[i]).days, 1) / 365.0
            sT = vix * np.sqrt(T)
            K = round(s0 * (1 + args.moneyness * sT) / 5.0) * 5.0    # strike ATM/OTM
            m_sigma = args.moneyness                                  # OTM in σ
            iv = vix * max(args.atm_ratio - args.call_skew * m_sigma, 0.03)
            premium = bs_call(s0, K, T, iv) + args.spread / 2.0       # compri all'ask
            if premium <= 0:
                i += 1; continue
            s_exp = S[i + H]
            payoff = max(s_exp - K, 0.0) - premium
            rows.append({"date": idx[i].date(), "year": idx[i].year,
                         "ret": payoff / premium, "premium": premium, "K": K,
                         "move": s_exp / s0 - 1})
            i += H + 1
        else:
            i += 1
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-rsi", type=float, default=10.0)
    ap.add_argument("--horizon", type=int, default=7, help="giorni (trading) a scadenza")
    ap.add_argument("--moneyness", type=float, default=0.0, help="strike a m·σ OTM (0=ATM)")
    ap.add_argument("--atm-ratio", type=float, default=0.77, help="IV_ATM/VIX (misurato IG)")
    ap.add_argument("--call-skew", type=float, default=0.16, help="calo IV/VIX per σ OTM (call)")
    ap.add_argument("--spread", type=float, default=1.5, help="spread bid/ask call (pt)")
    ap.add_argument("--risk-frac", type=float, default=0.05, help="frazione equity a rischio (=premio)")
    ap.add_argument("--from", dest="dfrom", default="2007-01-01")
    args = ap.parse_args()

    vix = pd.read_csv(VIX_CSV); vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")
    spx = pd.read_csv(US500_CSV); spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")
    df = pd.concat([vix, spx], axis=1).dropna()
    df = df[df.index >= pd.Timestamp(args.dfrom)]
    df["sma200"] = df["spx"].rolling(200).mean()
    df["rsi2"] = _rsi(df["spx"], 2)

    mask = (df["rsi2"] < args.entry_rsi) & (df["spx"] > df["sma200"])
    sig_pos = [df.index.get_loc(ts) for ts in df.index[mask]]

    t = run(df, sig_pos, args)
    print(f"US500 DIP-BUY via CALL comprate  (RSI2<{args.entry_rsi:.0f} & close>SMA200)  "
          f"strike {args.moneyness:+.1f}σ  {args.horizon}gg  — IV call ~{args.atm_ratio:.2f}×VIX, spread {args.spread}pt")
    if len(t) == 0:
        print("  no trades"); return 0
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    st = _stats(t["ret"].values)
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)")
    print(f"  premio medio {t['premium'].mean():.1f}pt (= {t['premium'].mean()/df['spx'].mean()*100:.2f}% dello spot)")
    print(f"\n  SEGNALE: WR {st['wr']:.0f}%  ret/trade {st['mean']*100:+.1f}% del premio  t={st['t']:+.2f}")

    # nulla: stessa call in giorni random
    allpos = list(range(0, len(df) - args.horizon - 1, args.horizon + 1))
    tn = run(df, allpos, args); sn = _stats(tn["ret"].values)
    print(f"  NULLA  : WR {sn['wr']:.0f}%  ret/trade {sn['mean']*100:+.1f}%  t={sn['t']:+.2f}  (N={sn['n']})")
    print(f"  → il dip {'AGGIUNGE' if st['mean'] > sn['mean'] else 'NON aggiunge'} "
          f"({(st['mean']-sn['mean'])*100:+.1f}% vs nulla)")

    eq = 1.0
    for r in t["ret"].values:
        eq *= (1 + args.risk_frac * r)
    print(f"\n  Compounding @ {args.risk_frac:.0%} premio/trade: {(eq-1)*100:+.0f}%  "
          f"CAGR {((eq)**(1/yrs)-1)*100:+.1f}%/yr   maxloss/trade = −{args.risk_frac:.0%} equity (rischio DEFINITO)")
    print("\n  per anno (ret medio/trade % del premio):")
    for y, s in t.groupby("year"):
        ss = _stats(s["ret"].values)
        print(f"   {y}: N={ss['n']:2d}  WR={ss['wr']:3.0f}%  ret {ss['mean']*100:+5.0f}%  somma {s['ret'].sum()*100:+5.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
