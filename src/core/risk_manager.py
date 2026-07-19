"""
RiskManager — sizing CFD con leva, kill switch giornaliero, cap esposizione.

Regole (docs/ARCHITETTURA-BOT.md §2B):
  - size CFD:  notional_target = equity * leva  ->  size = notional / (prezzo * val_punto)
  - kill switch: se l'equity scende di > max_daily_loss% dal valore di inizio
    giornata (UTC) -> stop nuovi ingressi;
  - max posizioni aperte contemporanee;
  - cap esposizione lorda aggregata (leva totale <= max_gross).
"""
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, ig_client, max_daily_loss_pct: float = 0.03,
                 max_open_trades: int = 3, max_gross_exposure: float = 3.0,
                 value_per_point: float = 1.0):
        self.ig = ig_client
        self.max_daily_loss = max_daily_loss_pct
        self.max_open_trades = max_open_trades
        self.max_gross = max_gross_exposure
        self.vpp = value_per_point
        self._day: Optional[str] = None
        self._day_start_equity: Optional[float] = None

    # ------------------------------------------------------------------
    def equity(self) -> float:
        """Balance del conto operativo (IG). 0.0 se non recuperabile."""
        try:
            for a in self.ig.get_accounts():
                if not self.ig.account_id or a.get("accountId") == self.ig.account_id:
                    return float((a.get("balance") or {}).get("balance") or 0.0)
        except Exception as e:
            logger.error(f"[Risk] equity() error: {e}")
        return 0.0

    def size_for(self, price: float, leverage: float,
                 min_size: float = 1.0, step: float = 1.0,
                 units: int = 1) -> float:
        """Contratti di UNA unità. Il notional target (equity*leva) è SPALMATO
        su `units` unità uguali (1 + scale_in — issue #8: come nel backtest,
        unità uguali; MAI leva piena a ogni ADD). Arrotondato allo step verso
        il basso (mai sovra-leva), >= min_size. NB: a equity piccola il floor
        min_size può rendere l'unità più grande del target — è il cap di
        esposizione lorda (can_open) a bloccare gli ADD in quel caso."""
        eq = self.equity()
        if eq <= 0 or price <= 0:
            return 0.0
        raw = (eq * leverage) / (price * self.vpp * max(1, int(units)))
        n = math.floor(raw / step) * step
        return max(min_size, round(n, 4))

    # ------------------------------------------------------------------
    def _roll_day(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._day != today:
            self._day = today
            self._day_start_equity = self.equity()
            logger.info(f"[Risk] nuovo giorno {today}, equity inizio "
                        f"{self._day_start_equity:.2f}")

    def kill_switch(self) -> bool:
        """True = perdita giornaliera oltre soglia -> blocca nuovi ingressi."""
        self._roll_day()
        if not self._day_start_equity:
            return False
        eq = self.equity()
        dd = (eq - self._day_start_equity) / self._day_start_equity
        if dd <= -self.max_daily_loss:
            logger.critical(f"[Risk] KILL SWITCH: {dd:+.2%} oggi "
                            f"(soglia -{self.max_daily_loss:.0%})")
            return True
        return False

    def gross_exposure(self, open_positions: List[Dict[str, Any]],
                       price: float) -> float:
        """Leva lorda usata = somma nozionali / equity."""
        eq = self.equity()
        if eq <= 0:
            return 0.0
        notional = sum(abs(p.get("size", 0)) * price * self.vpp
                       for p in open_positions)
        return notional / eq

    def can_open(self, open_positions: List[Dict[str, Any]],
                 price: float, new_size: float) -> Tuple[bool, str]:
        """Gate d'ingresso: kill switch + max posizioni + cap esposizione."""
        if self.kill_switch():
            return False, "kill switch giornaliero attivo"
        if len(open_positions) >= self.max_open_trades:
            return False, f"max posizioni ({self.max_open_trades}) raggiunto"
        eq = self.equity()
        if eq <= 0:
            return False, "equity non disponibile"
        future_gross = self.gross_exposure(open_positions, price) \
            + (new_size * price * self.vpp) / eq
        if future_gross > self.max_gross:
            return False, (f"cap esposizione: {future_gross:.1f}x > "
                           f"{self.max_gross:.1f}x")
        return True, "ok"
