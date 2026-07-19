"""
HealthCheck — telemetria API IG (issue #9).

Ping periodico; se l'API resta down oltre `max_down_sec` → allarme in LOG.
NON chiude posizioni, NON blocca ingressi, NON cambia sizing.

Principio (decisione 19 lug 2026): solo osservazione. Il flat automatico su
API-down è escluso di proposito (falsi positivi di rete = danni sul book).
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class HealthCheck:
    """`probe` deve tornare True se IG risponde in modo utile, False altrimenti."""

    def __init__(self, probe: Callable[[], bool],
                 interval_sec: float = 5.0,
                 max_down_sec: float = 30.0):
        self.probe = probe
        self.interval_sec = max(0.5, float(interval_sec))
        self.max_down_sec = max(1.0, float(max_down_sec))
        self._last_tick = 0.0
        self._down_since: Optional[float] = None
        self._alarm_latched = False
        self.ok = True
        self.last_error: Optional[str] = None
        self.pings = 0
        self.failures = 0

    @property
    def down_for_sec(self) -> float:
        if self._down_since is None:
            return 0.0
        return time.monotonic() - self._down_since

    def tick(self, force: bool = False) -> bool:
        """Esegue un ping se è passato `interval_sec` (o force=True).
        Ritorna True se l'ultimo stato conosciuto è UP."""
        now = time.monotonic()
        if not force and (now - self._last_tick) < self.interval_sec:
            return self.ok
        self._last_tick = now
        self.pings += 1
        try:
            up = bool(self.probe())
            err = None if up else "probe returned False"
        except Exception as e:
            up = False
            err = str(e)
        if up:
            if self._down_since is not None:
                logger.info(
                    f"[Health] IG di nuovo UP dopo {self.down_for_sec:.0f}s down "
                    f"(pings={self.pings}, fail={self.failures})")
            self._down_since = None
            self._alarm_latched = False
            self.ok = True
            self.last_error = None
            return True

        self.failures += 1
        self.ok = False
        self.last_error = err
        if self._down_since is None:
            self._down_since = now
            logger.warning(f"[Health] IG DOWN (inizio): {err}")
        elif self.down_for_sec >= self.max_down_sec and not self._alarm_latched:
            self._alarm_latched = True
            logger.critical(
                f"[Health] ⚠️ API-DOWN > {self.max_down_sec:.0f}s "
                f"(da {self.down_for_sec:.0f}s) — SOLO ALLARME LOG, "
                f"nessun flat automatico. Ultimo errore: {err}")
        else:
            logger.warning(
                f"[Health] IG ancora DOWN da {self.down_for_sec:.0f}s: {err}")
        return False

    def sleep_while_monitoring(self, total_sec: float) -> None:
        """Attende `total_sec` secondi, facendo tick di health nel frattempo."""
        if total_sec <= 0:
            return
        end = time.monotonic() + total_sec
        while True:
            self.tick()
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(self.interval_sec, remaining))
