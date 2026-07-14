#!/usr/bin/env python3
"""
Collaudo DRY-RUN di CondorStore + CondorMonitor: salvataggio, mark-to-market,
giorni a scadenza, reconcile con IG (incluso lo scenario di gamba mancante).
Nessuna connessione reale. Esegui: python scripts/test_condor_monitor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timezone

from src.options.audit_log import AuditLog
from src.options.condor import build_condor
from src.options.monitor import CondorMonitor
from src.options.store import CondorStore

UND = "IX.D.SPTRD.IFE.IP"
EPICS = {
    "long_put_wing":  {"epic": "OP.lpw", "strike": 7000},
    "short_put":      {"epic": "OP.sp",  "strike": 7290},
    "short_call":     {"epic": "OP.sc",  "strike": 7850},
    "long_call_wing": {"epic": "OP.lcw", "strike": 8140},
}
# mid correnti (option decay → il condor è in profitto)
MIDS = {UND: 7565.0, "OP.lpw": 2.0, "OP.sp": 8.0, "OP.sc": 7.0, "OP.lcw": 2.0}


class MockIG:
    def __init__(self, present_deals):
        self.present = set(present_deals)   # dealId ancora "su IG"
        self._epic_of = {"D_lpw": "OP.lpw", "D_sp": "OP.sp",
                         "D_sc": "OP.sc", "D_lcw": "OP.lcw"}

    def get_market(self, epic):
        mid = MIDS.get(epic)
        if mid is None:
            return None
        return {"snapshot": {"marketStatus": "TRADEABLE",
                             "bid": mid - 0.9, "offer": mid + 0.9}}

    def get_positions(self):
        out = []
        for deal, epic in self._epic_of.items():
            if deal in self.present:
                out.append({"position": {"dealId": deal, "level": MIDS[epic]},
                            "market": {"epic": epic}})
        return out


def make_condor():
    # scadenza ~30 giorni nel futuro per un DTE realistico
    from datetime import timedelta
    exp = (datetime.now(timezone.utc) + timedelta(days=30))
    exp_str = f"{exp.day:02d}-{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][exp.month-1]}-{exp.year%100:02d}"
    c = build_condor(UND, exp_str, 7565, 15.0, EPICS, size=1.0,
                     target_credit=20.0, max_loss=200.0)
    # simulo un'apertura riuscita: tutte OPEN con dealId
    deals = {"long_put_wing": "D_lpw", "short_put": "D_sp",
             "short_call": "D_sc", "long_call_wing": "D_lcw"}
    for leg in c.legs:
        leg.status = "OPEN"; leg.deal_id = deals[leg.role]; leg.fill_level = MIDS[leg.epic]
    c.status = "OPEN"; c.opened_ts = datetime.now(timezone.utc).isoformat()
    return c


def main():
    db = "data/condors_test.db"
    if os.path.exists(db):
        os.remove(db)
    store = CondorStore(db)
    cid = store.record(make_condor())
    print(f"salvato condor #{cid} nello store\n")

    # riletto dallo store (prova persistenza)
    assert len(store.get_open()) == 1, "il condor deve risultare aperto"
    print("--- persistenza store: OK (riletto 1 condor aperto) ---")

    print("\n########## RECONCILE OK — tutte e 4 le gambe su IG ##########")
    mon = CondorMonitor(MockIG(present_deals=["D_lpw", "D_sp", "D_sc", "D_lcw"]),
                        store, audit=AuditLog())
    print(mon.report())

    print("\n########## RECONCILE ANOMALIA — manca lo short_call su IG ##########")
    mon2 = CondorMonitor(MockIG(present_deals=["D_lpw", "D_sp", "D_lcw"]),
                         store, audit=AuditLog())
    rep = mon2.report()
    print(rep)
    assert "gambe mancanti su IG=['short_call']" in rep, "deve segnalare la gamba mancante"

    store.close()
    os.remove(db)
    print("\n✅ store + monitor OK (mark-to-market, DTE, reconcile, allarme gamba mancante).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
