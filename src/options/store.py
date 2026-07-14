"""
CondorStore — stato persistente dei condor (SQLite). Ogni condor con le sue 4
gambe (dealId, strike, fill), stato e scadenza. Sopravvive ai riavvii ed è la base
per il monitoraggio e il reconcile con IG (mai perdere una posizione).

Zero dipendenze esterne (sqlite3 stdlib). Speculare a src/core/position_store.py
ma per la struttura a 4 gambe.
"""
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from .condor import Condor, Leg


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class CondorStore:
    def __init__(self, db_path: str = "data/condors.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS condors (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                expiry         TEXT NOT NULL,
                underlying_epic TEXT,
                entry_spot     REAL, entry_vix REAL,
                target_credit  REAL, max_loss REAL, size REAL,
                status         TEXT NOT NULL,      -- OPEN|INCOMPLETE_HELD|CLOSED|ABORTED|PARTIAL_ERROR
                opened_ts      TEXT, closed_ts TEXT, close_reason TEXT,
                realized_pnl   REAL
            );
            CREATE TABLE IF NOT EXISTS condor_legs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                condor_id    INTEGER NOT NULL,
                role         TEXT NOT NULL, epic TEXT NOT NULL,
                direction    TEXT NOT NULL, kind TEXT NOT NULL,
                strike       REAL, size REAL,
                status       TEXT NOT NULL,
                deal_id      TEXT, fill_level REAL, reason TEXT,
                FOREIGN KEY(condor_id) REFERENCES condors(id)
            );
            CREATE INDEX IF NOT EXISTS idx_condor_status ON condors(status);
            CREATE INDEX IF NOT EXISTS idx_leg_condor ON condor_legs(condor_id);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    def record(self, c: Condor) -> int:
        """Salva un condor + le sue 4 gambe. Ritorna l'id nel DB."""
        size = c.legs[0].size if c.legs else 0.0
        cur = self._conn.execute(
            "INSERT INTO condors (expiry, underlying_epic, entry_spot, entry_vix, "
            "target_credit, max_loss, size, status, opened_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (c.expiry, c.underlying_epic, c.entry_spot, c.entry_vix,
             c.target_credit, c.max_loss, size, c.status, c.opened_ts or _utc()))
        cid = cur.lastrowid
        for l in c.legs:
            self._conn.execute(
                "INSERT INTO condor_legs (condor_id, role, epic, direction, kind, "
                "strike, size, status, deal_id, fill_level, reason) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (cid, l.role, l.epic, l.direction, l.kind, l.strike, l.size,
                 l.status, l.deal_id, l.fill_level, l.reason))
        self._conn.commit()
        return cid

    def update_status(self, condor_id: int, status: str,
                      close_reason: Optional[str] = None,
                      realized_pnl: Optional[float] = None):
        closed = _utc() if status in ("CLOSED", "ABORTED") else None
        self._conn.execute(
            "UPDATE condors SET status=?, closed_ts=COALESCE(?, closed_ts), "
            "close_reason=COALESCE(?, close_reason), "
            "realized_pnl=COALESCE(?, realized_pnl) WHERE id=?",
            (status, closed, close_reason, realized_pnl, condor_id))
        self._conn.commit()

    def update_leg(self, condor_id: int, role: str, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        args = list(fields.values()) + [condor_id, role]
        self._conn.execute(
            f"UPDATE condor_legs SET {cols} WHERE condor_id=? AND role=?", args)
        self._conn.commit()

    # ------------------------------------------------------------------
    def _row_to_condor(self, row: sqlite3.Row) -> Condor:
        legs = []
        for lr in self._conn.execute(
                "SELECT * FROM condor_legs WHERE condor_id=?", (row["id"],)).fetchall():
            legs.append(Leg(role=lr["role"], epic=lr["epic"], direction=lr["direction"],
                            kind=lr["kind"], strike=lr["strike"], size=lr["size"],
                            status=lr["status"], deal_id=lr["deal_id"],
                            fill_level=lr["fill_level"], reason=lr["reason"]))
        c = Condor(underlying_epic=row["underlying_epic"], expiry=row["expiry"],
                   entry_spot=row["entry_spot"], entry_vix=row["entry_vix"],
                   legs=legs, target_credit=row["target_credit"],
                   max_loss=row["max_loss"], status=row["status"],
                   opened_ts=row["opened_ts"])
        c.store_id = row["id"]      # comodità per il monitor
        return c

    def get_open(self) -> List[Condor]:
        """Condor ancora a mercato (OPEN o INCOMPLETE_HELD)."""
        rows = self._conn.execute(
            "SELECT * FROM condors WHERE status IN ('OPEN','INCOMPLETE_HELD') "
            "ORDER BY id").fetchall()
        return [self._row_to_condor(r) for r in rows]

    def get(self, condor_id: int) -> Optional[Condor]:
        r = self._conn.execute("SELECT * FROM condors WHERE id=?", (condor_id,)).fetchone()
        return self._row_to_condor(r) if r else None

    def history(self, limit: int = 100) -> List[Condor]:
        rows = self._conn.execute(
            "SELECT * FROM condors ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_condor(r) for r in rows]

    def close(self):
        self._conn.close()
