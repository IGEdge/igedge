#!/usr/bin/env python3
"""
Test policy arm per-strategia (nessuna rete). Esegui:
  python scripts/test_arming_policy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.options.arming import (is_strategy_armed, parse_strategy_list,
                                resolve_armed_allowlist, unknown_in)


def main() -> int:
    ok = True

    s = parse_strategy_list("putspread, callspread")
    if s != {"putspread", "callspread"}:
        print(f"FAIL parse: {s}"); ok = False
    else:
        print("OK  parse csv")

    if unknown_in("putspread,foo") != {"foo"}:
        print("FAIL unknown"); ok = False
    else:
        print("OK  unknown filtrati")

    al = resolve_armed_allowlist(None, env={"OPTIONS_ARMED_STRATEGIES": "putspread"})
    if al != {"putspread"}:
        print(f"FAIL env allowlist: {al}"); ok = False
    else:
        print("OK  allowlist da env")

    al2 = resolve_armed_allowlist("callspread",
                                  env={"OPTIONS_ARMED_STRATEGIES": "putspread"})
    if al2 != {"callspread"}:
        print(f"FAIL CLI vince su env: {al2}"); ok = False
    else:
        print("OK  CLI vince su env")

    if is_strategy_armed("putspread", gate_open=False, allowlist={"putspread"}):
        print("FAIL gate chiuso non deve armare"); ok = False
    else:
        print("OK  gate chiuso → no arm")

    if not is_strategy_armed("putspread", gate_open=True, allowlist={"putspread"}):
        print("FAIL put dovrebbe essere armata"); ok = False
    else:
        print("OK  put in allowlist + gate → arm")

    if is_strategy_armed("callspread", gate_open=True, allowlist={"putspread"}):
        print("FAIL call NON in allowlist non deve armare"); ok = False
    else:
        print("OK  call fuori allowlist → plan-only")

    if is_strategy_armed("putspread", gate_open=True, allowlist=set()):
        print("FAIL allowlist vuota non deve armare"); ok = False
    else:
        print("OK  allowlist vuota → plan-only")

    if ok:
        print("\nPolicy arming OK (modulare, no hardcode put).")
        return 0
    print("\nQUALCHE CHECK FALLITO.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
