#!/usr/bin/env python3
"""
SAMPLER dello SKEW IG US500 — il gate #1 dell'EDGE #2 (put-spread far-OTM).

Ogni run campiona lo smile REALE dalle opzioni mensili IG (scadenza standard,
3° venerdì): IV a più strike put/call + VIX (CBOE delayed) → una riga in
data/research/skew_samples.csv. Obiettivo: confermare in 2-4 settimane che i
rapporti IV/VIX usati nel backtest (ATM ~0.77, pendenza put ~0.30) reggono nel
tempo. READ-ONLY: nessun ordine, sessione persistente riusata, chiamate throttlate.

  python scripts/sample_skew_us500.py --live            # un campione (da lanciare 1x/giorno)
  python scripts/sample_skew_us500.py --report          # riepilogo dei campioni raccolti

Gate (docs/EDGE-2-vendi-put-lontane.md §7): se ATM medio va verso 0.9 o la
pendenza put scende molto sotto 0.30, l'edge si assottiglia → rifare i conti.
"""
import argparse
import csv
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.core.ig_client import IGClient
from src.options.audit_log import AuditLog
from src.options.chain_resolver import build_epic, round_strike
from src.options.monitor import parse_expiry, upcoming_standard_expiries
from src.options.orchestrator import Orchestrator, _implied_vol
from src.options.session import PersistentIGSession
from src.options.throttle import ThrottledClient

CSV_PATH = "data/research/skew_samples.csv"
# punti dello smile campionati, in unità di σ (distanza dallo spot)
PUT_SIGMAS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
CALL_SIGMAS = [0.5, 1.0, 1.5, 2.0]


def fetch_vix_cboe():
    """VIX corrente dal CBOE (delayed ~15min). Fallback: ultimo close nel CSV."""
    try:
        import requests
        r = requests.get(
            "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_VIX.json",
            timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        px = float(r.json()["data"]["current_price"])
        if px > 0:
            return px, "cboe_delayed"
    except Exception:
        pass
    try:
        import pandas as pd
        df = pd.read_csv("data/research/vix_daily.csv")
        return float(df["close"].iloc[-1]), f"csv:{df['ts'].iloc[-1]}"
    except Exception:
        return None, "unavailable"


def fit_slope(points):
    """Regressione per l'origine: ratio(nσ) − ratio(0) = slope·nσ → slope.
    points = [(n_sigma, iv_ratio − atm_ratio), ...]"""
    num = sum(n * y for n, y in points)
    den = sum(n * n for n, _ in points)
    return num / den if den > 0 else None


def make_client():
    key, ident, pwd = (os.getenv("IG_LIVE_API_KEY"), os.getenv("IG_LIVE_IDENTIFIER"),
                       os.getenv("IG_LIVE_PASSWORD"))
    if not (key and ident and pwd):
        print("❌ credenziali LIVE mancanti (.env IG_LIVE_*)")
        return None
    return IGClient(key, ident, pwd, "LIVE", os.getenv("IG_LIVE_ACCOUNT_ID") or None)


def sample(throttle=2.5):
    raw = make_client()
    if raw is None:
        return 1
    audit = AuditLog(dry_run=True)
    sess = PersistentIGSession(raw, "data/ig_session_live.json", audit=audit)
    if not sess.ensure():
        print("❌ sessione IG non disponibile")
        return 1
    client = ThrottledClient(raw, min_interval=throttle)
    # riuso gli helper dell'orchestratore (scoperta codice, spot via parità, mid)
    orch = Orchestrator.__new__(Orchestrator)
    orch.client, orch._cache = client, {}

    # scadenza standard più vicina a ~30gg (stessa finestra del put-spread)
    today = datetime.now(timezone.utc).date()
    best = None
    for exp_str, d in upcoming_standard_expiries():
        dte = (d - today).days
        if 7 <= dte <= 60 and (best is None or abs(dte - 30) < abs(best[1] - 30)):
            best = (exp_str, dte)
    if best is None:
        print("❌ nessuna scadenza standard in [7,60] DTE")
        return 1
    expiry, dte = best
    code = orch._discover_code(expiry)
    if not code:
        print(f"❌ codice epic non trovato per {expiry}")
        return 1
    spot, spot_src = orch._spot_from_monthly(code)
    if spot is None:
        print(f"❌ spot non disponibile ({spot_src})")
        return 1

    vix, vix_src = fetch_vix_cboe()
    if vix is None:
        print("❌ VIX non disponibile (CBOE e CSV falliti)")
        return 1

    T = max(dte, 1) / 365.0
    sig_pts = spot * (vix / 100.0) * math.sqrt(T)
    print(f"scad {expiry} (DTE {dte}, {code})  spot {spot:.0f} ({spot_src})  "
          f"VIX {vix:.2f} ({vix_src})  σ≈{sig_pts:.0f}pt")

    def iv_at(n_sigma, kind):
        k = round_strike(spot - n_sigma * sig_pts if kind == "PUT"
                         else spot + n_sigma * sig_pts, 50)
        m = client.get_market(build_epic(code, int(k), kind))
        if not m:
            return k, None, None
        s = m.get("snapshot", {}) or {}
        b, o = s.get("bid"), s.get("offer")
        if b is None or o is None:
            return k, None, None
        mid = (b + o) / 2.0
        return k, mid, _implied_vol(mid, spot, k, T, kind)

    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "expiry": expiry, "dte": dte, "spot": round(spot, 1),
           "vix": round(vix, 2), "vix_src": vix_src}
    # ATM (put; fallback call)
    k_atm, mid_atm, iv_atm = iv_at(0.0, "PUT")
    if iv_atm is None:
        k_atm, mid_atm, iv_atm = iv_at(0.0, "CALL")
    row["iv_atm"] = round(iv_atm, 4) if iv_atm else None
    print(f"  ATM {k_atm:.0f}: IV {iv_atm*100:.1f}%  ratio {iv_atm*100/vix:.2f}"
          if iv_atm else f"  ATM {k_atm:.0f}: n/d")

    put_pts, call_pts = [], []
    seen = {k_atm}
    for n in PUT_SIGMAS:
        k, mid, iv = iv_at(n, "PUT")
        if k in seen:
            continue
        seen.add(k)
        row[f"iv_put_{n}"] = round(iv, 4) if iv else None
        if iv and iv_atm:
            put_pts.append((n, iv / vix * 100 - iv_atm / vix * 100))
        print(f"  PUT  {n:.1f}σ  {k:.0f}: " +
              (f"IV {iv*100:.1f}%  ratio {iv*100/vix:.2f}" if iv else "n/d"))
    for n in CALL_SIGMAS:
        k, mid, iv = iv_at(n, "CALL")
        if k in seen:
            continue
        seen.add(k)
        row[f"iv_call_{n}"] = round(iv, 4) if iv else None
        if iv and iv_atm:
            call_pts.append((n, iv_atm / vix * 100 - iv / vix * 100))
        print(f"  CALL {n:.1f}σ  {k:.0f}: " +
              (f"IV {iv*100:.1f}%  ratio {iv*100/vix:.2f}" if iv else "n/d"))

    atm_ratio = iv_atm / (vix / 100.0) if iv_atm else None
    put_slope = fit_slope(put_pts) if put_pts else None
    call_slope = fit_slope(call_pts) if call_pts else None
    row["atm_ratio"] = round(atm_ratio, 3) if atm_ratio else None
    row["put_slope"] = round(put_slope, 3) if put_slope is not None else None
    row["call_slope"] = round(call_slope, 3) if call_slope is not None else None

    print(f"\n  MODELLO: atm_ratio {row['atm_ratio']}  (backtest: 0.77)"
          f"   put_slope {row['put_slope']}  (backtest: 0.30)"
          f"   call_slope {row['call_slope']}  (backtest: 0.16)")
    print(f"  chiamate IG: {getattr(client, 'calls', '?')}")

    # append CSV (header stabile: unione di tutte le colonne possibili)
    cols = (["ts", "expiry", "dte", "spot", "vix", "vix_src", "iv_atm"]
            + [f"iv_put_{n}" for n in PUT_SIGMAS]
            + [f"iv_call_{n}" for n in CALL_SIGMAS]
            + ["atm_ratio", "put_slope", "call_slope"])
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow({c: row.get(c) for c in cols})
    print(f"  → campione salvato in {CSV_PATH}")
    return 0


def report():
    import pandas as pd
    if not os.path.exists(CSV_PATH):
        print("nessun campione ancora — lancia prima il sampler")
        return 1
    df = pd.read_csv(CSV_PATH)
    print(f"CAMPIONI: {len(df)}   dal {df['ts'].iloc[0][:10]} al {df['ts'].iloc[-1][:10]}"
          f"   VIX range [{df['vix'].min():.1f}, {df['vix'].max():.1f}]")
    for col, ref in [("atm_ratio", 0.77), ("put_slope", 0.30), ("call_slope", 0.16)]:
        s = df[col].dropna()
        if len(s):
            print(f"  {col:11s}: media {s.mean():.3f}  min {s.min():.3f}  max {s.max():.3f}"
                  f"   (backtest: {ref})  {'✅ regge' if abs(s.mean()-ref) < 0.08 else '⚠️ DEVIA — rifare i conti'}")
    print("\nGATE (docs/EDGE-2-vendi-put-lontane.md §7): servono ~10-20 campioni su "
          "più livelli di VIX prima di giudicare.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="campiona dal conto reale (read-only)")
    ap.add_argument("--report", action="store_true", help="riepilogo campioni raccolti")
    ap.add_argument("--throttle", type=float, default=2.5)
    args = ap.parse_args()
    if args.report:
        return report()
    if not args.live:
        print("il sampler legge le mensili del conto REALE (read-only): usa --live")
        return 1
    return sample(throttle=args.throttle)


if __name__ == "__main__":
    raise SystemExit(main())
