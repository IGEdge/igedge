#!/usr/bin/env python3
"""
Collaudo DRY-RUN dell'esecuzione condor con la logica RITENTA (non disfa al primo
errore). Prova la regola d'oro — mai uno short nudo — SENZA sprecare spread.

Scenari:
  1. Happy path → OPEN.
  2. Uno SHORT fallisce 2 volte poi apre (RITENTO riesce) → OPEN, niente unwind.
  3. Uno SHORT fallisce SEMPRE → INCOMPLETE_HELD (parziale a rischio definito,
     tenuto + allarme), NON disfatto.
  4. Apertura AMBIGUA (open "fallisce" ma la posizione c'è) → guardia anti-doppione
     la ADOTTA → OPEN, niente doppio ordine.
  5. Come 3 ma con policy "unwind" → ABORTED (flat).
  6. Preflight KO (gamba non tradeable) → niente aperto.

Esegui: python scripts/test_condor_executor.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.options.audit_log import AuditLog
from src.options.condor import build_condor
from src.options.executor import CondorExecutor

EPICS = {
    "long_put_wing":  {"epic": "EP.long_put_wing",  "strike": 7000},
    "short_put":      {"epic": "EP.short_put",      "strike": 7290},
    "short_call":     {"epic": "EP.short_call",     "strike": 7850},
    "long_call_wing": {"epic": "EP.long_call_wing", "strike": 8140},
}


class MockIG:
    """Client IG simulato con fallimenti iniettabili per ruolo."""

    def __init__(self, fail_open=None, fail_open_times=None, ambiguous=None,
                 fail_close=None, untradeable=None, spread=1.8):
        self.fail_open = fail_open              # fallisce SEMPRE l'apertura
        self.fail_open_times = fail_open_times or {}   # role->K: fallisce le prime K
        self.ambiguous = ambiguous              # open ritorna None ma la posizione c'è
        self.fail_close = fail_close
        self.untradeable = untradeable
        self.spread = spread
        self._positions = []                    # [{epic,dealId,level}]
        self._deal_role = {}
        self._attempts = {}
        self._c = 0

    @staticmethod
    def _role(epic):
        return epic.split(".", 1)[1]

    def get_market(self, epic):
        role = self._role(epic)
        status = "EDITS_ONLY" if role == self.untradeable else "TRADEABLE"
        return {"snapshot": {"marketStatus": status, "bid": 100.0,
                             "offer": 100.0 + self.spread}}

    def _record(self, epic, role):
        deal_id = f"D{self._c}"; self._c += 1
        self._positions.append({"epic": epic, "dealId": deal_id, "level": 100.0})
        self._deal_role[deal_id] = role
        return deal_id

    def open_position(self, epic, direction, size, **kw):
        role = self._role(epic)
        self._attempts[role] = self._attempts.get(role, 0) + 1
        if role in self.fail_open_times and self._attempts[role] <= self.fail_open_times[role]:
            return {"dealStatus": "REJECTED", "reason": "REQUOTE"}     # transitorio
        if role == self.ambiguous:
            self._record(epic, role)                                   # posizione creata...
            return None                                                # ...ma conferma persa
        if role == self.fail_open:
            return {"dealStatus": "REJECTED", "reason": "INSUFFICIENT_FUNDS"}
        deal_id = self._record(epic, role)
        return {"dealStatus": "ACCEPTED", "dealId": deal_id, "level": 100.0}

    def close_position(self, deal_id, direction, size, **kw):
        role = self._deal_role.get(deal_id, "?")
        if role == self.fail_close:
            return {"dealStatus": "REJECTED", "reason": "MARKET_CLOSED"}
        self._positions = [p for p in self._positions if p["dealId"] != deal_id]
        return {"dealStatus": "ACCEPTED", "dealId": deal_id + "c", "level": 100.0}

    def get_positions(self):
        return [{"position": {"dealId": p["dealId"], "level": p["level"]},
                 "market": {"epic": p["epic"]}} for p in self._positions]


def make(client, on_fail="hold"):
    ex = CondorExecutor(client, audit=AuditLog(dry_run=True), live=False,
                        open_retries=3, close_retries=2, retry_delay=0.0,
                        on_fail=on_fail)
    condor = build_condor("US500", "31-AUG-26", 7565, 15.0, EPICS,
                          size=1.0, target_credit=20.0, max_loss=200.0)
    return ex, condor


def summarize(name, condor, res):
    legs = "  ".join(f"{l.role}={l.status}" for l in condor.legs)
    open_short = any(l.status == "OPEN" and not l.is_long for l in condor.legs)
    longs_all_open = all(l.status == "OPEN" for l in condor.legs if l.is_long)
    naked = open_short and not longs_all_open
    verdict = ("NO ✓" if not naked else
               "SÌ ma segnalato (serve operatore) ✓" if condor.status in ("INCOMPLETE_HELD", "PARTIAL_ERROR")
               else "⚠️ SÌ e NON gestito (BUG!)")
    print(f"\n[{name}] status={condor.status}  ok={res.get('ok')}  action={res.get('action','-')}")
    print(f"   {legs}")
    print(f"   short nudo residuo? {verdict}")
    return condor.status


def main():
    print("=" * 70); print("1 — happy path")
    ex, c = make(MockIG()); r = ex.open_condor(c); s = summarize("1", c, r)
    assert s == "OPEN" and r["ok"]

    print("\n" + "=" * 70); print("2 — short_call fallisce 2 volte poi apre (RITENTO)")
    ex, c = make(MockIG(fail_open_times={"short_call": 2})); r = ex.open_condor(c); s = summarize("2", c, r)
    assert s == "OPEN" and r["ok"], f"il retry doveva aprirla, ho {s}"

    print("\n" + "=" * 70); print("3 — short_call fallisce SEMPRE → INCOMPLETE_HELD (non disfa)")
    ex, c = make(MockIG(fail_open="short_call")); r = ex.open_condor(c); s = summarize("3", c, r)
    assert s == "INCOMPLETE_HELD", f"atteso INCOMPLETE_HELD, ho {s}"
    assert c.by_role("short_put").status == "OPEN", "lo short_put coperto resta aperto (defined-risk)"

    print("\n" + "=" * 70); print("4 — apertura AMBIGUA su short_call → adottata via get_positions")
    ex, c = make(MockIG(ambiguous="short_call")); r = ex.open_condor(c); s = summarize("4", c, r)
    assert s == "OPEN" and r["ok"], f"doveva adottare la posizione, ho {s}"

    print("\n" + "=" * 70); print("5 — short_call fallisce sempre, policy=unwind → ABORTED (flat)")
    ex, c = make(MockIG(fail_open="short_call"), on_fail="unwind"); r = ex.open_condor(c); s = summarize("5", c, r)
    assert s == "ABORTED", f"atteso ABORTED, ho {s}"
    assert not any(l.status == "OPEN" for l in c.legs), "flat"

    print("\n" + "=" * 70); print("6 — preflight KO (long_call_wing non tradeable)")
    ex, c = make(MockIG(untradeable="long_call_wing")); r = ex.open_condor(c); s = summarize("6", c, r)
    assert s == "ABORTED" and not r["ok"]
    assert all(l.status == "PENDING" for l in c.legs)

    print("\n" + "=" * 70)
    print("✅ TUTTI OK — ritento sicuro, mai short nudo, unwind solo su richiesta.")
    print("   Audit: logs/condor_audit.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
