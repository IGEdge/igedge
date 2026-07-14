#!/usr/bin/env python3
"""
Ciclo operativo degli edge OPZIONI a 2 gambe. DEFAULT = plan-only (nessun ordine).

  EDGE #2: python scripts/run_spread.py --strat putspread --live
  EDGE #3: python scripts/run_spread.py --strat callspread --live
  entrambi: --strat both
  APRIRE davvero (pilot): aggiungi --arm --i-understand-live-risk

Segnali raccolti qui e passati all'orchestratore:
  - VIX corrente + VIX3M (CBOE delayed ~15min; fallback: ultimo CSV locale)
  - max VIX 10gg (storia CBOE aggiornata al volo, 1 chiamata HTTP non-IG)
  - SMA200 (da data/research/us500_daily.csv — cambia lenta, ok se di qualche
    giorno fa; il confronto è con lo spot LIVE via parità)
Read-only su IG in plan-only (~8-12 chiamate throttlate, sessione riusata).
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import pandas as pd

from src.core.ig_client import IGClient
from src.options.audit_log import AuditLog
from src.options.executor import CondorExecutor
from src.options.session import PersistentIGSession
from src.options.spread_orchestrator import SpreadConfig, SpreadOrchestrator
from src.options.store import CondorStore
from src.options.throttle import ThrottledClient

CBOE_Q = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{sym}.json"
CBOE_H = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"


def cboe_now(sym):
    try:
        import requests
        r = requests.get(CBOE_Q.format(sym=sym), timeout=10,
                         headers={"User-Agent": "Mozilla/5.0"})
        px = float(r.json()["data"]["current_price"])
        return (px, "cboe_delayed") if px > 0 else (None, "bad")
    except Exception as e:
        return None, f"err:{e}"


def cboe_hist_tail(sym, n=15):
    """Ultimi n close dalla storia CBOE (fresca, 1 chiamata)."""
    try:
        import requests
        r = requests.get(CBOE_H.format(sym=sym), timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower() for c in df.columns]
        return df["close"].tail(n).tolist()
    except Exception:
        return None


def gather_signals():
    vix_now, vix_src = cboe_now("VIX")
    v3_now, _ = cboe_now("VIX3M")
    tail = cboe_hist_tail("VIX", 15)
    if vix_now is None and tail:
        vix_now, vix_src = tail[-1], "cboe_hist_close"
    vix10max = None
    if tail:
        recent = tail[-9:] + ([vix_now] if vix_now else [])
        vix10max = max(recent) if recent else None
    if v3_now is None:
        t3 = cboe_hist_tail("VIX3M", 2)
        v3_now = t3[-1] if t3 else None
    ratio = (vix_now / v3_now) if (vix_now and v3_now) else None
    # SMA200 dal daily locale (cambia ~0.05%/giorno: tolleranza qualche giorno)
    sma200, sma_note = None, "us500_daily.csv mancante"
    try:
        spx = pd.read_csv("data/research/us500_daily.csv")
        closes = spx["close"].tail(200)
        sma200 = float(closes.mean())
        last_ts = str(spx["ts"].iloc[-1])[:10]
        sma_note = f"da csv fino al {last_ts}"
    except Exception:
        pass
    return {"vix_now": vix_now, "vix_src": vix_src, "vix10max": vix10max,
            "ts_ratio": ratio, "sma200": sma200, "sma_note": sma_note,
            "vix3m": v3_now}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strat", choices=["putspread", "callspread", "both"],
                    default="both")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--arm", action="store_true",
                    help="APRE davvero (richiede --live e --i-understand-live-risk)")
    ap.add_argument("--i-understand-live-risk", action="store_true")
    ap.add_argument("--capital", type=float, default=1000.0,
                    help="equity del conto opzioni (€): 1 contratto ogni €1000")
    ap.add_argument("--throttle", type=float, default=2.5)
    ap.add_argument("--db", default="data/condors.db")
    ap.add_argument("--vix", type=float, default=None, help="forza il VIX (test)")
    args = ap.parse_args()

    armed = args.arm and args.i_understand_live_risk and args.live
    if args.arm and not armed:
        print("⛔ --arm ignorato: servono --live E --i-understand-live-risk. Plan-only.")
    if not args.live:
        print("(nota: il demo IG non ha le mensili → usa --live, è read-only in plan-only)")

    if args.live:
        key, ident, pwd = (os.getenv("IG_LIVE_API_KEY"), os.getenv("IG_LIVE_IDENTIFIER"),
                           os.getenv("IG_LIVE_PASSWORD"))
        if not (key and ident and pwd):
            print("❌ credenziali LIVE mancanti (.env IG_LIVE_*)"); return 1
        raw = IGClient(key, ident, pwd, "LIVE", os.getenv("IG_LIVE_ACCOUNT_ID") or None)
        sess_file = "data/ig_session_live.json"
    else:
        raw = IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                       os.getenv("IG_PASSWORD"), "DEMO",
                       os.getenv("IG_OPT_ACCOUNT_ID") or os.getenv("IG_ACCOUNT_ID") or None)
        sess_file = "data/ig_session_demo.json"

    audit = AuditLog(dry_run=not armed)
    sess = PersistentIGSession(raw, sess_file, audit=audit)
    if not sess.ensure():
        print("❌ sessione IG non disponibile"); return 1
    client = ThrottledClient(raw, min_interval=args.throttle)
    store = CondorStore(args.db)
    execu = CondorExecutor(client, audit=audit, live=args.live)
    orch = SpreadOrchestrator(client, store, execu, audit=audit,
                              spread_cfg=SpreadConfig(capital_eur=args.capital))

    sig = gather_signals()
    if args.vix is not None:
        sig["vix_now"], sig["vix_src"] = args.vix, "override"
    print(f"SEGNALI  VIX {sig['vix_now']}{'' if sig['vix_now'] is None else f' ({sig['vix_src']})'}"
          f"   max10gg {sig['vix10max'] and round(sig['vix10max'],1)}"
          f"   VIX3M {sig['vix3m'] and round(sig['vix3m'],2)}"
          f"   VIX/VIX3M {sig['ts_ratio'] and round(sig['ts_ratio'],3)}"
          f"   SMA200 {sig['sma200'] and round(sig['sma200'])} ({sig['sma_note']})")
    if sig["vix_now"] is None:
        print("❌ VIX non disponibile"); return 1

    strats = ["putspread", "callspread"] if args.strat == "both" else [args.strat]
    for strat in strats:
        print("\n" + "=" * 62)
        print(f"[{strat.upper()}]  {'🔴 ARMATO' if armed else '🟢 plan-only'}   capitale €{args.capital:,.0f}".replace(",", "."))
        plan = orch.run_spread(strat, armed=armed,
                               vix_now=sig["vix_now"], vix_src=sig["vix_src"],
                               vix10max=sig["vix10max"], ts_ratio=sig["ts_ratio"],
                               sma200=sig["sma200"])
        if not plan.get("ok"):
            print(f"  NIENTE DA FARE: {plan.get('reason')}")
            continue
        s = plan["spread"]
        print(f"  segnale: {plan['signal']}")
        print(f"  scad {plan['expiry']} (DTE {plan['dte']}, {plan['code']})  "
              f"spot {plan['spot']:.0f} ({plan['spot_src']})")
        for leg in s.open_order():
            q = plan["quotes"][leg.role]
            print(f"   {leg.role:15s} {leg.direction:4s} {leg.kind:4s} {leg.strike:.0f}"
                  f"   bid/ask {q['bid']}/{q['offer']}   x{leg.size}")
        lab = ("credito (incassi)" if strat == "putspread" else "guadagno max")
        print(f"  {lab} {plan['reward_pts']}pt   RISCHIO MAX {plan['risk_pts']}pt"
              f"  = ~€{plan['risk_eur']:.0f} totali (size {plan['size']})")
        if armed:
            print(f"  ESITO: opened={plan.get('opened')}  store #{plan.get('store_id')}  "
                  f"stato {s.status}")
        else:
            print("  (plan-only: nessun ordine inviato)")
    print(f"\nchiamate IG usate: {getattr(client, 'calls', '?')}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
