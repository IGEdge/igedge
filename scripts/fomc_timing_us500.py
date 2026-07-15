#!/usr/bin/env python3
"""
C9 — Pre-FOMC drift come TIMING d'ingresso della call mensile (spec pipeline).

Test in 2 passi (kill pre-registrati):
 1. EFFETTO GREZZO: ritorno close(T−1)→close(T) nei giorni di annuncio FOMC
    vs tutti gli altri giorni. Split pre/post-2015 (pubblicazione Lucca-Moench).
    KILL: se il post-2015 è ≤ 0 → morto, non si passa al punto 2.
 2. OVERLAY: call spread ATM/+1σ (edge #3, smile reale) aperta a T−1 della Fed
    (solo in uptrend) vs il calendario standard. KILL: miglioria < +0.3%/trade.

Date FOMC: annunci delle riunioni PROGRAMMATE (8/anno, ~14:00 ET), calendario
pubblico Fed 2007-2026, hardcoded (le straordinarie 2020 escluse: non
prevedibili ex-ante). Possibile errore di ±1 data isolata: non cambia il t.
"""
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

FOMC = """2007-01-31 2007-03-21 2007-05-09 2007-06-28 2007-08-07 2007-09-18 2007-10-31 2007-12-11
2008-01-30 2008-03-18 2008-04-30 2008-06-25 2008-08-05 2008-09-16 2008-10-29 2008-12-16
2009-01-28 2009-03-18 2009-04-29 2009-06-24 2009-08-12 2009-09-23 2009-11-04 2009-12-16
2010-01-27 2010-03-16 2010-04-28 2010-06-23 2010-08-10 2010-09-21 2010-11-03 2010-12-14
2011-01-26 2011-03-15 2011-04-27 2011-06-22 2011-08-09 2011-09-21 2011-11-02 2011-12-13
2012-01-25 2012-03-13 2012-04-25 2012-06-20 2012-08-01 2012-09-13 2012-10-24 2012-12-12
2013-01-30 2013-03-20 2013-05-01 2013-06-19 2013-07-31 2013-09-18 2013-10-30 2013-12-18
2014-01-29 2014-03-19 2014-04-30 2014-06-18 2014-07-30 2014-09-17 2014-10-29 2014-12-17
2015-01-28 2015-03-18 2015-04-29 2015-06-17 2015-07-29 2015-09-17 2015-10-28 2015-12-16
2016-01-27 2016-03-16 2016-04-27 2016-06-15 2016-07-27 2016-09-21 2016-11-02 2016-12-14
2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17""".split()

ATM, CSLOPE = 0.77, 0.16


def bs_call(S, K, T, sig):
    if T <= 0 or sig <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * np.sqrt(T))
    return S * norm.cdf(d1) - K * norm.cdf(d1 - sig * np.sqrt(T))


def tstat(r):
    r = np.array(r)
    return r.mean() / (r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else float("nan")


def callspread_trades(df, entries, H=21, spread=1.5):
    """Call spread ATM/+1σ (edge #3) aperta agli indici `entries` (uptrend già filtrato)."""
    S, V = df["spx"].values, df["vix"].values
    idx = df.index
    rets = []
    last_exit = -1
    for i in entries:
        if i <= last_exit or i + H >= len(df):
            continue
        s0, vix0 = S[i], V[i] / 100.0
        T0 = max((idx[i + H] - idx[i]).days, 1) / 365.0
        K1, K2 = s0, s0 * (1 + vix0 * np.sqrt(T0))
        iv1 = vix0 * ATM
        n2 = (K2 / s0 - 1) / (vix0 * np.sqrt(T0))
        iv2 = vix0 * max(ATM - CSLOPE * n2, 0.03)
        debit = bs_call(s0, K1, T0, iv1) - bs_call(s0, K2, T0, iv2) + spread
        if debit <= 0:
            continue
        pay = min(max(S[i + H] - K1, 0), K2 - K1)
        rets.append((pay - debit) / debit)
        last_exit = i + H
    return np.array(rets)


def main():
    spx = pd.read_csv("data/research/us500_daily.csv")
    spx["ts"] = pd.to_datetime(spx["ts"], utc=True).dt.tz_localize(None).dt.normalize()
    spx = spx.set_index("ts")["close"].rename("spx")
    vix = pd.read_csv("data/research/vix_daily.csv")
    vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None).dt.normalize()
    vix = vix.set_index("ts")["close"].rename("vix")
    df = pd.concat([spx, vix], axis=1).dropna()
    df["sma200"] = df["spx"].rolling(200).mean()
    df["ret1"] = df["spx"].pct_change()

    fomc = pd.to_datetime(FOMC)
    pos = df.index.get_indexer(fomc, method=None)
    fomc_i = [p for p in pos if p > 0]          # solo date presenti nei dati
    print(f"PASSO 1 — effetto grezzo close(T−1)→close(T), {len(fomc_i)} annunci FOMC nei dati")
    is_f = np.zeros(len(df), bool)
    for p in fomc_i:
        is_f[p] = True
    for label, lo, hi in [("full 2007-2026", "2007", "2027"),
                          ("pre-2015 (epoca Lucca-Moench)", "2007", "2015"),
                          ("POST-2015 (il kill)", "2015", "2027")]:
        m = (df.index >= lo) & (df.index < hi)
        rf = df["ret1"].values[m & is_f]
        rn = df["ret1"].values[m & ~is_f & ~np.isnan(df["ret1"].values)]
        print(f"  {label:32s} FOMC: N={len(rf):3d} media {np.nanmean(rf)*100:+.3f}% "
              f"WR {np.nanmean(rf>0)*100:.0f}% t={tstat(rf[~np.isnan(rf)]):+.2f}   "
              f"| altri giorni: media {np.nanmean(rn)*100:+.3f}%")

    m15 = (df.index >= "2015") & is_f
    post = df["ret1"].values[m15]
    post = post[~np.isnan(post)]
    if post.mean() <= 0:
        print("\n❌ KILL: effetto post-2015 ≤ 0 → C9 morto, niente passo 2 (come da spec).")
        return 0
    print(f"\n✅ effetto post-2015 vivo ({post.mean()*100:+.3f}%/evento) → PASSO 2")

    # PASSO 2: call spread aperta a T−1 FOMC (uptrend) vs calendario (uptrend)
    up = (df["spx"] > df["sma200"]).values
    fomc_entries = [p - 1 for p in fomc_i if p >= 1 and up[p - 1]]
    cal_entries = [i for i in range(200, len(df)) if up[i]]     # il ciclo li dirada (last_exit)
    r_fomc = callspread_trades(df, fomc_entries)
    r_cal = callspread_trades(df, cal_entries)
    print(f"  call spread ANCORATA a T−1 FOMC : N={len(r_fomc):3d} (~{len(r_fomc)/19:.0f}/anno)  "
          f"ret/trade {r_fomc.mean()*100:+.1f}% del premio  WR {np.mean(r_fomc>0)*100:.0f}%  t={tstat(r_fomc):+.2f}")
    print(f"  call spread CALENDARIO (edge #3): N={len(r_cal):3d} (~{len(r_cal)/19:.0f}/anno)  "
          f"ret/trade {r_cal.mean()*100:+.1f}% del premio  WR {np.mean(r_cal>0)*100:.0f}%  t={tstat(r_cal):+.2f}")
    diff = (r_fomc.mean() - r_cal.mean()) * 100
    print(f"  → differenza {diff:+.1f}%/trade (kill pre-registrato: < +0.3% per-trade "
          f"NON vale la complicazione; e occhio alla frequenza: {len(r_fomc)} vs {len(r_cal)} trade)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
