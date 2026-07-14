#!/usr/bin/env python3
"""
Defined-risk short-vol model on US500 (harvest the VRP with capped tail).

The VRP probe (vrp_probe_us500.py) showed implied > realized by ~3.6 vol points,
82% of the time — but with brutal tails (Feb 2020: RV 74 vs VIX 14). Selling vol
naked blows up; DEFINED-RISK structures cap the loss. This models that: sell a
1-month structure priced with Black-Scholes at the VIX-implied vol, settle at
expiry against the REALIZED S&P move. Gross of the real IG option spread (the
demo paper-trade step) — this answers "after capping the tail, is the edge still
there and how big?".

Structures:
  putspread : short put + long further-OTM put (bullish/neutral, rides index drift)
  condor    : iron condor (short put spread + short call spread) — pure delta-neutral VRP

Strikes set in implied-SD units: short at a·σ√T from spot, long wing at b·σ√T.
Priced with BS (r,q≈0 for a short-dated probe — negligible vs the VRP). Sized so
each trade risks a fixed fraction of equity of its own max loss.

No lookahead: enter at t with VIX_t; settle at t+H with the realized price.

Data: vix_daily.csv (CBOE) + us500_daily.csv. Usage:
  python scripts/short_vol_us500.py --strat putspread
  python scripts/short_vol_us500.py --strat condor --a 1.0 --b 2.0
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


def bs(S, K, T, sig, r=0.0, q=0.0, kind="put"):
    if T <= 0 or sig <= 0:
        intr = max(K - S, 0.0) if kind == "put" else max(S - K, 0.0)
        return intr
    d1 = (np.log(S / K) + (r - q + 0.5 * sig ** 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if kind == "put":
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)
    return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strat", choices=["putspread", "condor"], default="putspread")
    ap.add_argument("--horizon", type=int, default=21, help="days to expiry")
    ap.add_argument("--a", type=float, default=1.0, help="short strike, in σ√T from spot")
    ap.add_argument("--b", type=float, default=2.0, help="long wing, in σ√T from spot")
    ap.add_argument("--skew", type=float, default=0.0,
                    help="put skew: vol points (frazione) di IV IN PIÙ per ogni σ sotto l'ATM "
                         "(e in meno per le call). Reale SPX ~0.02 (2 pt/σ). 0=flat.")
    ap.add_argument("--iv-factor", type=float, default=1.0,
                    help="scala l'IV di PLACEMENT degli strike (banda resta su VIX).")
    ap.add_argument("--iv-price-factor", type=float, default=None,
                    help="scala l'IV di PRICING (credito) separatamente dal placement; "
                         "default = iv-factor. IG prezza ~0.77×VIX → prova placement 1.0 + pricing 0.77.")
    # --- SMILE REALE calibrato sui prezzi IG (14 lug 2026), sostituisce lo skew grezzo ---
    ap.add_argument("--real-smile", action="store_true",
                    help="prezza ogni gamba allo SMILE reale IG (modello a pendenza, "
                         "placement a σ=VIX). IV_put(nσ)=VIX·(atm+put_slope·n), "
                         "IV_call(nσ)=VIX·(atm−call_slope·n).")
    ap.add_argument("--smile-atm", type=float, default=0.77, help="IV_ATM/VIX (misurato 13.7/17.8)")
    ap.add_argument("--smile-put-slope", type=float, default=0.30,
                    help="pendenza skew put per σ OTM (1σ:+0.31→1.08, 2σ:+0.60→1.37 misurati)")
    ap.add_argument("--smile-call-slope", type=float, default=0.16,
                    help="pendenza skew call per σ OTM (1σ:−0.16→0.61 misurato)")
    ap.add_argument("--tail-hedge", type=float, default=0.0,
                    help="COMPRA una put a questa distanza in σ (es. 3.0), oltre l'ala del condor "
                         "(carry negativo, paga nei crash). 0=off.")
    ap.add_argument("--hedge-mult", type=float, default=1.0,
                    help="quante put di copertura per condor (default 1)")
    ap.add_argument("--risk-frac", type=float, default=0.10, help="equity fraction risked/trade (max loss)")
    ap.add_argument("--spread-leg", type=float, default=0.0,
                    help="real IG bid-ask per option leg, in index points (measured ~1.8)")
    ap.add_argument("--roundtrip", action="store_true",
                    help="pay the spread also to CLOSE (else hold to expiry = entry only)")
    # --- regime filters on the VIX (tail management) ---
    ap.add_argument("--vix-min", type=float, default=0.0, help="enter only if VIX >= this")
    ap.add_argument("--vix-max", type=float, default=999.0, help="enter only if VIX <= this (skip spikes)")
    ap.add_argument("--vix-ma", type=int, default=0, help="VIX rolling-mean window for regime (0=off)")
    ap.add_argument("--regime", choices=["off", "calm", "stormy"], default="off",
                    help="calm=VIX<MA, stormy=VIX>=MA (needs --vix-ma)")
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
    S = df["spx"].values
    V = df["vix"].values
    VMA = df["vix"].rolling(args.vix_ma).mean().values if args.vix_ma > 0 else None
    idx = df.index
    n = len(df)
    H = args.horizon

    trades = []
    skipped = 0
    i = 0
    while i + H < n:
        s0 = S[i]
        # IV di PLACEMENT (dove metti gli strike) e di PRICING (quanto credito incassi),
        # scalabili separatamente. La BANDA (regime) resta sulla VIX vera (V[i]).
        vix = V[i] / 100.0
        iv = vix * (1.0 if args.real_smile else args.iv_factor)    # placement (real-smile: a σ=VIX)
        ivp_factor = args.iv_price_factor if args.iv_price_factor is not None else args.iv_factor
        iv_price = vix * ivp_factor                                # pricing (se non real-smile)
        # tempo a scadenza in GIORNI DI CALENDARIO reali (convenzione opzioni /365)
        T = max((idx[i + H] - idx[i]).days, 1) / 365.0
        # regime filter (tail management): decide whether to sell vol here (su VIX vera)
        ok = args.vix_min <= V[i] <= args.vix_max
        if args.regime != "off" and VMA is not None and np.isfinite(VMA[i]):
            calm = V[i] < VMA[i]
            ok = ok and (calm if args.regime == "calm" else not calm)
        if not ok:
            skipped += 1
            i += H
            continue
        sT = iv * np.sqrt(T)                       # implied move (fraction) to expiry
        s_exp = S[i + H]
        Kp1 = s0 * (1 - args.a * sT)               # short put
        Kp2 = s0 * (1 - args.b * sT)               # long put (wing)
        # put skew: IV più alta più si scende (put), più bassa salendo (call).
        # Ogni gamba è a n·σ dall'ATM (n=a o b): iv_leg = iv + skew·n (put) / −skew·n (call).
        if args.real_smile:                         # SMILE reale (modello a pendenza)
            iv_ps = vix * (args.smile_atm + args.smile_put_slope * args.a)
            iv_pw = vix * (args.smile_atm + args.smile_put_slope * args.b)
        else:
            iv_ps = iv_price + args.skew * args.a
            iv_pw = iv_price + args.skew * args.b
        credit = bs(s0, Kp1, T, iv_ps, kind="put") - bs(s0, Kp2, T, iv_pw, kind="put")
        credit_put = credit
        width = Kp1 - Kp2
        credit_call = 0.0
        if args.strat == "condor":
            Kc1 = s0 * (1 + args.a * sT)           # short call
            Kc2 = s0 * (1 + args.b * sT)           # long call (wing)
            if args.real_smile:
                iv_cs = vix * max(args.smile_atm - args.smile_call_slope * args.a, 0.03)
                iv_cw = vix * max(args.smile_atm - args.smile_call_slope * args.b, 0.03)
            else:
                iv_cs = max(iv_price - args.skew * args.a, 0.01)   # call short (1σ sopra)
                iv_cw = max(iv_price - args.skew * args.b, 0.01)   # call wing (2σ sopra)
            credit_call = bs(s0, Kc1, T, iv_cs, kind="call") - bs(s0, Kc2, T, iv_cw, kind="call")
            credit += credit_call
        # real IG spread: each crossed leg costs half its bid-ask vs mid.
        n_legs = 4 if args.strat == "condor" else 2
        cross = n_legs * (2 if args.roundtrip else 1)
        spread_cost = args.spread_leg / 2.0 * cross
        credit -= spread_cost                      # you receive less than the mid credit
        maxloss = width - credit                   # per unit; symmetric wings => same both sides
        if maxloss <= 0:
            i += H; continue
        # payoff at expiry (per unit of structure)
        put_pay = max(Kp1 - s_exp, 0.0) - max(Kp2 - s_exp, 0.0)
        pnl = credit - put_pay
        if args.strat == "condor":
            call_pay = max(s_exp - Kc1, 0.0) - max(s_exp - Kc2, 0.0)
            pnl -= call_pay
        # tail hedge: COMPRA una put lontana (paga nei crash, carry negativo)
        if args.tail_hedge > 0:
            Kh = s0 * (1 - args.tail_hedge * sT)
            ivh = iv + args.skew * args.tail_hedge          # skew: put lontane IV alta
            Ph = bs(s0, Kh, T, ivh, kind="put") + args.spread_leg / 2.0  # compri all'ask
            pnl += args.hedge_mult * (max(Kh - s_exp, 0.0) - Ph)
        ret_on_risk = pnl / maxloss                # P&L as fraction of capital at risk
        trades.append({"date": idx[i].date(), "year": idx[i].year,
                       "credit": credit, "maxloss": maxloss,
                       "credit_put": credit_put, "credit_call": credit_call,
                       "ret": ret_on_risk, "spx_move": s_exp / s0 - 1})
        i += H

    t = pd.DataFrame(trades)
    if len(t) == 0:
        print("no trades"); return 0

    # equity: risk risk_frac of equity as the max-loss each trade
    eq = 1.0; curve = []
    for r in t["ret"].values:
        eq *= (1 + args.risk_frac * r)
        curve.append(eq)
    curve = np.array(curve)
    mdd = ((np.maximum.accumulate(curve) - curve) / np.maximum.accumulate(curve)).max() * 100
    yrs = max((pd.Timestamp(t['date'].iloc[-1]) - pd.Timestamp(t['date'].iloc[0])).days / 365.25, 0.5)
    cagr = (curve[-1] ** (1 / yrs) - 1) * 100

    sp = (f"NETTO spread {args.spread_leg}pt/gamba"
          f"{' round-trip' if args.roundtrip else ' (hold-to-expiry)'}"
          if args.spread_leg > 0 else "LORDO spread IG")
    reg = ""
    if args.vix_min > 0 or args.vix_max < 999:
        reg += f" VIX∈[{args.vix_min:.0f},{args.vix_max:.0f}]"
    if args.regime != "off":
        reg += f" regime={args.regime}(MA{args.vix_ma})"
    skew_txt = f" skew={args.skew*100:.1f}pt/σ" if args.skew else ""
    if args.tail_hedge:
        skew_txt += f" +tail-hedge@{args.tail_hedge}σ×{args.hedge_mult:g}"
    print(f"US500 SHORT-VOL {args.strat.upper()}  short@{args.a}σ long@{args.b}σ  {H}d{skew_txt}  "
          f"(rischio {args.risk_frac:.0%}/trade){reg}  — {sp}")
    print(f"  {t['date'].iloc[0]} → {t['date'].iloc[-1]}   {len(t)} trade (~{len(t)/yrs:.0f}/anno)"
          f"{f', {skipped} periodi saltati dal filtro' if skipped else ''}")
    print(f"\n  credito medio {t['credit'].mean():.1f}pt   maxloss medio {t['maxloss'].mean():.1f}pt   "
          f"(premio/rischio {t['credit'].mean()/t['maxloss'].mean():.2f})")
    if args.strat == "condor":
        # scomposizione: il lato call copre il suo spread? (2 gambe × spread_leg)
        call_spread_cost = 2 * args.spread_leg
        put_spread_cost = 2 * args.spread_leg
        cp = t["credit_put"].mean(); cc = t["credit_call"].mean()
        print(f"  ├─ lato PUT : credito lordo {cp:.1f}pt  → netto ~{cp - put_spread_cost:+.1f}pt "
              f"(spread {put_spread_cost:.1f})")
        print(f"  └─ lato CALL: credito lordo {cc:.1f}pt  → netto ~{cc - call_spread_cost:+.1f}pt "
              f"(spread {call_spread_cost:.1f})"
              + ("  ⚠️ lato call MAGRO: rischia di non coprire lo spread" if cc - call_spread_cost < 3 else ""))
    print(f"  WR {(t['ret']>0).mean()*100:.0f}%   ret medio/trade {t['ret'].mean()*100:+.1f}% del capitale a rischio   "
          f"t={t['ret'].mean()/(t['ret'].std(ddof=1)/np.sqrt(len(t))):+.1f}")
    print(f"  peggior trade {t['ret'].min()*100:+.0f}%   migliore {t['ret'].max()*100:+.0f}%")
    print(f"  Equity @ rischio {args.risk_frac:.0%}: {(curve[-1]-1)*100:+.0f}%   CAGR {cagr:+.1f}%/yr   maxDD {mdd:.0f}%")
    print("\n  per anno (ret medio/trade % del rischio):")
    for y, s in t.groupby("year"):
        print(f"   {y}: N={len(s):2d}  WR={(s['ret']>0).mean()*100:3.0f}%  "
              f"ret {s['ret'].mean()*100:+5.0f}%  peggior {s['ret'].min()*100:+4.0f}%")
    if args.spread_leg > 0:
        print(f"\n  ✓ NETTO dello spread IG reale ({args.spread_leg}pt/gamba). Hold-to-expiry = "
              "solo spread d'ingresso. Prossimo: conferma settlement IG + paper trading demo + gestione coda.")
    else:
        print("\n  ⚠️ LORDO dello spread opzioni IG. Passa --spread-leg 1.8 per il netto reale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
