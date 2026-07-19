"""
SpreadStore — stato persistente degli spread multi-gamba (SQLite).

Generico (putspread / callspread / legacy). Sopravvive ai riavvii; base per
monitor e reconcile IG.

Nota schema (issue #16): le tabelle SQL restano `condors` / `condor_legs` per
non rompere DB già sul Pi. Solo l'API Python è rinominata. File default:
`data/spreads.db`, con fallback automatico a `data/condors.db` se esiste già.
"""
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Union

from .spread import Leg, OptionSpread

# Alias tipi
Condor = OptionSpread


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_spreads_db_path(preferred: Optional[str] = None) -> str:
    """Sceglie il path DB senza perdere dati legacy.

    Ordine: path esplicito → spreads.db se esiste → condors.db se esiste →
    crea spreads.db.
    """
    if preferred:
        return preferred
    new = "data/spreads.db"
    old = "data/condors.db"
    if os.path.isfile(new):
        return new
    if os.path.isfile(old):
        return old
    return new


class SpreadStore:
    def __init__(self, db_path: Optional[str] = None):
        path = resolve_spreads_db_path(db_path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db_path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        # Nomi tabella legacy `condors*` — non rinominare senza migrazione dedicata
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS condors (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                expiry         TEXT NOT NULL,
                underlying_epic TEXT,
                entry_spot     REAL, entry_vix REAL,
                target_credit  REAL, max_loss REAL, size REAL,
                status         TEXT NOT NULL,
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
        try:
            self._conn.execute("ALTER TABLE condors ADD COLUMN strategy TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    def record(self, c: OptionSpread) -> int:
        """Salva uno spread + gambe. Ritorna l'id nel DB."""
        size = c.legs[0].size if c.legs else 0.0
        strat = getattr(c, "strategy", None) or "unknown"
        cur = self._conn.execute(
            "INSERT INTO condors (expiry, underlying_epic, entry_spot, entry_vix, "
            "target_credit, max_loss, size, status, opened_ts, strategy) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (c.expiry, c.underlying_epic, c.entry_spot, c.entry_vix,
             c.target_credit, c.max_loss, size, c.status, c.opened_ts or _utc(),
             strat))
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

    def update_status(self, spread_id: int, status: str,
                      close_reason: Optional[str] = None,
                      realized_pnl: Optional[float] = None):
        closed = _utc() if status in ("CLOSED", "ABORTED") else None
        self._conn.execute(
            "UPDATE condors SET status=?, closed_ts=COALESCE(?, closed_ts), "
            "close_reason=COALESCE(?, close_reason), "
            "realized_pnl=COALESCE(?, realized_pnl) WHERE id=?",
            (status, closed, close_reason, realized_pnl, spread_id))
        self._conn.commit()

    def update_leg(self, spread_id: int, role: str, **fields):
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        args = list(fields.values()) + [spread_id, role]
        self._conn.execute(
            f"UPDATE condor_legs SET {cols} WHERE condor_id=? AND role=?", args)
        self._conn.commit()

    def _row_to_spread(self, row: sqlite3.Row) -> OptionSpread:
        legs = []
        for lr in self._conn.execute(
                "SELECT * FROM condor_legs WHERE condor_id=?", (row["id"],)).fetchall():
            legs.append(Leg(role=lr["role"], epic=lr["epic"], direction=lr["direction"],
                            kind=lr["kind"], strike=lr["strike"], size=lr["size"],
                            status=lr["status"], deal_id=lr["deal_id"],
                            fill_level=lr["fill_level"], reason=lr["reason"]))
        c = OptionSpread(underlying_epic=row["underlying_epic"], expiry=row["expiry"],
                         entry_spot=row["entry_spot"], entry_vix=row["entry_vix"],
                         legs=legs, target_credit=row["target_credit"],
                         max_loss=row["max_loss"], status=row["status"],
                         opened_ts=row["opened_ts"])
        c.store_id = row["id"]
        try:
            c.strategy = row["strategy"] or "unknown"
        except (IndexError, KeyError):
            c.strategy = "unknown"
        return c

    # alias interno usato da codice legacy
    _row_to_condor = _row_to_spread

    def get_open(self) -> List[OptionSpread]:
        rows = self._conn.execute(
            "SELECT * FROM condors WHERE status IN ('OPEN','INCOMPLETE_HELD') "
            "ORDER BY id").fetchall()
        return [self._row_to_spread(r) for r in rows]

    def get(self, spread_id: int) -> Optional[OptionSpread]:
        r = self._conn.execute("SELECT * FROM condors WHERE id=?", (spread_id,)).fetchone()
        return self._row_to_spread(r) if r else None

    def history(self, limit: int = 100) -> List[OptionSpread]:
        rows = self._conn.execute(
            "SELECT * FROM condors ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._row_to_spread(r) for r in rows]

    def close(self):
        self._conn.close()


# Alias retrocompat
CondorStore = SpreadStore
