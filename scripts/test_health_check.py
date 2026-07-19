#!/usr/bin/env python3
"""
Test unitario issue #9 — HealthCheck solo telemetria (nessuna rete IG).

Verifica:
  1) probe OK → stato up
  2) probe fail sotto soglia → warning, niente CRITICAL latch
  3) fail oltre max_down_sec → allarme latched (una volta)
  4) recovery → di nuovo up, latch resettato
  5) nessun side-effect di trading (modulo non chiude nulla)

Esegui:  python scripts/test_health_check.py
"""
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.core.health_check import HealthCheck

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s %(message)s")


def main() -> int:
    state = {"up": True}
    hc = HealthCheck(lambda: state["up"], interval_sec=0.5, max_down_sec=1.0)
    ok = True

    if not hc.tick(force=True) or not hc.ok:
        print("FAIL: atteso UP al primo ping")
        ok = False
    else:
        print("OK  ping UP")

    state["up"] = False
    hc.tick(force=True)
    if hc.ok or hc._alarm_latched:
        print(f"FAIL: down breve non deve latchare (ok={hc.ok}, "
              f"latch={hc._alarm_latched})")
        ok = False
    else:
        print("OK  DOWN breve senza CRITICAL latch")

    time.sleep(1.1)
    hc.tick(force=True)
    if not hc._alarm_latched or hc.ok:
        print(f"FAIL: dopo >max_down atteso latch (ok={hc.ok}, "
              f"latch={hc._alarm_latched})")
        ok = False
    else:
        print("OK  CRITICAL latch dopo soglia")

    # secondo tick down: latch resta, non deve "sbloccare" trading (niente da fare)
    hc.tick(force=True)
    if not hc._alarm_latched:
        print("FAIL: latch perso mentre ancora down")
        ok = False
    else:
        print("OK  latch stabile mentre ancora DOWN")

    state["up"] = True
    hc.tick(force=True)
    if not hc.ok or hc._alarm_latched or hc.down_for_sec != 0:
        print(f"FAIL: recovery incompleto ok={hc.ok} latch={hc._alarm_latched} "
              f"down={hc.down_for_sec}")
        ok = False
    else:
        print("OK  recovery UP, latch resettato")

    # garanzia API: nessun metodo di flat/close sul modulo
    banned = [n for n in dir(hc) if "flat" in n.lower() or "close" in n.lower()]
    if banned:
        print(f"FAIL: metodi sospetti sul HealthCheck: {banned}")
        ok = False
    else:
        print("OK  nessun metodo flat/close sul HealthCheck")

    if ok:
        print("\nTutti i check issue #9 PASSATI (telemetria-only).")
        return 0
    print("\nQUALCHE CHECK FALLITO.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
