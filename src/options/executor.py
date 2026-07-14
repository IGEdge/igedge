"""
CondorExecutor — apertura/chiusura SICURA ed ECONOMICA delle 4 gambe.

Principio: mai uno short nudo — MA senza sprecare spread disfacendo tutto al primo
errore di IG. Chiave: **ordine longs-first**. Aprendo prima le 2 ali di protezione
e poi gli short, OGNI stato intermedio è a rischio definito (mai naked). Quindi, se
una gamba fallisce, si può **INSISTERE (ritentare)** su quella gamba invece di
disfare — è sicuro e non butta via lo spread già pagato.

Apertura (`open_condor`):
  0. PREFLIGHT: le 4 gambe tradeable con quote sane, altrimenti non si apre nulla.
  1. Apri in ordine longs-first. Su ogni gamba RITENTA (backoff) con guardia
     anti-doppione (controllo get_positions prima di ritentare → mai due volte).
  2. Se una gamba fallisce DOPO tutti i retry:
       - la posizione è a rischio definito (longs-first) → NON si disfa;
       - **regola invalicabile:** se manca un'ALA, NON si apre il suo short;
       - default `on_fail="hold"`: si TIENE il parziale (defined-risk) + ALLARME
         CRITICO all'operatore (completare/decidere). `on_fail="unwind"` = flat.
  3. Guardia difensiva: se mai risultasse uno short nudo (non dovrebbe, con
     longs-first) → unwind forzato immediato.

Chiusura (`close_condor`): shorts-first (togli il rischio), con retry.

Il client è iniettabile: reale (IGClient live) o simulato (MockIG) per il dry-run.
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .audit_log import AuditLog
from .condor import Condor, Leg


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class CondorExecutor:
    def __init__(self, client, audit: AuditLog = None, live: bool = False,
                 max_spread_pts: float = 6.0, currency: str = "USD",
                 open_retries: int = 5, close_retries: int = 5,
                 retry_delay: float = 1.5, on_fail: str = "hold"):
        self.client = client
        self.audit = audit or AuditLog(dry_run=not live)
        self.live = live
        self.max_spread_pts = max_spread_pts
        self.currency = currency
        self.open_retries = open_retries         # insisti sulla gamba che manca
        self.close_retries = close_retries       # una chiusura DEVE riuscire
        self.retry_delay = retry_delay
        self.on_fail = on_fail                    # "hold" (default) | "unwind"

    # ==================================================================
    # PREFLIGHT
    # ==================================================================
    def preflight(self, condor: Condor) -> Dict[str, Any]:
        problems = []
        for leg in condor.legs:
            m = self.client.get_market(leg.epic)
            if not m:
                problems.append((leg.role, "no_market_data")); continue
            snap = m.get("snapshot", {}) or {}
            status, bid, offer = snap.get("marketStatus"), snap.get("bid"), snap.get("offer")
            if status != "TRADEABLE":
                problems.append((leg.role, f"status={status}"))
            elif bid is None or offer is None:
                problems.append((leg.role, "no_quote"))
            elif (offer - bid) > self.max_spread_pts:
                problems.append((leg.role, f"spread={offer - bid:.1f}>{self.max_spread_pts}"))
        ok = not problems
        self.audit.event("preflight", level="INFO" if ok else "ERROR",
                         ok=ok, problems=problems, expiry=condor.expiry)
        return {"ok": ok, "problems": problems}

    # ==================================================================
    # APERTURA
    # ==================================================================
    def open_condor(self, condor: Condor, on_fail: Optional[str] = None) -> Dict[str, Any]:
        policy = on_fail or self.on_fail
        self.audit.info("condor_open_start", desc=condor.describe(), live=self.live,
                        policy=policy)

        pf = self.preflight(condor)
        if not pf["ok"]:
            condor.status = "ABORTED"
            self.audit.error("condor_aborted_preflight", problems=pf["problems"])
            return {"ok": False, "reason": "preflight_failed", "problems": pf["problems"]}

        opened: List[Leg] = []
        for leg in condor.open_order():          # LONGS first, poi SHORTS
            res = self._open_leg_robust(leg)     # ritenta + guardia anti-doppione
            if res["ok"]:
                leg.status = "OPEN"; leg.deal_id = res["deal_id"]; leg.fill_level = res.get("level")
                opened.append(leg)
                self.audit.info("leg_opened", role=leg.role, epic=leg.epic,
                                direction=leg.direction, deal_id=leg.deal_id,
                                fill=leg.fill_level, adopted=res.get("adopted", False))
            else:
                leg.status = "FAILED"; leg.reason = res["reason"]
                self.audit.critical("leg_open_persistent_fail", role=leg.role,
                                    epic=leg.epic, reason=res["reason"],
                                    retries=self.open_retries)
                return self._handle_incomplete(condor, opened, leg, policy)

        condor.status = "OPEN"; condor.opened_ts = _utc()
        self.audit.info("condor_OPEN_OK", expiry=condor.expiry, legs=len(opened),
                        deals=[l.deal_id for l in opened])
        return {"ok": True, "condor": condor}

    def _handle_incomplete(self, condor: Condor, opened: List[Leg],
                           failed: Leg, policy: str) -> Dict[str, Any]:
        """Gestisce l'apertura incompleta. La posizione è defined-risk (longs-first);
        di default la si TIENE + allarme. Guardia: se mai fosse naked → unwind."""
        # difesa: c'è uno short OPEN senza la sua ala LONG aperta?
        longs_all_open = all(l.status == "OPEN" for l in condor.legs if l.is_long)
        naked = any(l.status == "OPEN" and not l.is_long for l in condor.legs) and not longs_all_open
        if naked:
            self.audit.critical("NAKED_SHORT_DETECTED_forcing_unwind", failed=failed.role)
            self._unwind(condor, opened, trigger=f"naked_after:{failed.role}")
            return {"ok": False, "reason": f"naked_unwound:{failed.role}", "action": "unwound"}

        if policy == "unwind":
            self._unwind(condor, opened, trigger=f"policy_unwind:{failed.role}")
            return {"ok": False, "reason": f"incomplete:{failed.role}", "action": "unwound"}

        # default HOLD: parziale a rischio definito, tenuto + allarme operatore
        condor.status = "INCOMPLETE_HELD"
        self.audit.critical("INCOMPLETE_HELD_defined_risk", failed=failed.role,
                            open_legs=[l.role for l in opened],
                            note="posizione a rischio definito; operatore: completa la gamba mancante o decidi")
        return {"ok": False, "reason": f"incomplete_held:{failed.role}",
                "action": "held", "open_legs": [l.role for l in opened]}

    # ==================================================================
    # CHIUSURA (normale) / UNWIND (solo su policy o difesa)
    # ==================================================================
    def close_condor(self, condor: Condor, reason: str = "manual") -> Dict[str, Any]:
        self.audit.info("condor_close_start", reason=reason, expiry=condor.expiry)
        stuck = []
        for leg in condor.close_order():         # SHORTS first
            if leg.status != "OPEN":
                continue
            res = self._close_leg(leg)
            if res["ok"]:
                leg.status = "CLOSED"; leg.fill_level = res.get("level", leg.fill_level)
                self.audit.info("leg_closed", role=leg.role, deal_id=leg.deal_id, fill=res.get("level"))
            else:
                stuck.append(leg)
                self.audit.critical("leg_close_FAILED", role=leg.role, deal_id=leg.deal_id, reason=res["reason"])
        if stuck:
            condor.status = "PARTIAL_ERROR"
            self.audit.critical("MANUAL_INTERVENTION_NEEDED", stuck=[l.role for l in stuck],
                                deal_ids=[l.deal_id for l in stuck])
            return {"ok": False, "reason": "close_failed", "stuck": [l.role for l in stuck]}
        condor.status = "CLOSED"
        self.audit.info("condor_CLOSED_OK", reason=reason)
        return {"ok": True}

    def _unwind(self, condor: Condor, opened: List[Leg], trigger: str) -> None:
        self.audit.warn("UNWIND_start", trigger=trigger, to_close=len(opened))
        stuck = []
        for leg in reversed(opened):
            res = self._close_leg(leg)
            if res["ok"]:
                leg.status = "CLOSED"
                self.audit.info("leg_unwound", role=leg.role, deal_id=leg.deal_id)
            else:
                stuck.append(leg)
                self.audit.critical("UNWIND_leg_FAILED", role=leg.role, deal_id=leg.deal_id, reason=res["reason"])
        if stuck:
            condor.status = "PARTIAL_ERROR"
            self.audit.critical("MANUAL_INTERVENTION_NEEDED", trigger=trigger,
                                stuck=[l.role for l in stuck], deal_ids=[l.deal_id for l in stuck])
        else:
            condor.status = "ABORTED"
            self.audit.info("UNWIND_complete_FLAT", trigger=trigger)

    # ==================================================================
    # Gambe singole
    # ==================================================================
    def _open_leg_robust(self, leg: Leg) -> Dict[str, Any]:
        """Apre una gamba INSISTENDO: ritenta fino a open_retries. Dopo ogni
        fallimento controlla get_positions (guardia anti-doppione): se la gamba è
        in realtà aperta (conferma persa), la adotta invece di riaprirla."""
        last = {"ok": False, "reason": "unknown"}
        for attempt in range(self.open_retries + 1):
            last = self._open_leg(leg)
            if last["ok"]:
                if attempt > 0:
                    self.audit.info("leg_open_retry_ok", role=leg.role, attempt=attempt + 1)
                return last
            # fallita: forse è passata comunque? (conferma ambigua)
            existing = self._find_open_position(leg.epic)
            if existing:
                self.audit.warn("leg_open_adopted_ambiguous", role=leg.role,
                                epic=leg.epic, deal_id=existing["deal_id"])
                return {"ok": True, "deal_id": existing["deal_id"],
                        "level": existing.get("level"), "adopted": True}
            self.audit.warn("leg_open_retry", role=leg.role, epic=leg.epic,
                            attempt=attempt + 1, reason=last["reason"])
            if attempt < self.open_retries:
                time.sleep(self.retry_delay)
        return last

    def _open_leg(self, leg: Leg) -> Dict[str, Any]:
        try:
            conf = self.client.open_position(
                leg.epic, leg.direction, leg.size,
                currency=self.currency, order_type="MARKET")
        except Exception as e:
            return {"ok": False, "reason": f"exception:{e}"}
        return self._verify(conf)

    def _close_leg(self, leg: Leg) -> Dict[str, Any]:
        """Chiude una gamba; flattare è prioritario → ritenta fino a close_retries."""
        if not leg.deal_id:
            return {"ok": False, "reason": "no_deal_id"}
        last = {"ok": False, "reason": "unknown"}
        for attempt in range(self.close_retries + 1):
            try:
                conf = self.client.close_position(leg.deal_id, leg.direction, leg.size)
                last = self._verify(conf)
            except Exception as e:
                last = {"ok": False, "reason": f"exception:{e}"}
            if last["ok"]:
                if attempt > 0:
                    self.audit.info("leg_close_retry_ok", role=leg.role, attempt=attempt + 1)
                return last
            self.audit.warn("leg_close_retry", role=leg.role, deal_id=leg.deal_id,
                            attempt=attempt + 1, reason=last["reason"])
            if attempt < self.close_retries:
                time.sleep(self.retry_delay)
        return last

    def _find_open_position(self, epic: str) -> Optional[Dict[str, Any]]:
        """Guardia anti-doppione: c'è già una nostra posizione aperta su questo epic?
        (usata solo dopo un'apertura fallita/ambigua)."""
        try:
            for item in self.client.get_positions():
                pos = item.get("position", {}) or {}
                mkt = item.get("market", {}) or {}
                if mkt.get("epic") == epic and pos.get("dealId"):
                    return {"deal_id": pos.get("dealId"), "level": pos.get("level")}
        except Exception as e:
            self.audit.warn("get_positions_failed_during_guard", epic=epic, reason=str(e))
        return None

    @staticmethod
    def _verify(conf) -> Dict[str, Any]:
        """OK solo se ACCEPTED con dealId. None/REJECTED/senza dealId = fallimento."""
        if conf is None:
            return {"ok": False, "reason": "no_confirm"}
        if conf.get("dealStatus") == "ACCEPTED" and conf.get("dealId"):
            return {"ok": True, "deal_id": conf.get("dealId"), "level": conf.get("level")}
        return {"ok": False, "reason": conf.get("reason") or conf.get("dealStatus") or "rejected"}
