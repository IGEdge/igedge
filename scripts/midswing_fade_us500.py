#!/usr/bin/env python3
"""
MIDSWING-FADE — Test 1 (placebo / falsification gate) on US500.

Hypothesis (to KILL, not confirm): after a defined down-impulse (leg A), price
bounces; when the bounce reaches ~50% of A, a SHORT there has positive expectancy
(target ≈ 50% of the bounce). This is the project's first NON-long-biased idea, so
it sidesteps the intraday-long headwind that killed B/C/D.

Binding method (docs/EDGES.md MIDSWING-FADE §1-4): the entry is CONDITIONAL on the
level being TOUCHED — at the touch, a bounce about to die and one that runs to 78%
are indistinguishable. So Test 1 asks: does the MFE/MAE distribution after the real
50% touch differ from PLACEBO touches at random levels r∈U(0.30,0.70) on the SAME
leg A? If not distinguishable (KS + bootstrap mean-diff, α=0.01) → NOISE, stop.

Causal, no look-ahead:
  - ATR(14) on 5m bars; ATR-ZigZag pivots CONFIRMED only after a k_swing×ATR
    reversal — the confirmation bar (not the extreme) is when we "know" leg A.
  - Down-impulse A = pivotHigh H0 → pivotLow L0, valid if A ≥ a_min×ATR.
  - Event = FIRST touch of level L0 + r×A at/after confirmation (only if not
    already retraced past r at confirmation — else uncatchable, skipped).
  - MFE/MAE measured over the next W bars, normalised to ATR (short convention).

Data: us500_1m.pkl (Dukascopy) → 5m RTH bars. PROXY for ES/SPY (a proper ES feed
+ SPY cross-check is a later phase, per the spec). RTH only, no overnight.

Usage:
  python scripts/midswing_fade_us500.py
  python scripts/midswing_fade_us500.py --k-swing 2 --a-min 5 --r-entry 0.5
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
from scipy import stats

from src.data.dukascopy_cache import load_1m_cached

ET = "America/New_York"


def build_5m_rth(m1: pd.DataFrame) -> pd.DataFrame:
    et = m1.tz_convert(ET)
    mod = et.index.hour * 60 + et.index.minute
    rth = et[(mod >= 9 * 60 + 30) & (mod < 16 * 60)]
    b = rth.resample("5min").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna()
    b["date"] = b.index.normalize()
    return b


def atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean().bfill().values


def find_pivots(high, low, atr_arr, k):
    """Causal ATR-ZigZag. Returns alternating pivots as (idx, price, kind,
    conf_idx): the extreme is at idx, but it is only CONFIRMED at conf_idx when
    price reverses by k×ATR. No look-ahead: conf_idx >= idx always."""
    n = len(high)
    piv = []
    trend = +1                      # +1: seeking a high; -1: seeking a low
    ext_p, ext_i = high[0], 0
    for i in range(1, n):
        thr = k * atr_arr[i]
        if not np.isfinite(thr) or thr <= 0:
            continue
        if trend == +1:
            if high[i] > ext_p:
                ext_p, ext_i = high[i], i
            elif ext_p - low[i] >= thr:
                piv.append((ext_i, ext_p, "H", i))
                trend = -1; ext_p, ext_i = low[i], i
        else:
            if low[i] < ext_p:
                ext_p, ext_i = low[i], i
            elif high[i] - ext_p >= thr:
                piv.append((ext_i, ext_p, "L", i))
                trend = +1; ext_p, ext_i = high[i], i
    return piv


def build_events(b, atr_arr, piv, k, a_min, r_entry, W, n_placebo, rng, same_day=True):
    """For each confirmed down-impulse (H0→L0), build the REAL r_entry event and
    n_placebo random-level events; measure short-side MFE/MAE over next W bars.
    Returns (real_rows, placebo_rows) as lists of dicts."""
    high, low, close = b["high"].values, b["low"].values, b["close"].values
    dates = b["date"].values
    n = len(b)
    real, plac = [], []

    def measure(entry_price, e_idx, a):
        """MFE/MAE (short) over (e_idx, e_idx+W], normalised to ATR at entry."""
        j0, j1 = e_idx + 1, min(n, e_idx + 1 + W)
        if j1 <= j0:
            return None
        # keep it intraday: stop the window at end of the entry day
        if same_day:
            d = dates[e_idx]
            k1 = j0
            while k1 < j1 and dates[k1] == d:
                k1 += 1
            j1 = k1
            if j1 <= j0:
                return None
        seg_hi = high[j0:j1].max()
        seg_lo = low[j0:j1].min()
        a_atr = atr_arr[e_idx]
        if not np.isfinite(a_atr) or a_atr <= 0:
            return None
        mfe = (entry_price - seg_lo) / a_atr    # favourable for a short (down)
        mae = (seg_hi - entry_price) / a_atr    # adverse for a short (up)
        return mfe, mae

    def first_touch(level, start_i, day):
        """First bar >= start_i (same day) whose HIGH reaches up to `level`."""
        for j in range(start_i, n):
            if same_day and dates[j] != day:
                return -1
            if high[j] >= level:
                return j
        return -1

    for a_i in range(1, len(piv)):
        idxL, priceL, kindL, confL = piv[a_i]
        idxH, priceH, kindH, confH = piv[a_i - 1]
        if kindL != "L" or kindH != "H":
            continue
        A = priceH - priceL
        atr_c = atr_arr[confL]
        if not np.isfinite(atr_c) or atr_c <= 0 or A < a_min * atr_c:
            continue
        day = dates[confL]
        # retracement already achieved at confirmation:
        r_conf = (close[confL] - priceL) / A

        # REAL event at r_entry (only catchable if not already past it)
        if r_conf < r_entry:
            lvl = priceL + r_entry * A
            e = first_touch(lvl, confL + 1, day)
            if e >= 0:
                m = measure(lvl, e, A)
                if m:
                    real.append({"date": pd.Timestamp(day).date(),
                                 "year": pd.Timestamp(day).year,
                                 "A_atr": A / atr_c, "mfe": m[0], "mae": m[1]})
        # PLACEBO events at random levels on the SAME leg A
        for _ in range(n_placebo):
            r = float(rng.uniform(0.30, 0.70))
            if r_conf >= r:
                continue
            lvl = priceL + r * A
            e = first_touch(lvl, confL + 1, day)
            if e >= 0:
                m = measure(lvl, e, A)
                if m:
                    plac.append({"r": r, "mfe": m[0], "mae": m[1]})
    return real, plac


def _bootstrap_meandiff(a, b, n=5000, rng=None):
    """Two-sided bootstrap p-value for mean(a) - mean(b) == 0."""
    rng = rng or np.random.default_rng(0)
    obs = a.mean() - b.mean()
    pooled = np.concatenate([a, b])
    na = len(a)
    diffs = np.empty(n)
    for i in range(n):
        s = rng.permutation(pooled)
        diffs[i] = s[:na].mean() - s[na:].mean()
    p = (np.abs(diffs) >= abs(obs)).mean()
    return obs, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", default="2022-01-01")
    ap.add_argument("--to", dest="dto", default="2026-07-11")
    ap.add_argument("--k-swing", type=float, default=3.0, help="ATR mult for pivot confirm")
    ap.add_argument("--a-min", type=float, default=5.0, help="min impulse A in ATR")
    ap.add_argument("--r-entry", type=float, default=0.5, help="retracement entry level")
    ap.add_argument("--window", type=int, default=60, help="forward bars for MFE/MAE")
    ap.add_argument("--n-placebo", type=int, default=20)
    ap.add_argument("--alpha", type=float, default=0.01)
    args = ap.parse_args()

    print(f"Loading 1m bars {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    if len(m1) == 0:
        print("❌ no cached bars"); return 1
    b = build_5m_rth(m1)
    atr_arr = atr(b, 14)
    piv = find_pivots(b["high"].values, b["low"].values, atr_arr, args.k_swing)
    rng = np.random.default_rng(0)
    real, plac = build_events(b, atr_arr, piv, args.k_swing, args.a_min,
                              args.r_entry, args.window, args.n_placebo, rng)

    print(f"\nMIDSWING-FADE Test 1 (placebo)  k_swing={args.k_swing} a_min={args.a_min} "
          f"r_entry={args.r_entry}  W={args.window}b  (US500 5m RTH proxy)")
    print(f"  pivot causali: {len(piv)}  |  eventi reali: {len(real)}  |  placebo: {len(plac)}")
    if len(real) < 30:
        print("  ⚠️ troppi pochi eventi reali per un test robusto — allenta a_min/r_entry/k_swing")
        if len(real) == 0:
            return 0
    R = pd.DataFrame(real); P = pd.DataFrame(plac)

    # short-side edge proxy: MFE (down) should EXCEED MAE (up) more than placebo
    for col in ("mfe", "mae"):
        rr, pp = R[col].values, P[col].values
        ks = stats.ks_2samp(rr, pp)
        obs, bp = _bootstrap_meandiff(rr, pp, 5000, rng)
        verdict = "DIVERSO" if (ks.pvalue < args.alpha or bp < args.alpha) else "≈ placebo"
        print(f"\n  [{col.upper()}]  reale μ={rr.mean():+.3f}  placebo μ={pp.mean():+.3f}  "
              f"(ATR)  Δμ={obs:+.3f}")
        print(f"        KS D={ks.statistic:.3f} p={ks.pvalue:.4f}  |  bootstrap p={bp:.4f}  → {verdict}")

    # net directional edge at the touch: E[MFE - MAE] real vs placebo
    r_net = (R["mfe"] - R["mae"]).values
    p_net = (P["mfe"] - P["mae"]).values
    ks = stats.ks_2samp(r_net, p_net)
    obs, bp = _bootstrap_meandiff(r_net, p_net, 5000, rng)
    edge = (ks.pvalue < args.alpha or bp < args.alpha) and obs > 0
    print(f"\n  [MFE−MAE] (edge direzionale short)  reale μ={r_net.mean():+.3f}  "
          f"placebo μ={p_net.mean():+.3f}  Δμ={obs:+.3f}")
    print(f"        KS p={ks.pvalue:.4f}  bootstrap p={bp:.4f}")
    print(f"\n  === VERDETTO TEST 1: "
          f"{'STRUTTURA (procedere a Test 2)' if edge else 'RUMORE (kill — indistinguibile dal placebo)'} ===")
    print(f"  (α={args.alpha}. Criterio spec: se reale ≈ placebo → il pattern è rumore, stop.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
