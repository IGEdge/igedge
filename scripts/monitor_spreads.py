#!/usr/bin/env python3
"""
Monitoraggio spread multi-gamba a mercato (read-only). Issue #16.

  python scripts/monitor_spreads.py            # demo (IG_*)
  python scripts/monitor_spreads.py --live     # reale (IG_LIVE_*)

SOLO LETTURA: non apre/chiude. Alias deprecato: monitor_condors.py
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
from src.options.monitor import SpreadMonitor
from src.options.session import PersistentIGSession
from src.options.store import SpreadStore, resolve_spreads_db_path
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
    ap.add_argument("--db", default=None,
                    help="default spreads.db (fallback condors.db)")
    args = ap.parse_args()

    db_path = resolve_spreads_db_path(args.db)
    store = SpreadStore(db_path)
    if not store.get_open():
        print(f"Nessuno spread aperto in {db_path}.")
        store.close(); return 0

    raw = make_client(args.live)
    if raw is None:
        return 1
    print(f"Ambiente: {'LIVE (REALE)' if args.live else 'DEMO'} — {raw.base_url}")
    audit = AuditLog(dry_run=True)  # monitor sempre read-only → dry_run tag ok
    sess_file = f"data/ig_session_{'live' if args.live else 'demo'}.json"
    if not PersistentIGSession(raw, sess_file, audit=audit).ensure():
        print("❌ sessione IG non disponibile"); return 1

    client = ThrottledClient(raw, min_interval=2.5)
    mon = SpreadMonitor(client, store, audit=audit)
    print(mon.report())
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
