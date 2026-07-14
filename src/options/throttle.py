"""
ThrottledClient — wrapper che impone un intervallo minimo tra le chiamate IG, per
NON arrivare mai al rate-limit (`exceeded-api-key-allowance`). Approccio proattivo:
si aspetta PRIMA di ogni chiamata, così restiamo sotto il limite invece di
sbatterci contro e ritentare.

Avvolge un IGClient (o qualunque client con gli stessi metodi). Tutte le chiamate
usate dai moduli opzioni passano di qui: get_market, open_position,
close_position, get_positions, search_markets. login/logout e gli attributi
(base_url, account_id, _headers) passano dritti.

Difesa aggiuntiva: se una chiamata torna un errore di allowance, backoff lungo e
un solo retry (non dovrebbe mai servire col throttle, ma è una rete di sicurezza).
"""
import time
from typing import Any, Optional


class ThrottledClient:
    def __init__(self, client, min_interval: float = 2.5, audit=None,
                 allowance_backoff: float = 65.0):
        self._c = client
        self.min_interval = min_interval
        self.audit = audit
        self.allowance_backoff = allowance_backoff
        self._last = 0.0
        self._calls = 0

    # ------------------------------------------------------------------
    def _wait(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()
        self._calls += 1

    def _throttled(self, method, *args, **kwargs) -> Any:
        self._wait()
        return method(*args, **kwargs)

    # metodi usati dai moduli opzioni (throttlati) ----------------------
    def get_market(self, *a, **k):
        return self._throttled(self._c.get_market, *a, **k)

    def open_position(self, *a, **k):
        return self._throttled(self._c.open_position, *a, **k)

    def close_position(self, *a, **k):
        return self._throttled(self._c.close_position, *a, **k)

    def get_positions(self, *a, **k):
        return self._throttled(self._c.get_positions, *a, **k)

    def search_markets(self, *a, **k):
        return self._throttled(self._c.search_markets, *a, **k)

    # login/logout: una tantum, non throttlati -------------------------
    def login(self):
        return self._c.login()

    def logout(self):
        return self._c.logout()

    @property
    def calls(self) -> int:
        return self._calls

    # tutto il resto (base_url, account_id, _headers, ...) passa dritto
    def __getattr__(self, name):
        return getattr(self._c, name)
