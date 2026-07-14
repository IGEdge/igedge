"""
PositionStore — stato persistente delle posizioni (SQLite) + reconcile con IG.

La spina dorsale della sicurezza (docs/ARCHITETTURA-BOT.md §2A): ogni posizione
aperta è registrata con il suo dealId e sopravvive ai riavvii. A ogni ciclo si
riconcilia con lo stato reale su IG per non tradare mai alla cieca:

  - posizione nostra OPEN ma NON su IG  -> chiusa esternamente (SL/manuale) ->
    la marchiamo CLOSED (reason=external) e la segnaliamo;
  - posizione su IG ma NON nostra        -> ORFANA (aperta fuori dal bot) ->
    segnalata (decisione all'operatore/strategia).

Zero dipendenze esterne (sqlite3 stdlib).
"""
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PositionStore:
    def __init__(self, db_path: str = "data/positions.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id      TEXT,
                epic         TEXT NOT NULL,
                strategy     TEXT NOT NULL,
                direction    TEXT NOT NULL,      -- BUY | SELL
                size         REAL NOT NULL,
                entry_level  REAL,
                entry_ts     TEXT NOT NULL,
                status       TEXT NOT NULL,      -- OPEN | CLOSED
                exit_level   REAL,
                exit_ts      TEXT,
                exit_reason  TEXT,               -- signal | external | manual | ...
                pnl          REAL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_status ON positions(status)")
        self._conn.commit()

    # ------------------------------------------------------------------
    # Scritture
    # ------------------------------------------------------------------

    def record_open(self, deal_id: str, epic: str, strategy: str,
                    direction: str, size: float,
                    entry_level: Optional[float] = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO positions (deal_id, epic, strategy, direction, size, "
            "entry_level, entry_ts, status) VALUES (?,?,?,?,?,?,?, 'OPEN')",
            (deal_id, epic, strategy, direction.upper(), size, entry_level,
             _utc_now()),
        )
        self._conn.commit()
        logger.info(f"[Store] OPEN #{cur.lastrowid} {strategy} {direction} "
                    f"{size} {epic} deal={deal_id}")
        return cur.lastrowid

    def record_close(self, deal_id: str, exit_level: Optional[float] = None,
                     exit_reason: str = "signal",
                     pnl: Optional[float] = None) -> bool:
        cur = self._conn.execute(
            "UPDATE positions SET status='CLOSED', exit_level=?, exit_ts=?, "
            "exit_reason=?, pnl=? WHERE deal_id=? AND status='OPEN'",
            (exit_level, _utc_now(), exit_reason, pnl, deal_id),
        )
        self._conn.commit()
        if cur.rowcount:
            logger.info(f"[Store] CLOSE deal={deal_id} reason={exit_reason} "
                        f"pnl={pnl}")
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Letture
    # ------------------------------------------------------------------

    def get_open(self, strategy: Optional[str] = None) -> List[Dict[str, Any]]:
        q = "SELECT * FROM positions WHERE status='OPEN'"
        args: tuple = ()
        if strategy:
            q += " AND strategy=?"
            args = (strategy,)
        return [dict(r) for r in self._conn.execute(q, args).fetchall()]

    def has_open(self, strategy: str, epic: Optional[str] = None) -> bool:
        """Idempotenza: la strategia ha già una posizione aperta?"""
        for p in self.get_open(strategy):
            if epic is None or p["epic"] == epic:
                return True
        return False

    def history(self, limit: int = 200) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM positions ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]

    # ------------------------------------------------------------------
    # Reconcile con IG (da chiamare a OGNI ciclo prima di operare)
    # ------------------------------------------------------------------

    def reconcile(self, ig_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Confronta lo stato nostro con le posizioni reali IG (output di
        IGClient.get_positions()). Aggiorna le chiuse esternamente, segnala gli
        orfani. Ritorna un report; NON chiude nulla in automatico (decisione
        dell'operatore/strategia sugli orfani)."""
        ig_by_deal: Dict[str, Dict[str, Any]] = {}
        for item in ig_positions:
            pos = item.get("position", {}) or {}
            deal = pos.get("dealId")
            if deal:
                ig_by_deal[deal] = item

        our_open = self.get_open()
        our_deals = {p["deal_id"] for p in our_open if p["deal_id"]}

        closed_externally = []
        for p in our_open:
            if p["deal_id"] and p["deal_id"] not in ig_by_deal:
                self.record_close(p["deal_id"], exit_reason="external")
                closed_externally.append(p)

        orphans = [item for deal, item in ig_by_deal.items()
                   if deal not in our_deals]

        report = {
            "ok": not closed_externally and not orphans,
            "our_open": len(our_open),
            "ig_open": len(ig_by_deal),
            "closed_externally": closed_externally,
            "orphans_on_ig": orphans,
        }
        if closed_externally:
            logger.warning(f"[Reconcile] {len(closed_externally)} posizioni "
                           f"chiuse esternamente (SL/manuale)")
        if orphans:
            logger.warning(f"[Reconcile] {len(orphans)} posizioni ORFANE su IG "
                           f"(non nostre) — richiede attenzione")
        return report

    def close(self):
        self._conn.close()
