#!/usr/bin/env python3
"""
Session-level edge research on US500 — the "scheletro" the idea doc asks for:
mechanical session H/L levels + the NULL TEST (does a real prior-session extreme
beat a RANDOM level at the same distance?). This measures whether the edge
EXISTS before any strategy is built. Descriptive/statistical, not a bot.

Pre-registered, mechanical definitions (UTC; DST shifts RTH ±1h — noted, a
first-pass caveat):
  ASIA   00:00-07:00   LONDON 07:00-13:00   NY 13:00-20:00

Hypothesis tested (classic liquidity-grab / killzone):
  When session S+1 SWEEPS session S's high (trades above it) then RECLAIMS it
  (comes back below within a window), fade SHORT: stop above the swept extreme,
  target R×risk below. Symmetric for a low sweep -> LONG.
  Pairs: London-fades-Asia, NY-fades-London.

NULL TEST: for each event, replace the real level with one at session_open ±
a distance PERMUTED from the pool of real level-distances (same direction),
and run the identical sweep+reclaim+fade. If real expectancy doesn't sit in
the tail of the null distribution, the "edge" is just volatility, not structure.

Data: 1-minute bars aggregated from the cached Dukascopy ticks (no re-download).

Usage:
  python scripts/session_research_us500.py --from 2022-01-01 --to 2026-07-11
  python scripts/session_research_us500.py --from 2022-06-01 --to 2022-07-01 -R 1.5
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

from src.data.dukascopy_cache import load_1m_cached

SESSIONS = {"ASIA": (0, 7), "LONDON": (7, 13), "NY": (13, 20)}
PAIRS = [("ASIA", "LONDON"), ("LONDON", "NY")]


def evaluate_level(sb: pd.DataFrame, level: float, side: str, R: float,
                   buf: float, reclaim_max_min: int, mode: str = "reversal"):
    """Evaluate one session's 1m bars against `level`, in R multiples.

    side='high': the level sits above the open (a sweep = break above);
    'low': below. Two mutually-exclusive hypotheses on the sweep:
      mode='reversal'     -> price RECLAIMS the level within the window: fade
                             back into the range (short a high sweep / long a
                             low sweep), stop beyond the swept extreme.
      mode='continuation' -> price HOLDS beyond the level (no reclaim): ride the
                             breakout (long a high sweep / short a low sweep),
                             stop back through the level.
    Returns the outcome in R, or None if no valid event of that mode occurred."""
    highs = sb["high"].values
    lows = sb["low"].values
    closes = sb["close"].values
    n = len(sb)

    # 1) sweep bar (first bar trading beyond the level)
    swept = -1
    for i in range(n):
        if (side == "high" and highs[i] >= level) or \
           (side == "low" and lows[i] <= level):
            swept = i
            break
    if swept < 0:
        return None

    # 2) observe the reclaim window: reclaim (came back) or hold (stayed beyond)?
    reclaim = -1
    extreme = level
    end_w = min(n, swept + reclaim_max_min)
    for i in range(swept, end_w):
        if side == "high":
            extreme = max(extreme, highs[i])
            if closes[i] < level:
                reclaim = i
                break
        else:
            extreme = min(extreme, lows[i])
            if closes[i] > level:
                reclaim = i
                break

    # Decide entry/stop/target/direction from mode+side; then simulate once.
    if mode == "reversal":
        if reclaim < 0:
            return None                      # never reclaimed -> not a fade
        entry, start = level, reclaim + 1
        if side == "high":                   # SHORT the fade
            stop = extreme + buf; risk = stop - entry; long_ = False
        else:                                # LONG the fade
            stop = extreme - buf; risk = entry - stop; long_ = True
    else:                                    # continuation: breakout held
        if reclaim >= 0:
            return None                      # reclaimed -> that's a fade event
        start = end_w
        entry = closes[end_w - 1]
        if side == "high":                   # LONG the breakout
            stop = level - buf; risk = entry - stop; long_ = True
        else:                                # SHORT the breakout
            stop = level + buf; risk = stop - entry; long_ = False
    if risk <= 0:
        return None
    target = entry + R * risk if long_ else entry - R * risk

    outcome = None
    for i in range(start, n):
        if long_:
            if lows[i] <= stop:
                outcome = -1.0; break
            if highs[i] >= target:
                outcome = R; break
        else:
            if highs[i] >= stop:
                outcome = -1.0; break
            if lows[i] <= target:
                outcome = R; break
    if outcome is None:                      # time barrier at session end
        outcome = (closes[-1] - entry) / risk if long_ else (entry - closes[-1]) / risk
    return outcome, risk                     # (R multiple, risk in price points)


def build_events(m1: pd.DataFrame):
    """Extract sweep-fade events for each pre-registered session pair.
    Returns list of dicts: {pair, side, level, open, dist, next_bars}."""
    days = m1.index.normalize()
    events = []
    for day, day_bars in m1.groupby(days):
        sess = {}
        for name, (h0, h1) in SESSIONS.items():
            lo = day + pd.Timedelta(hours=h0)
            hi = day + pd.Timedelta(hours=h1)
            b = day_bars[(day_bars.index >= lo) & (day_bars.index < hi)]
            if len(b) >= 10:
                sess[name] = b
        for prior, nxt in PAIRS:
            if prior not in sess or nxt not in sess:
                continue
            pb, nb = sess[prior], sess[nxt]
            p_high, p_low = pb["high"].max(), pb["low"].min()
            n_open = nb["open"].iloc[0]
            # Regime tag (no lookahead): directionality of the PRIOR session.
            # body/range high -> prior session TRENDED (its extreme is a real
            # breakout, fading is dangerous); low -> it RANGED (extreme is a
            # liquidity wick, the classic fade setup). Doc's #1 filter.
            p_rng = p_high - p_low
            body = abs(pb["close"].iloc[-1] - pb["open"].iloc[0])
            reg = "TREND" if (p_rng > 0 and body / p_rng >= 0.5) else "RANGE"
            # high sweep only meaningful if next opens BELOW the prior high
            if n_open < p_high:
                events.append({"pair": f"{nxt}<-{prior}", "side": "high",
                               "level": p_high, "open": n_open, "reg": reg,
                               "dist": p_high - n_open, "bars": nb})
            if n_open > p_low:
                events.append({"pair": f"{nxt}<-{prior}", "side": "low",
                               "level": p_low, "open": n_open, "reg": reg,
                               "dist": n_open - p_low, "bars": nb})
    return events


def run_real(events, R, buf, reclaim_max_min, mode="reversal", cost_pts=0.0):
    rows = []
    for e in events:
        res = evaluate_level(e["bars"], e["level"], e["side"], R, buf,
                             reclaim_max_min, mode)
        if res is None:
            continue
        gross, risk = res
        cost_r = cost_pts / risk if risk > 0 else 0.0
        rows.append({"pair": e["pair"], "side": e["side"], "R": gross,
                     "net": gross - cost_r, "risk": risk,
                     "year": e["bars"].index[0].year})
    return pd.DataFrame(rows)


def run_null(events, R, buf, reclaim_max_min, n_perm, mode="reversal", seed=0):
    """Permute level-distances across events (same direction), re-evaluate.
    Returns array of null mean gross-R expectancies (structural test)."""
    rng = np.random.default_rng(seed)
    dists = np.array([e["dist"] for e in events])
    out = []
    for _ in range(n_perm):
        perm = rng.permutation(dists)
        rs = []
        for e, d in zip(events, perm):
            level = e["open"] + d if e["side"] == "high" else e["open"] - d
            res = evaluate_level(e["bars"], level, e["side"], R, buf,
                                 reclaim_max_min, mode)
            if res is not None:
                rs.append(res[0])
        if rs:
            out.append(float(np.mean(rs)))
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", required=True)
    ap.add_argument("--to", dest="dto", required=True)
    ap.add_argument("-R", type=float, default=1.5, help="reward:risk of the fade")
    ap.add_argument("--buf-bps", type=float, default=2.0,
                    help="stop buffer beyond swept extreme, bps of price")
    ap.add_argument("--reclaim-min", type=int, default=30,
                    help="max minutes after sweep to reclaim the level")
    ap.add_argument("--perm", type=int, default=500, help="null permutations")
    ap.add_argument("--mode", choices=["reversal", "continuation"],
                    default="reversal", help="fade the sweep vs ride it")
    ap.add_argument("--cost-pts", type=float, default=2.0,
                    help="round-trip cost in index points (spread+slippage)")
    args = ap.parse_args()

    print(f"Loading 1m bars {args.dfrom} → {args.dto} (cache)...")
    m1 = load_1m_cached(args.dfrom, args.dto)
    if len(m1) == 0:
        print("❌ no cached bars in range — is the download done for this window?")
        return 1
    print(f"  {len(m1):,} 1m bars  ({m1.index[0]} → {m1.index[-1]})")

    buf = m1["close"].mean() * args.buf_bps / 10_000.0
    events = build_events(m1)
    print(f"  candidate sweep setups: {len(events)}  (buf={buf:.2f}pt, "
          f"R={args.R}, reclaim≤{args.reclaim_min}m)")

    def analyze(evs, label):
        """Real vs null on an event subset. Returns None if too few events."""
        real = run_real(evs, args.R, buf, args.reclaim_min, args.mode)
        if len(real) < 20:
            print(f"  {label:22s} N={len(real):4d}  (troppo pochi per il nulla)")
            return
        null = run_null(evs, args.R, buf, args.reclaim_min, args.perm, args.mode)
        real_exp = real["R"].mean()
        wr = (real["R"] > 0).mean() * 100
        pct = (null < real_exp).mean() * 100 if len(null) else float("nan")
        z = ((real_exp - null.mean()) / null.std()
             if len(null) and null.std() > 0 else float("nan"))
        verdict = ("EDGE ✓" if pct >= 95 else
                   "debole" if pct >= 80 else "no-edge")
        print(f"  {label:22s} N={len(real):4d}  WR={wr:3.0f}%  "
              f"E[R]={real_exp:+.3f}  null={null.mean():+.3f}  "
              f"batte {pct:4.0f}% random  z={z:+.2f}  → {verdict}")

    print(f"\n=== {args.mode.upper()} INCONDIZIONATO — real vs nulla ===")
    analyze(events, "ALL")

    print("\n=== CONDIZIONATO PER REGIME (giorno trend vs range) ===")
    for reg in ("RANGE", "TREND"):
        analyze([e for e in events if e["reg"] == reg], f"reg={reg}")

    print("\n=== CONDIZIONATO PER COPPIA DI SESSIONI ===")
    for pair in sorted({e["pair"] for e in events}):
        analyze([e for e in events if e["pair"] == pair], pair)

    print("\n=== REGIME × COPPIA ===")
    for pair in sorted({e["pair"] for e in events}):
        for reg in ("RANGE", "TREND"):
            analyze([e for e in events if e["pair"] == pair and e["reg"] == reg],
                    f"{pair} {reg}")

    # --- Tradeability: netto costi reali + stabilità anno per anno ---
    rr = run_real(events, args.R, buf, args.reclaim_min, args.mode, args.cost_pts)
    if len(rr):
        avg_risk = rr["risk"].mean()
        print(f"\n=== NETTO COSTI ({args.cost_pts}pt round-trip) + STABILITÀ ANNUALE ===")
        print(f"  risk medio {avg_risk:.1f}pt → costo ≈ {args.cost_pts / avg_risk:.2f}R/trade")
        print(f"  E[R]  gross {rr['R'].mean():+.3f}  →  NET {rr['net'].mean():+.3f}  "
              f"(N={len(rr)}, WR net {(rr['net'] > 0).mean() * 100:.0f}%)")
        for y, sub in rr.groupby("year"):
            print(f"   {y}: N={len(sub):4d}  gross {sub['R'].mean():+.3f}  "
                  f"net {sub['net'].mean():+.3f}  sum_net {sub['net'].sum():+6.1f}R")

    print("\n  Il test del nulla (gross) dice se è STRUTTURA o rumore; il blocco "
          "\n  NETTO COSTI dice se è comunque TRADEABILE. Servono entrambi: batte "
          "\n  il nulla E resta positivo netto costi E stabile ogni anno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
