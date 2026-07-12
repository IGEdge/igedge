"""
DipBuyStrategy — EDGE #1 live (mean-reversion di breve, intraday).

Calcola il segnale dalle barre DAILY di IG (SMA200 + RSI(2)) e decide l'azione.
Esecuzione intraday (flat overnight) gestita dal bot loop. Documentazione e
validazione: docs/EDGE_BUYTHEDIP.md.

Regole:
  ENTER: close > SMA200  AND  RSI(2) < entry_rsi        (compra il dip in uptrend)
  ADD  : in posizione, RSI(2) < add_rsi                 (scale-in su dip profondo)
  EXIT : close > SMA(exit_ma)  OR  RSI(2) > exit_rsi     (rimbalzo completato)
  (il time-exit e il flat-overnight li applica il bot loop)

Interfaccia: decide(has_position, n_units) -> (action, info). Nessuno stop
stretto (peggiora la MR — vedi doc).
"""
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _rsi(close: pd.Series, period: int) -> float:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    ru = up.ewm(alpha=1.0 / period, adjust=False).mean()
    rd = dn.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


class DipBuyStrategy:
    name = "dip_buy"

    def __init__(self, ig_client, config: Dict[str, Any]):
        self.ig = ig_client
        self.epic = config.get("epic", "IX.D.SPTRD.IFE.IP")
        self.entry_rsi = float(config.get("entry_rsi", 10))
        self.exit_rsi = float(config.get("exit_rsi", 70))
        self.exit_ma = int(config.get("exit_ma", 10))
        self.add_rsi = float(config.get("add_rsi", 5))
        self.scale_in = int(config.get("scale_in", 2))
        self.leverage = float(config.get("leverage", 3.0))

    # ------------------------------------------------------------------
    def _indicators(self) -> Optional[Dict[str, float]]:
        """SMA200, SMA(exit_ma), RSI(2) sulle chiusure daily IG (barre chiuse)."""
        res = self.ig.get_prices_v2(self.epic, resolution="DAY", num_points=220)
        bars = res.get("bars", [])
        if len(bars) < 201:
            logger.warning(f"[dip_buy] solo {len(bars)} barre daily (servono 201)")
            return None
        closes = pd.Series([b["close"] for b in bars])
        return {
            "close": float(closes.iloc[-1]),
            "sma200": float(closes.tail(200).mean()),
            "sma_exit": float(closes.tail(self.exit_ma).mean()),
            "rsi2": _rsi(closes, 2),
        }

    # ------------------------------------------------------------------
    def decide(self, has_position: bool, n_units: int = 0
               ) -> Tuple[str, Dict[str, Any]]:
        """Ritorna ('ENTER'|'ADD'|'EXIT'|'HOLD'|'FLAT', info)."""
        ind = self._indicators()
        if ind is None:
            return "FLAT", {"reason": "no_data"}
        info = dict(ind)

        if not has_position:
            if ind["close"] > ind["sma200"] and ind["rsi2"] < self.entry_rsi:
                return "ENTER", info
            return "FLAT", info

        # in posizione
        if ind["close"] > ind["sma_exit"] or ind["rsi2"] > self.exit_rsi:
            return "EXIT", info
        if n_units <= self.scale_in and ind["rsi2"] < self.add_rsi:
            return "ADD", info
        return "HOLD", info
