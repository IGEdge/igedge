#!/usr/bin/env python3
"""
Monitoraggio dei condor a mercato (read-only). Legge lo store e stampa il report
minuzioso: mark-to-market, giorni a scadenza, distanza dagli short, P&L non
realizzato, reconcile con IG (allarme gambe mancanti / orfani).

  python scripts/monitor_condors.py            # demo (IG_*)
  python scripts/monitor_condors.py --live     # reale (IG_LIVE_*)

SOLO LETTURA: non apre/chiude nulla. ⚠️ Sul live consuma allowance API (poche
chiamate a report; non lanciarlo in loop stretto).
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
from src.options.monitor import CondorMonitor
from src.options.session import PersistentIGSession
from src.options.store import CondorStore
from src.options.throttle import ThrottledClient


def make_client(live: bool):
    if live:
        key, ident, pwd = (os.getenv("IG_LIVE_API_KEY"), os.getenv("IG_LIVE_IDENTIFIER"),
                           os.getenv("IG_LIVE_PASSWORD"))
        if not (key and ident and pwd):
            print("❌ credenziali LIVE mancanti in .env (IG_LIVE_*)"); return None
        return IGClient(key, ident, pwd, "LIVE", os.getenv("IG_LIVE_ACCOUNT_ID") or None)
    return IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                    os.getenv("IG_PASSWORD"), "DEMO",
                    os.getenv("IG_OPT_ACCOUNT_ID") or os.getenv("IG_ACCOUNT_ID") or None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--db", default="data/condors.db")
    args = ap.parse_args()

    store = CondorStore(args.db)
    if not store.get_open():
        print(f"Nessun condor aperto in {args.db}.")
        store.close(); return 0

    raw = make_client(args.live)
    if raw is None:
        return 1
    print(f"Ambiente: {'LIVE (REALE)' if args.live else 'DEMO'} — {raw.base_url}")
    audit = AuditLog(dry_run=not args.live)
    sess_file = f"data/ig_session_{'live' if args.live else 'demo'}.json"
    if not PersistentIGSession(raw, sess_file, audit=audit).ensure():
        print("❌ sessione IG non disponibile"); return 1

    client = ThrottledClient(raw, min_interval=2.5)      # anti rate-limit
    mon = CondorMonitor(client, store, audit=audit)
    print(mon.report())
    # niente logout: sessione riusabile
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
