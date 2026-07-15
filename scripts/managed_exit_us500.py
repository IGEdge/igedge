#!/usr/bin/env python3
"""
C8 — USCITE GESTITE ("incassa i vincitori prima") per gli edge #2 e #3.

Confronta HOLD-TO-EXPIRY (baseline validata) con la chiusura anticipata del
vincitore, a REALISMO PIENO:
  - valore mid-life ricalcolato OGNI GIORNO con lo smile REALE misurato su IG
    (ATM 0.77×VIX, pendenza put 0.30, call −0.16 — verificato 3× sul conto vero);
  - chiusura anticipata paga lo SPREAD D'USCITA PIENO per gamba, ALLARGATO
    quando il VIX è alto (stress → book più largo): exit_spread = spread_leg ×
    (1.5 se VIX<25, 2.0 se VIX≥25) — dichiarato e conservativo;
  - il capitale liberato RIENTRA: putspread al prossimo segnale post-panico,
    callspread al giorno dopo se l'uptrend regge (più cicli/anno = compounding).

Soglie SOLO da spec pre-registrata (niente sweep): put {50,25,10}% del credito
residuo; call {2x,3x} del debito e {60,80}% dell'ampiezza.
Kill: se nessuna soglia batte hold-to-expiry su CAGR E maxDD (netto uscita) su
entrambe le finestre → resta hold-to-expiry.

  python scripts/managed_exit_us500.py --strat putspread
  python scripts/managed_exit_us500.py --strat putspread --from 2007-01-01 --no-ts
  python scripts/managed_exit_us500.py --strat callspread
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

USD2EUR = 0.93
ATM, PSLOPE, CSLOPE = 0.77, 0.30, 0.16


def bs(S, K, T, sig, kind):
    if T <= 0 or sig <= 0:
        return max(K - S, 0.0) if kind == "put" else max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if kind == "put":
        return K * norm.cdf(-d2) - S * norm.cdf(-d1)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


def iv_put(S, K, vix, T):
    n = max((1 - K / S) / (vix * np.sqrt(T)), 0.0) if T > 0 else 0.0
    return vix * (ATM + PSLOPE * n)


def iv_call(S, K, vix, T):
    n = max((K / S - 1) / (vix * np.sqrt(T)), 0.0) if T > 0 else 0.0
    return vix * max(ATM - CSLOPE * n, 0.03)


def spread_value(strat, S, K1, K2, vix, T):
    """Valore MID della struttura al giorno corrente (smile reale)."""
    if strat == "putspread":     # short K1, long K2 (K2<K1): valore del residuo da RICOMPRARE
        return bs(S, K1, T, iv_put(S, K1, vix, T), "put") - bs(S, K2, T, iv_put(S, K2, vix, T), "put")
    return bs(S, K1, T, iv_call(S, K1, vix, T), "call") - bs(S, K2, T, iv_call(S, K2, vix, T), "call")


def run(df, args, exit_rule):
    """exit_rule(status)->bool decide la chiusura anticipata. None = baseline."""
    S, V, R = df["spx"].values, df["vix"].values, df["ratio"].values
    SMA = df["sma200"].values
    VMAX = df["vix"].rolling(10).max().values
    idx = df.index
    n = len(df)
    H = args.horizon
    rows = []
    i = 0
    while i + H < n:
        # ---- segnale d'ingresso ----
        if args.strat == "putspread":
            ok = V[i] >= 20 and np.isfinite(VMAX[i]) and V[i] < 0.90 * VMAX[i]
            if not args.no_ts:
                ok = ok and np.isfinite(R[i]) and R[i] <= 1.0
        else:
            ok = np.isfinite(SMA[i]) and S[i] > SMA[i]
        if not ok:
            i += 1 if args.strat == "putspread" else H
            continue
        s0, vix0 = S[i], V[i] / 100.0
        T0 = max((idx[i + H] - idx[i]).days, 1) / 365.0
        sT = vix0 * np.sqrt(T0)
        if args.strat == "putspread":
            K1, K2 = s0 * (1 - 1.5 * sT), s0 * (1 - 2.5 * sT)
            entry_mid = spread_value("putspread", s0, K1, K2, vix0, T0)
            credit = entry_mid - args.spread_leg          # vendi: incassi mid − spread
            width = K1 - K2
            risk = width - credit
        else:
            K1, K2 = s0, s0 * (1 + 1.0 * sT)
            entry_mid = spread_value("callspread", s0, K1, K2, vix0, T0)
            debit = entry_mid + args.spread_leg           # compri: paghi mid + spread
            width = K2 - K1
            risk = debit
        if risk <= 0:
            i += H
            continue
        # ---- percorso giornaliero ----
        exit_j, exit_pnl = None, None
        if exit_rule is not None:
            for j in range(i + 1, i + H):
                Tj = max((idx[i + H] - idx[j]).days, 1) / 365.0
                val = spread_value(args.strat, S[j], K1, K2, V[j] / 100.0, Tj)
                stress = 2.0 if V[j] >= 25 else 1.5
                cost_exit = args.spread_leg * stress      # 2 gambe attraversate
                if args.strat == "putspread":
                    st = {"residuo_frac": max(val, 0) / max(credit, 1e-9)}
                    if exit_rule(st):
                        exit_j = j
                        exit_pnl = credit - (val + cost_exit)   # ricompri il residuo
                        break
                else:
                    st = {"mult": (val - cost_exit) / debit,
                          "width_frac": (val - cost_exit) / width}
                    if exit_rule(st):
                        exit_j = j
                        exit_pnl = (val - cost_exit) - debit    # rivendi
                        break
        if exit_j is None:                                # a scadenza (intrinseco)
            s_exp = S[i + H]
            if args.strat == "putspread":
                pay = max(K1 - s_exp, 0) - max(K2 - s_exp, 0)
                exit_pnl = credit - pay
            else:
                pay = min(max(s_exp - K1, 0), width)
                exit_pnl = pay - debit
            exit_j = i + H
        rows.append({"date": idx[i].date(), "year": idx[i].year,
                     "ret": exit_pnl / risk, "risk": risk,
                     "held": exit_j - i, "early": exit_j < i + H})
        # ---- riciclo del capitale ----
        if args.strat == "putspread":
            i = exit_j + 1        # torna a cercare il segnale dal giorno dopo
        else:
            i = exit_j + 1 if exit_j < i + H else i + H
    return pd.DataFrame(rows)


def report(name, t, risk_frac=0.12):
    r = t["ret"].values
    yrs = max((pd.Timestamp(t["date"].iloc[-1]) - pd.Timestamp(t["date"].iloc[0])).days / 365.25, 1)
    eq, curve = 1.0, []
    for x in r:
        eq *= 1 + risk_frac * x
        curve.append(eq)
    c = np.array(curve)
    mdd = ((np.maximum.accumulate(c) - c) / np.maximum.accumulate(c)).max() * 100
    tstat = r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else float("nan")
    early = t["early"].mean() * 100
    print(f"  {name:34s} {len(t):3d} trade (~{len(t)/yrs:.0f}/anno)  WR {100*(r>0).mean():3.0f}%  "
          f"ret {r.mean()*100:+5.1f}%  t={tstat:+5.1f}  worst {r.min()*100:+4.0f}%  "
          f"CAGR@{risk_frac:.0%} {(c[-1]**(1/yrs)-1)*100:+.1f}%  maxDD {mdd:.0f}%  "
          f"(uscite anticipate {early:.0f}%, hold medio {t['held'].mean():.0f}gg)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strat", choices=["putspread", "callspread"], default="putspread")
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--spread-leg", type=float, default=1.0)
    ap.add_argument("--no-ts", action="store_true")
    ap.add_argument("--risk-frac", type=float, default=0.35)
    ap.add_argument("--from", dest="dfrom", default="2009-10-01")
    args = ap.parse_args()

    vix = pd.read_csv("data/research/vix_daily.csv")
    vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")
    spx = pd.read_csv("data/research/us500_daily.csv")
    spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")
    df = pd.concat([vix, spx], axis=1).dropna()
    v3 = pd.read_csv("data/research/vix3m_daily.csv")
    v3["ts"] = pd.to_datetime(v3["ts"]).dt.tz_localize(None).dt.normalize()
    df["ratio"] = df["vix"] / v3.set_index("ts")["close"].reindex(df.index)
    df["sma200"] = df["spx"].rolling(200).mean()
    df = df[df.index >= pd.Timestamp(args.dfrom)]

    print(f"C8 USCITE GESTITE — {args.strat}  dal {args.dfrom}"
          f"{' (senza TS)' if args.no_ts else ''}  — smile reale, uscita paga "
          f"spread pieno ×1.5 (×2 se VIX≥25)")
    report("BASELINE hold-to-expiry", run(df, args, None), args.risk_frac)
    if args.strat == "putspread":
        for frac in (0.50, 0.25, 0.10):
            t = run(df, args, lambda st, f=frac: st["residuo_frac"] <= f)
            report(f"chiudi a residuo ≤{frac:.0%} del credito", t, args.risk_frac)
    else:
        for m in (2.0, 3.0):
            t = run(df, args, lambda st, m=m: st["mult"] >= m)
            report(f"chiudi a {m:.0f}× il debito", t, args.risk_frac)
        for wf in (0.60, 0.80):
            t = run(df, args, lambda st, w=wf: st["width_frac"] >= w)
            report(f"chiudi a {wf:.0%} dell'ampiezza", t, args.risk_frac)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
