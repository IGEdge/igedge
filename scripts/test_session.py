#!/usr/bin/env python3
"""
Collaudo DRY-RUN della sessione persistente: prova che NON si ri-logga se i token
salvati sono validi (anti-lockout), e che si ri-logga UNA sola volta se scaduti.
Nessuna connessione reale. Esegui: python scripts/test_session.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.options.session import PersistentIGSession

SF = "data/ig_session_test.json"


class MockIG:
    """IGClient simulato: conta i login e simula la validità server dei token."""
    def __init__(self, server_expired=False):
        self.base_url = "https://api.ig.com/gateway/deal"
        self.cst = None
        self.security_token = None
        self.account_id = "TVYYM"
        self.lightstreamer_endpoint = None
        self.login_count = 0
        self.server_expired = server_expired

    def login(self):
        self.login_count += 1
        self.cst = f"CST{self.login_count}"
        self.security_token = f"X{self.login_count}"
        return True

    def apply_tokens(self, cst, x, acc=None, ls=None):
        self.cst, self.security_token = cst, x
        if acc:
            self.account_id = acc

    def is_session_valid(self):
        if not (self.cst and self.security_token):
            return False
        return not self.server_expired


def main():
    if os.path.exists(SF):
        os.remove(SF)

    print("1 — primo avvio (nessun file): deve fare UN login")
    c1 = MockIG()
    s1 = PersistentIGSession(c1, SF)
    assert s1.ensure() and c1.login_count == 1, "atteso 1 login"
    print(f"   login_count={c1.login_count}  token salvati ✓")

    print("\n2 — nuovo processo, token VALIDI: deve RIUSARE (0 login)")
    c2 = MockIG(server_expired=False)
    s2 = PersistentIGSession(c2, SF)
    assert s2.ensure() and c2.login_count == 0, f"NON doveva loggare, count={c2.login_count}"
    print(f"   login_count={c2.login_count}  → sessione riusata ✓ (niente login = niente lockout)")

    print("\n3 — token SCADUTI sul server: deve ri-loggare UNA volta")
    c3 = MockIG(server_expired=True)
    s3 = PersistentIGSession(c3, SF)
    assert s3.ensure() and c3.login_count == 1, f"atteso 1 relogin, count={c3.login_count}"
    print(f"   login_count={c3.login_count}  → un solo relogin ✓")

    print("\n4 — molti 'run' di fila con token validi: SEMPRE 0 login")
    total = 0
    for _ in range(5):
        c = MockIG(server_expired=False)
        PersistentIGSession(c, SF).ensure()
        total += c.login_count
    assert total == 0, f"5 run non dovevano loggare, totale={total}"
    print(f"   5 run → login totali={total}  ✓ (a regime NON si incappa nel lockout)")

    os.remove(SF)
    print("\n✅ sessione persistente OK: login una volta, riuso, relogin solo se scaduta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
