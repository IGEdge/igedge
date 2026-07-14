#!/usr/bin/env python3
"""
Collaudo DRY-RUN dell'orchestratore: mock con catena opzioni + quote BS.
Valida gate segnale (VIX), risoluzione catena, credito NETTO reale, sizing, e il
plan-only (nessun ordine). Poi prova il path ARMATO col mock (apre nel mock).

Esegui: python scripts/test_orchestrator.py
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scipy.stats import norm

from src.options.audit_log import AuditLog
from src.options.executor import CondorExecutor
from src.options.orchestrator import Orchestrator, OrchConfig
from src.options.store import CondorStore

UND = "IX.D.SPTRD.IFE.IP"
SPOT = 7565.0
IV = 0.15
MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
# scadenza STANDARD (formato MON-YY = 3° venerdì) del mese PROSSIMO
_n = datetime.now(timezone.utc)
_y, _m = (_n.year + 1, 1) if _n.month == 12 else (_n.year, _n.month + 1)
EXP = f"{MON[_m-1]}-{_y % 100:02d}"          # es. "AUG-26"
CODE = "OTCSPX1"                              # codice epic che mappa a EXP (come sul reale)
from src.options.monitor import parse_expiry as _pe
T = max((_pe(EXP) - _n).days, 1) / 365.0


def bs(S, K, T, sig, kind):
    d1 = (math.log(S / K) + 0.5 * sig ** 2 * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if kind == "PUT":
        return K * norm.cdf(-d2) - S * norm.cdf(-d1)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


class MockIG:
    def __init__(self):
        self.strikes = list(range(6500, 8601, 50))
        self._deal_role = {}; self._c = 0; self._positions = []

    def get_market(self, epic):
        # solo il codice CODE (=OTCSPX1) esiste, e mappa alla scadenza standard EXP
        import re
        m = re.search(r"OP\.D\.(\w+)\.(\d+)([CP])\.IP$", epic)
        if not m:
            return None
        code, strike, cp = m.group(1), float(m.group(2)), m.group(3)
        if code != CODE:
            return None                          # altri codici → non esistono (404)
        kind = "PUT" if cp == "P" else "CALL"
        mid = max(bs(SPOT, strike, T, IV, kind), 0.2)
        return {"snapshot": {"marketStatus": "TRADEABLE",
                             "bid": round(mid - 0.9, 2), "offer": round(mid + 0.9, 2)},
                "instrument": {"expiry": EXP, "name": f"US 500 {int(strike)} {kind} ($1)"}}

    # per il path armato (executor)
    def open_position(self, epic, direction, size, **kw):
        did = f"D{self._c}"; self._c += 1
        self._positions.append({"epic": epic, "dealId": did})
        return {"dealStatus": "ACCEPTED", "dealId": did, "level": 100.0}

    def close_position(self, deal_id, direction, size, **kw):
        return {"dealStatus": "ACCEPTED", "dealId": deal_id + "c", "level": 100.0}

    def get_positions(self):
        return [{"position": {"dealId": p["dealId"]}, "market": {"epic": p["epic"]}}
                for p in self._positions]


def show(plan):
    if not plan.get("ok"):
        print(f"  → SKIP/NO: {plan.get('reason')}  (action={plan.get('action')})")
        return
    c = plan["condor"]
    print(f"  spot {plan['spot']}  VIX {plan['vix']} ({plan['vix_src']})  "
          f"scad {plan['expiry']} DTE {plan['dte']}  σ≈{plan['sigma_pts']}pt")
    print(f"  strike: {c.describe()}")
    print(f"  credito reale {plan['credit_pts']}pt  max perdita {plan['maxloss_pts']}pt  "
          f"size {plan['size']}  rischio {plan['risk_ccy']} ({plan['risk_pct']:.0f}%)")
    if plan.get("warn"):
        print(f"  ⚠️ {plan['warn']}")
    print(f"  action: {plan.get('action')}")


def main():
    db = "data/condors_orch_test.db"
    if os.path.exists(db):
        os.remove(db)
    store = CondorStore(db)
    client = MockIG()
    ex = CondorExecutor(client, audit=AuditLog(dry_run=True), live=False, retry_delay=0.0)
    orch = Orchestrator(client, store, ex, audit=AuditLog(dry_run=True),
                        config=OrchConfig(capital=1000.0, dte_min=5, dte_max=70))

    print("=" * 66); print("A — IV AUTONOMA dalla catena (no override): PLAN-ONLY")
    p = orch.run_once(armed=False); show(p)      # niente override → ricava l'IV da solo
    assert p["ok"] and "PLAN_ONLY" in p["action"], "doveva pianificare"
    assert str(p["vix_src"]).startswith("atm_iv"), f"IV doveva venire dalla catena, ho {p['vix_src']}"
    assert 13 < p["vix"] < 17, f"IV ricavata ~15 attesa, ho {p['vix']}"
    assert len(store.get_open()) == 0, "plan-only NON deve aprire"

    print("\n" + "=" * 66); print("B — VIX 12 (fuori banda): skip")
    p = orch.run_once(armed=False, vix_override=12.0); show(p)
    assert not p["ok"] and p.get("action") == "skip"

    print("\n" + "=" * 66); print("C — VIX 32 (fuori banda alto): skip")
    p = orch.run_once(armed=False, vix_override=32.0); show(p)
    assert not p["ok"] and p.get("action") == "skip"

    print("\n" + "=" * 66); print("D — ARMATO (mock, IV autonoma): apre davvero e salva")
    p = orch.run_once(armed=True); show(p)
    assert p.get("opened") is True, "doveva aprire nel mock"
    assert len(store.get_open()) == 1, "il condor deve essere nello store"
    print(f"  → condor #{p['store_id']} salvato, stato {p['condor'].status}")

    print("\n" + "=" * 66); print("E — secondo giro: max posizioni raggiunto → skip")
    p = orch.run_once(armed=False, vix_override=15.0); show(p)
    assert not p["ok"] and p.get("action") == "skip"

    store.close(); os.remove(db)
    print("\n✅ orchestratore OK: gate segnale, catena, credito reale, sizing, "
          "plan-only sicuro, armato funzionante, gate max-posizioni.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
