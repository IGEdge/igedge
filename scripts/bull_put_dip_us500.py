#!/usr/bin/env python3
"""
EDGE #3 (candidato) — Bull-put sui dip: l'EDGE #1 (dip-buy) espresso via opzioni.

Idea (docs/EDGE-option-combinato.md): quando scatta il segnale VALIDATO del dip-buy
(RSI2<10 daily in uptrend, close>SMA200), la volatilità implicita è gonfiata dal
ribasso. Invece di comprare il CFD, si VENDE un BULL PUT SPREAD (a rischio definito,
credito) sfruttando: (a) il premio gonfiato dal panico, (b) la mean-reversion
rialzista dell'S&P (l'edge #1). Tenuto a scadenza (cash-settled).

Perché è interessante: profitta PROPRIO quando l'iron condor (EDGE #2) soffre — il
mercato è sceso → il put side del condor perde → ma il bull-put-sui-dip guadagna sul
rimbalzo. Complemento naturale, se timing-ato dal segnale reale (non dall'emozione).

Regole (long-only sul premio, no lookahead — segnale su barra daily chiusa):
  SEGNALE: RSI(2) < entry_rsi  AND  close > SMA200  (identico a EDGE #1).
  STRUTTURA: vendi put a Kp1 = S·(1 − a·σ√T), compra put a Kp2 = S·(1 − b·σ√T).
             σ dal VIX; skew opzionale; una posizione per volta (non-overlap).
  EXIT: a scadenza (H giorni), settlement a intrinseco.

Confronto col NULLA: stesso bull put venduto ogni H giorni SENZA segnale → il dip
aggiunge edge? Dati: us500_daily.csv + vix_daily.csv (2007-2026).

Usage:
  python scripts/bull_put_dip_us500.py
  python scripts/bull_put_dip_us500.py --horizon 10 --a 1.0 --b 2.0 --spread-leg 1.8
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


def bs_put(S, K, T, sig, r=0.0, q=0.0):
    if T <= 0 or sig <= 0:
        return max(K - S, 0.0)
    d1 = (np.log(S / K) + (r - q + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def rsi(close: pd.Series, period: int = 2) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0); dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _stats(r: np.ndarray) -> dict:
    n = len(r)
    if n == 0:
        return dict(n=0, mean=float("nan"), wr=float("nan"), t=float("nan"))
    m = float(np.mean(r)); sd = float(np.std(r, ddof=1)) if n > 1 else float("nan")
    t = m / (sd / np.sqrt(n)) if sd and sd > 0 else float("nan")
    return dict(n=n, mean=m, wr=float(np.mean(np.array(r) > 0)) * 100, t=t)


def price_bull_put(S, iv, T, a, b, skew, spread_leg):
    """Ritorna (credit_netto, maxloss, Kp1, Kp2)."""
    sT = iv * np.sqrt(T)
    Kp1 = S * (1 - a * sT)          # short put
    Kp2 = S * (1 - b * sT)          # long put (wing)
    iv1 = iv + skew * a
    iv2 = iv + skew * b
    credit = bs_put(S, Kp1, T, iv1) - bs_put(S, Kp2, T, iv2)
    credit -= 2 * spread_leg / 2.0 * 1  # 2 gambe × mezzo spread (hold-to-expiry)
    width = Kp1 - Kp2
    return credit, width - credit, Kp1, Kp2


def run(df, signal_idx, args):
    """Esegue i bull put ai giorni in signal_idx (non-overlap), ritorna DataFrame trade."""
    S = df["spx"].values; V = df["vix"].values; idx = df.index
    n = len(df); H = args.horizon
    rows = []
    sig_set = set(signal_idx)
    i = 0
    while i + H < n:
        if i in sig_set and (args.vix_max <= 0 or V[i] <= args.vix_max):
            s0 = S[i]; iv = V[i] / 100.0
            T = max((idx[i + H] - idx[i]).days, 1) / 365.0
            credit, maxloss, Kp1, Kp2 = price_bull_put(s0, iv, T, args.a, args.b,
                                                       args.skew, args.spread_leg)
            if maxloss <= 0:
                i += 1; continue
            s_exp = S[i + H]
            pay = max(Kp1 - s_exp, 0.0) - max(Kp2 - s_exp, 0.0)
            pnl = credit - pay
            rows.append({"date": idx[i].date(), "year": idx[i].year,
                         "ret": pnl / maxloss, "credit": credit, "maxloss": maxloss,
                         "vix": V[i], "move": s_exp / s0 - 1})
            i += H + 1                 # non-overlap
        else:
            i += 1
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-rsi", type=float, default=10.0)
    ap.add_argument("--horizon", type=int, default=10, help="giorni (trading) a scadenza")
    ap.add_argument("--a", type=float, default=1.0, help="short put a a·σ√T")
    ap.add_argument("--b", type=float, default=2.0, help="ala a b·σ√T")
    ap.add_argument("--skew", type=float, default=0.02)
    ap.add_argument("--spread-leg", type=float, default=1.8)
    ap.add_argument("--vix-max", type=float, default=0.0, help="salta se VIX> (0=off)")
    ap.add_argument("--risk-frac", type=float, default=0.10)
    ap.add_argument("--from", dest="dfrom", default="2007-01-01")
    args = ap.parse_args()

    vix = pd.read_csv(VIX_CSV); vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")
    spx = pd.read_csv(US500_CSV); spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")
    df = pd.concat([vix, spx], axis=1).dropna()
    df = df[df.index >= pd.Timestamp(args.dfrom)].reset_index().rename(columns={"index": "ts"})
    df = df.set_index("ts")
    df["sma200"] = df["spx"].rolling(200).mean()
    df["rsi2"] = rsi(df["spx"], 2)

    # segnale dip-buy (barra chiusa): RSI2<entry AND close>SMA200
    mask = (df["rsi2"] < args.entry_rsi) & (df["spx"] > df["sma200"])
    sig_pos = [df.index.get_loc(ts) for ts in df.index[mask]]

    t = run(df, sig_pos, args)
    tag = f"skew {args.skew*100:.0f}pt/σ, spread {args.spread_leg}pt, hold-to-expiry"
    print(f"US500 BULL-PUT sui DIP  (RSI2<{args.entry_rsi:.0f} & close>SMA200)  "
          f"short@{args.a}σ ala@{args.b}σ  {args.horizon}gg  — {tag}")
    if len(t) == 0:
        print("  no trades"); return 0
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    st = _stats(t["ret"].values)
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)")
    print(f"  credito medio {t['credit'].mean():.1f}pt  maxloss medio {t['maxloss'].mean():.1f}pt  "
          f"VIX medio all'ingresso {t['vix'].mean():.1f}")
    print(f"\n  SEGNALE:  WR {st['wr']:.0f}%  ret/trade {st['mean']*100:+.1f}% del rischio  t={st['t']:+.2f}")

    # confronto NULLA: stesso bull put ogni H giorni SENZA segnale
    allpos = list(range(0, len(df) - args.horizon - 1, args.horizon + 1))
    tn = run(df, allpos, args)
    sn = _stats(tn["ret"].values)
    print(f"  NULLA:    WR {sn['wr']:.0f}%  ret/trade {sn['mean']*100:+.1f}%  t={sn['t']:+.2f}  "
          f"(bull put ogni {args.horizon}gg senza segnale, N={sn['n']})")
    print(f"  → il dip {'AGGIUNGE edge' if st['mean'] > sn['mean'] else 'NON aggiunge'} "
          f"({(st['mean']-sn['mean'])*100:+.1f}% vs nulla)")

    # equity + per-anno (per vedere se copre gli anni-crash del condor)
    eq = 1.0
    for r in t["ret"].values:
        eq *= (1 + args.risk_frac * r)
    tot = eq - 1
    print(f"\n  Compounding @ {args.risk_frac:.0%}/trade: {tot*100:+.0f}%  CAGR "
          f"{((eq)**(1/yrs)-1)*100:+.1f}%/yr   (peggior trade {t['ret'].min()*100:+.0f}% del rischio)")
    print("\n  Per anno (ret medio/trade % del rischio) — occhio agli anni-crash del condor:")
    for y, s in t.groupby("year"):
        ss = _stats(s["ret"].values)
        flag = "  ← anno duro condor" if y in (2008, 2018, 2020, 2022) else ""
        print(f"   {y}: N={ss['n']:2d}  WR={ss['wr']:3.0f}%  ret {ss['mean']*100:+5.0f}%  "
              f"somma {s['ret'].sum()*100:+5.0f}%{flag}")
    print("\n  Promosso solo se: batte il nulla E positivo netto E aiuta negli anni-crash del condor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
