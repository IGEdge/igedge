#!/usr/bin/env python3
"""
COPERTURA REATTIVA sul put-spread (richiesta utente, 14 lug 2026).

Idea: il put-spread mensile resta il motore (si apre SEMPRE, hold-to-expiry).
Durante la vita del trade, se il mercato ROMPE una soglia → COMPRI una put ATM
(la copertura) sulla stessa scadenza; la RIVENDI quando il panico ha fatto il
picco (VIX in raffreddamento — lo stesso segnale postspike già validato) o a
scadenza. Nei crash veri la put guadagna più di quanto perde lo spread (che è
cappato) → il trade può diventare PROFITTEVOLE anche col mercato a picco.
Il costo: i falsi allarmi (rompe la soglia e poi recupera) pagano il whipsaw.
QUESTO backtest misura se il saldo è positivo. NB: diverso dal tail-hedge
PREVENTIVO sempre-acceso (falsificato): qui la protezione è CONDIZIONATA.

Pricing reale (smile IG misurato), spread bid/ask per gamba, path giornaliero.
Baseline = identico programma SENZA copertura (deve riprodurre short_vol).

  python scripts/hedge_reactive_us500.py                       # postspike+TS 2009-
  python scripts/hedge_reactive_us500.py --entry postspike --from 2007-01-01   # col 2008
  python scripts/hedge_reactive_us500.py --entry calendar     # col feb-2020
  parametri: --trig 1.0 (soglia in σ) --hedge-exit cool|expiry --close-main
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


def bs(S, K, T, sig, kind="put"):
    if T <= 0 or sig <= 0:
        return max(K - S, 0.0) if kind == "put" else max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if kind == "put":
        return K * norm.cdf(-d2) - S * norm.cdf(-d1)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


def stats_line(name, rets):
    r = np.array(rets)
    n = len(r)
    m = r.mean()
    t = m / (r.std(ddof=1) / np.sqrt(n)) if n > 1 and r.std(ddof=1) > 0 else float("nan")
    return (f"  {name:28s} WR {100*(r>0).mean():3.0f}%  ret/trade {m*100:+5.1f}%  "
            f"t={t:+5.1f}  peggiore {r.min()*100:+4.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", choices=["postspike_ts", "postspike", "calendar"],
                    default="postspike_ts")
    ap.add_argument("--a", type=float, default=1.5)
    ap.add_argument("--b", type=float, default=2.5)
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--smile-atm", type=float, default=0.77)
    ap.add_argument("--smile-put-slope", type=float, default=0.30)
    ap.add_argument("--spread-leg", type=float, default=1.0, help="spread gambe OTM")
    ap.add_argument("--spread-atm", type=float, default=1.8, help="spread put ATM (copertura)")
    ap.add_argument("--vix-min", type=float, default=14.0, help="(solo calendar)")
    ap.add_argument("--vix-max", type=float, default=30.0)
    ap.add_argument("--spike-min", type=float, default=20.0)
    ap.add_argument("--cool", type=float, default=0.90)
    ap.add_argument("--trig", type=float, default=1.0,
                    help="copertura se close <= S0*(1-trig*σ√T) (in σ della mossa implicita)")
    ap.add_argument("--hedge-exit", choices=["cool", "expiry"], default="cool",
                    help="cool = vendi la put al raffreddamento VIX; expiry = tienila")
    ap.add_argument("--close-main", action="store_true",
                    help="chiudi ANCHE lo spread quando esci dalla copertura (coordinato)")
    ap.add_argument("--risk-frac", type=float, default=0.35)
    ap.add_argument("--from", dest="dfrom", default="2009-10-01")
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
    df = df[df.index >= pd.Timestamp(args.dfrom)]
    S, V, R = df["spx"].values, df["vix"].values, df["ratio"].values
    VMAX = df["vix"].rolling(10).max().values
    idx = df.index
    n = len(df)
    H = args.horizon

    def entry_ok(i):
        if args.entry == "calendar":
            return args.vix_min <= V[i] <= args.vix_max
        ok = V[i] >= args.spike_min and np.isfinite(VMAX[i]) and V[i] < args.cool * VMAX[i]
        if args.entry == "postspike_ts":
            ok = ok and np.isfinite(R[i]) and R[i] <= 1.0
        return ok

    base_rets, hedg_rets, rows = [], [], []
    i = 0
    while i + H < n:
        if not entry_ok(i):
            i += 1 if args.entry != "calendar" else H
            continue
        s0, vix0 = S[i], V[i] / 100.0
        T0 = max((idx[i + H] - idx[i]).days, 1) / 365.0
        sT = vix0 * np.sqrt(T0)
        K1, K2 = s0 * (1 - args.a * sT), s0 * (1 - args.b * sT)
        iv1 = vix0 * (args.smile_atm + args.smile_put_slope * args.a)
        iv2 = vix0 * (args.smile_atm + args.smile_put_slope * args.b)
        credit = (bs(s0, K1, T0, iv1) - bs(s0, K2, T0, iv2)) - args.spread_leg
        width = K1 - K2
        maxloss = width - credit
        if maxloss <= 0:
            i += H
            continue
        trigger_level = s0 * (1 - args.trig * sT)

        # ---- percorso giornaliero: baseline + copertura reattiva ----
        s_exp = S[i + H]
        pay_spread_exp = credit - (max(K1 - s_exp, 0) - max(K2 - s_exp, 0))
        base_rets.append(pay_spread_exp / maxloss)

        hedge_pnl, hedged, whip = 0.0, False, False
        j_h = None
        for j in range(i + 1, i + H):
            if S[j] <= trigger_level:            # ROTTURA → compra put ATM
                j_h = j
                break
        pnl = pay_spread_exp                      # default: spread a scadenza
        if j_h is not None:
            hedged = True
            sj, vj = S[j_h], V[j_h] / 100.0
            Tj = max((idx[i + H] - idx[j_h]).days, 1) / 365.0
            Kh = sj                               # put ATM al giorno della rottura
            ivh = vj * args.smile_atm
            cost_h = bs(sj, Kh, Tj, ivh) + args.spread_atm / 2.0     # compri all'ask
            # exit della copertura
            j_x = i + H                           # default: a scadenza
            if args.hedge_exit == "cool":
                vmax_h = V[j_h]
                for j in range(j_h + 1, i + H):
                    vmax_h = max(vmax_h, V[j])
                    if V[j] < args.cool * vmax_h and V[j] > V[i]:   # picco passato
                        j_x = j
                        break
            if j_x >= i + H:                      # tenuta a scadenza: intrinseco
                val_h = max(Kh - s_exp, 0.0)
            else:
                sx, vx = S[j_x], V[j_x] / 100.0
                Tx = max((idx[i + H] - idx[j_x]).days, 1) / 365.0
                val_h = bs(sx, Kh, Tx, vx * args.smile_atm) - args.spread_atm / 2.0
            hedge_pnl = val_h - cost_h
            whip = hedge_pnl < 0
            if args.close_main and j_x < i + H:   # chiusura coordinata dello spread
                sx, vx = S[j_x], V[j_x] / 100.0
                Tx = max((idx[i + H] - idx[j_x]).days, 1) / 365.0
                ivx1 = vx * (args.smile_atm + args.smile_put_slope * args.a)
                ivx2 = vx * (args.smile_atm + args.smile_put_slope * args.b)
                cost_close = (bs(sx, K1, Tx, ivx1) - bs(sx, K2, Tx, ivx2)) + args.spread_leg
                pnl = credit - cost_close
        hedg_rets.append((pnl + hedge_pnl) / maxloss)
        rows.append({"date": idx[i].date(), "year": idx[i].year, "hedged": hedged,
                     "whip": whip, "base": base_rets[-1], "hedged_ret": hedg_rets[-1],
                     "hedge_pnl_pts": hedge_pnl, "maxloss": maxloss})
        i += H

    t = pd.DataFrame(rows)
    if len(t) == 0:
        print("no trades")
        return 0
    print(f"COPERTURA REATTIVA put-spread {args.a}σ/{args.b}σ — entry={args.entry} "
          f"dal {args.dfrom}  trigger {args.trig}σ  exit={args.hedge_exit}"
          f"{' +chiusura coordinata' if args.close_main else ''}")
    print(f"  {len(t)} trade — copertura scattata in {int(t['hedged'].sum())} "
          f"({100*t['hedged'].mean():.0f}%), falsi allarmi {int(t['whip'].sum())}")
    print(stats_line("BASELINE (senza copertura)", t["base"]))
    print(stats_line("CON COPERTURA REATTIVA", t["hedged_ret"]))
    for cap, lab in [(0.35, "equity @35% rischio (≈€1000/contratto)")]:
        for col, nm in [("base", "baseline"), ("hedged_ret", "con copertura")]:
            eq = 1.0
            curve = []
            for r in t[col]:
                eq *= 1 + cap * r
                curve.append(eq)
            c = np.array(curve)
            dd = ((np.maximum.accumulate(c) - c) / np.maximum.accumulate(c)).max()
            yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 1)
            print(f"    {nm:14s}: CAGR {(c[-1]**(1/yrs)-1)*100:+.1f}%/yr  maxDD {dd*100:.0f}%")
    # dettagli: i trade dove la copertura è scattata
    h = t[t["hedged"]]
    if len(h):
        print("\n  trade con copertura scattata (base → con copertura, % del rischio):")
        for _, r in h.iterrows():
            print(f"   {r['date']}  {r['base']*100:+5.0f}% → {r['hedged_ret']*100:+5.0f}%"
                  f"   (put: {r['hedge_pnl_pts']:+.0f}pt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
