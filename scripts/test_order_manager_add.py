#!/usr/bin/env python3
"""
Test unitario issue #3 — scale-in ADD (nessuna connessione IG, mercato irrilevante).

Verifica:
  1) ENTER apre la prima unità
  2) secondo ENTER (senza allow_stack) → already_open (anti-doppione)
  3) ADD con allow_stack=True apre una NUOVA deal distinta
  4) nello store restano 2 posizioni OPEN

Esegui:  python scripts/test_order_manager_add.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.core.order_manager import OrderManager
from src.core.position_store import PositionStore

EPIC = "IX.D.SPTRD.IFE.IP"
STRAT = "dip_buy"


class MockIG:
    """Simula fill ACCEPTED; nessuna rete."""

    def __init__(self):
        self.n = 0
        self.opens = []

    def open_position(self, epic, direction, size, stop_distance=None,
                      limit_distance=None):
        self.n += 1
        deal_id = f"DEAL-{self.n}"
        self.opens.append({"deal_id": deal_id, "epic": epic,
                           "direction": direction, "size": size})
        return {"dealStatus": "ACCEPTED", "dealId": deal_id, "level": 6000.0}

    def close_position(self, deal_id, direction, size):
        return {"dealStatus": "ACCEPTED", "dealId": deal_id, "level": 6010.0}


def main() -> int:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    store = PositionStore(db.name)
    ig = MockIG()
    om = OrderManager(ig, store, max_retries=0)

    ok = True

    r1 = om.open(EPIC, "BUY", 1.0, STRAT, allow_stack=False)
    if not (r1.get("ok") and r1.get("deal_id") == "DEAL-1"):
        print(f"FAIL ENTER: {r1}")
        ok = False
    else:
        print("OK  ENTER → DEAL-1 aperta")

    r2 = om.open(EPIC, "BUY", 1.0, STRAT, allow_stack=False)
    if r2.get("ok") or r2.get("reason") != "already_open":
        print(f"FAIL anti-doppione ENTER: {r2}")
        ok = False
    else:
        print("OK  secondo ENTER → already_open (come previsto)")

    r3 = om.open(EPIC, "BUY", 1.0, STRAT, allow_stack=True)
    if not (r3.get("ok") and r3.get("deal_id") == "DEAL-2"):
        print(f"FAIL ADD allow_stack: {r3}")
        ok = False
    else:
        print("OK  ADD allow_stack → DEAL-2 aperta (scale-in)")

    open_pos = store.get_open(STRAT)
    if len(open_pos) != 2:
        print(f"FAIL store: attese 2 OPEN, trovate {len(open_pos)}")
        ok = False
    else:
        ids = {p["deal_id"] for p in open_pos}
        print(f"OK  store ha 2 OPEN: {sorted(ids)}")

    store.close()
    try:
        os.unlink(db.name)
    except OSError:
        pass

    if ok:
        print("\nTutti i check issue #3 PASSATI (mock, mercato chiuso ok).")
        return 0
    print("\nQUALCHE CHECK FALLITO.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
