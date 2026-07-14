"""
OrderManager — esecuzione sicura: conferma il fill, retry sui transitori,
idempotenza, e registra tutto nel PositionStore.

Principi (docs/ARCHITETTURA-BOT.md §2A):
  - MAI assumere il fill: ogni deal è confermato (dealStatus ACCEPTED/REJECTED);
  - idempotenza: non apre se la strategia ha già una posizione su quell'epic;
  - retry SOLO sui fallimenti transitori (nessuna conferma), MAI su REJECTED
    (rifiuto logico: size, mercato chiuso, regola violata);
  - ogni apertura/chiusura è scritta nello store (con dealId) per il reconcile.
"""
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, ig_client, store, max_retries: int = 2,
                 retry_delay: float = 1.0):
        self.ig = ig_client
        self.store = store
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def open(self, epic: str, direction: str, size: float, strategy: str,
             stop_distance: Optional[float] = None,
             limit_distance: Optional[float] = None) -> Dict[str, Any]:
        # idempotenza: una posizione per strategia+epic
        if self.store.has_open(strategy, epic):
            logger.info(f"[Order] {strategy} ha già una posizione su {epic} — skip")
            return {"ok": False, "reason": "already_open"}
        if size <= 0:
            return {"ok": False, "reason": "size<=0"}

        for attempt in range(self.max_retries + 1):
            conf = self.ig.open_position(
                epic, direction, size,
                stop_distance=stop_distance, limit_distance=limit_distance)
            if conf is None:
                logger.warning(f"[Order] nessuna conferma (transitorio) "
                               f"tentativo {attempt + 1}/{self.max_retries + 1}")
                time.sleep(self.retry_delay)
                continue
            status = conf.get("dealStatus")
            if status == "ACCEPTED":
                deal_id, level = conf.get("dealId"), conf.get("level")
                self.store.record_open(deal_id, epic, strategy, direction,
                                       size, level)
                return {"ok": True, "deal_id": deal_id, "level": level,
                        "confirm": conf}
            # REJECTED = rifiuto logico -> NON ritentare
            reason = conf.get("reason", "REJECTED")
            logger.error(f"[Order] apertura RIFIUTATA {epic}: {reason}")
            return {"ok": False, "reason": reason, "confirm": conf}

        return {"ok": False, "reason": "no_confirm_after_retries"}

    def close(self, position: Dict[str, Any],
              exit_reason: str = "signal") -> Dict[str, Any]:
        """`position` è un dict dello store (deal_id, direction, size, entry_level)."""
        deal_id = position.get("deal_id")
        if not deal_id:
            return {"ok": False, "reason": "no_deal_id"}
        conf = self.ig.close_position(deal_id, position["direction"],
                                      position["size"])
        if conf and conf.get("dealStatus") == "ACCEPTED":
            level = conf.get("level")
            entry = position.get("entry_level")
            pnl = None
            if entry and level:
                d = 1 if position["direction"].upper() == "BUY" else -1
                pnl = d * (level - entry) * position["size"]  # in punti*size
            self.store.record_close(deal_id, level, exit_reason, pnl)
            return {"ok": True, "level": level, "pnl": pnl}
        reason = conf.get("reason", "no_confirm") if conf else "no_confirm"
        logger.error(f"[Order] chiusura fallita deal={deal_id}: {reason}")
        return {"ok": False, "reason": reason}
