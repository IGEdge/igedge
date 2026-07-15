#!/usr/bin/env python3
"""
Ciclo operativo dell'EDGE #2 (short-vol condor). DEFAULT = plan-only: risolve la
catena reale, calcola il condor esatto (strike, credito, rischio) con le quote
vere, e NON apre nulla. `--arm` apre davvero (solo con tua autorizzazione).

Anti rate-limit: client THROTTLATO (intervallo minimo tra chiamate) + catena
risolta con poche search + get_market solo sui 4 leg. Read-only in plan-only.

  python scripts/run_condor.py --live                    # plan-only sul REALE (nessun ordine)
  python scripts/run_condor.py --live --vix 16           # forza il VIX
  python scripts/run_condor.py --live --arm --i-understand-live-risk   # APRE davvero

Senza --live gira sul demo (che però non ha le mensili → catena vuota).
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

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.core.ig_client import IGClient
from src.options.audit_log import AuditLog
from src.options.executor import CondorExecutor
from src.options.orchestrator import Orchestrator, OrchConfig
from src.options.session import PersistentIGSession
from src.options.store import CondorStore
from src.options.throttle import ThrottledClient


def make_client(live):
    if live:
        key, ident, pwd = (os.getenv("IG_LIVE_API_KEY"), os.getenv("IG_LIVE_IDENTIFIER"),
                           os.getenv("IG_LIVE_PASSWORD"))
        if not (key and ident and pwd):
            print("❌ credenziali LIVE mancanti (.env IG_LIVE_*)"); return None
        return IGClient(key, ident, pwd, "LIVE", os.getenv("IG_LIVE_ACCOUNT_ID") or None)
    return IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                    os.getenv("IG_PASSWORD"), "DEMO",
                    os.getenv("IG_OPT_ACCOUNT_ID") or os.getenv("IG_ACCOUNT_ID") or None)


def main():
    print("=" * 70)
    print("⛔ DEPRECATO: l'IRON CONDOR è FALSIFICATO al pricing reale (14 lug 2026)")
    print("   — il lato call IG (a sconto) rende il condor perdente.")
    print("   Strategie operative: scripts/run_spread.py (putspread/callspread).")
    print("   Questo script resta SOLO come storia/debug. NON usarlo per trading.")
    print("=" * 70)
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--arm", action="store_true", help="APRE davvero (richiede --i-understand-live-risk)")
    ap.add_argument("--i-understand-live-risk", action="store_true")
    ap.add_argument("--vix", type=float, default=None, help="forza il VIX (altrimenti ultimo CSV)")
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--dte-min", type=int, default=20, help="giorni min a scadenza")
    ap.add_argument("--dte-max", type=int, default=45, help="giorni max a scadenza")
    ap.add_argument("--vix-min", type=float, default=14.0, help="floor banda VIX (demo: abbassa per vedere il condor)")
    ap.add_argument("--vix-max", type=float, default=30.0, help="cap banda VIX")
    ap.add_argument("--throttle", type=float, default=2.5, help="secondi minimi tra chiamate IG")
    ap.add_argument("--db", default="data/condors.db")
    args = ap.parse_args()

    armed = args.arm and args.i_understand_live_risk and args.live
    if args.arm and not armed:
        print("⛔ --arm ignorato: serve --live E --i-understand-live-risk. Resto in plan-only.")

    raw = make_client(args.live)
    if raw is None:
        return 1
    print(f"Ambiente: {'LIVE (REALE)' if args.live else 'DEMO'} — {raw.base_url}"
          f"   modalità: {'🔴 ARMATO (aprirà!)' if armed else '🟢 plan-only (nessun ordine)'}")
    audit = AuditLog(dry_run=not armed)
    # sessione PERSISTENTE: login una volta, riuso token (anti-lockout)
    sess_file = f"data/ig_session_{'live' if args.live else 'demo'}.json"
    sess = PersistentIGSession(raw, sess_file, audit=audit)
    if not sess.ensure():
        print("❌ sessione IG non disponibile (login/token)"); return 1

    client = ThrottledClient(raw, min_interval=args.throttle)  # anti rate-limit
    store = CondorStore(args.db)
    execu = CondorExecutor(client, audit=audit, live=args.live)
    orch = Orchestrator(client, store, execu, audit=audit,
                        config=OrchConfig(capital=args.capital,
                                          dte_min=args.dte_min, dte_max=args.dte_max,
                                          vix_min=args.vix_min, vix_max=args.vix_max))

    plan = orch.run_once(armed=armed, vix_override=args.vix)
    print("\n" + "=" * 60)
    if not plan.get("ok"):
        print(f"NIENTE DA FARE: {plan.get('reason')}  (action={plan.get('action')})")
    else:
        c = plan["condor"]
        print(f"SPOT {plan['spot']}  VIX {plan['vix']} ({plan['vix_src']})  "
              f"scad {plan['expiry']} DTE {plan['dte']}  σ≈{plan['sigma_pts']}pt")
        print("CONDOR:")
        for l in c.open_order():
            print(f"   {l.role:15s} {l.direction} {l.kind} {l.strike:.0f}  epic={l.epic}")
        print(f"CREDITO reale {plan['credit_pts']}pt  MAX PERDITA {plan['maxloss_pts']}pt  "
              f"size {plan['size']}")
        print(f"→ max profitto ~{plan['credit_pts']*plan['size']:.0f}  "
              f"max perdita ~{plan['risk_ccy']:.0f} ({plan['risk_pct']:.0f}% del capitale)")
        if plan.get("warn"):
            print(f"⚠️ {plan['warn']}")
        if armed:
            print(f"\nESITO APERTURA: opened={plan.get('opened')}  condor #{plan.get('store_id')}  "
                  f"stato {c.status}")
        else:
            print("\n(plan-only: nessun ordine inviato)")
    print(f"\nchiamate IG usate: {getattr(client, 'calls', '?')}")
    # NON fare logout: la sessione resta viva e riusabile (evita login ripetuti)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
