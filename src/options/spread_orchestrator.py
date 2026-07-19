"""
SpreadOrchestrator — adapter a 2 GAMBE per gli edge opzioni:

  EDGE #2 putspread  : SELL put 1.5σ + BUY put 2.5σ (ala sotto)
                       segnale: POST-PANICO (VIX≥20 in raffreddamento + VIX/VIX3M≤1)
  EDGE #3 callspread : BUY call ATM + SELL call +1σ
                       segnale: UPTREND (spot > SMA200)

Riusa TUTTA l'infrastruttura del condor (che era 4 gambe): sessione persistente,
executor longs-first con ritento (la gamba COMPRATA si apre per prima → ogni
stato parziale è a rischio definito), store SQLite, throttle, audit.
I segnali di mercato (VIX corrente, max 10gg, ratio VIX3M, SMA200) arrivano da
FUORI (CLI) — qui solo gate + costruzione + economia reale dalle quote.

DEFAULT plan-only: nessun ordine senza armed=True (e --i-understand-live-risk).
"""
import math
from dataclasses import dataclass
from typing import Optional

from .chain_resolver import build_epic, round_strike
from .condor import Condor, Leg
from .orchestrator import Orchestrator


@dataclass
class SpreadConfig:
    # putspread (EDGE #2)
    ps_short_sig: float = 1.5
    ps_wing_sig: float = 2.5
    spike_min: float = 20.0        # post-panico: VIX minimo
    cool: float = 0.90             # ...e sotto il 90% del max 10gg
    ts_max: float = 1.0            # ...e VIX/VIX3M <= 1
    min_credit_pts: float = 4.0
    # callspread (EDGE #3)
    cs_long_sig: float = 0.0       # ATM
    cs_short_sig: float = 1.0
    max_debit_frac: float = 0.35   # sanity: debito <= 35% dell'ampiezza
    # comune
    dte_min: int = 20
    dte_max: int = 45
    capital_eur: float = 1000.0
    eur_per_contract: float = 1000.0   # 1 contratto ogni €1000 di equity
    usd2eur: float = 0.93
    max_positions_per_strat: int = 1
    # issue #7: impegno totale (posizioni aperte + nuovo trade) <= 50% del CONTO
    # REALE letto da /accounts — non solo del capital_eur dichiarato da CLI
    max_account_frac: float = 0.50


class SpreadOrchestrator(Orchestrator):
    """Eredita da Orchestrator: _pick_expiry, _discover_code, _spot_from_monthly,
    _mid, cache e client throttlato. Aggiunge plan/open dei verticali a 2 gambe."""

    def __init__(self, client, store, executor, audit=None, spread_cfg=None):
        super().__init__(client, store, executor, audit=audit)
        self.scfg = spread_cfg or SpreadConfig()
        self.cfg.dte_min = self.scfg.dte_min
        self.cfg.dte_max = self.scfg.dte_max

    # ------------------------------------------------------------- segnali
    def signal(self, strat: str, vix_now: float, vix10max: Optional[float],
               ts_ratio: Optional[float], spot: float,
               sma200: Optional[float]) -> dict:
        c = self.scfg
        if strat == "putspread":
            if vix_now < c.spike_min:
                return {"ok": False, "reason": f"VIX {vix_now:.1f} < {c.spike_min:.0f}: niente panico da vendere"}
            if vix10max is None or not (vix_now < c.cool * vix10max):
                return {"ok": False, "reason": f"VIX {vix_now:.1f} non in raffreddamento "
                        f"(serve < {c.cool:.2f}×max10gg={c.cool*(vix10max or 0):.1f})"}
            if ts_ratio is None or ts_ratio > c.ts_max:
                return {"ok": False, "reason": f"term structure non rientrata "
                        f"(VIX/VIX3M={ts_ratio if ts_ratio else float('nan'):.2f} > {c.ts_max})"}
            return {"ok": True, "reason": "post-panico: spike in raffreddamento, TS ok"}
        if strat == "callspread":
            if sma200 is None:
                return {"ok": False, "reason": "SMA200 non disponibile"}
            if spot <= sma200:
                return {"ok": False, "reason": f"spot {spot:.0f} <= SMA200 {sma200:.0f}: no uptrend"}
            return {"ok": True, "reason": f"uptrend: spot {spot:.0f} > SMA200 {sma200:.0f}"}
        return {"ok": False, "reason": f"strat sconosciuta: {strat}"}

    # ------------------------------------------------------ margine (#7)
    def _margin_gate(self, new_risk_usd: float, strict: bool = False):
        """Impegno totale (max-loss posizioni aperte + nuovo trade) vs conto
        REALE da /accounts. Il rischio arriva in USD (opzioni $1/pt) e viene
        CONVERTITO nella valuta del conto (verificato sul reale 19 lug 2026:
        TVYYM è in EUR anche se le opzioni quotano USD). Ritorna
        (ok, reason, info). strict=True (percorso ARMATO): se il conto non è
        leggibile → RIFIUTA (fail-closed); in plan-only → warning e avanti."""
        c = self.scfg
        try:
            accounts = self.client.get_accounts()
        except Exception as e:
            accounts = None
            err = str(e)
        else:
            err = None
        bal = avail = ccy = None
        for a in accounts or []:
            if not getattr(self.client, "account_id", None) \
                    or a.get("accountId") == self.client.account_id:
                b = a.get("balance") or {}
                bal = b.get("balance")
                avail = b.get("available", bal)
                ccy = a.get("currency")
                break
        if bal is None:
            msg = f"conto non leggibile da /accounts ({err or 'nessun match'})"
            if strict:
                self.audit.error("margin_gate_REFUSE", reason=msg, strict=True)
                return False, f"MARGINE: {msg} → rifiuto (armato)", {}
            self.audit.warn("margin_gate_unknown", reason=msg)
            return True, None, {"warning": f"margine non verificabile: {msg}"}
        # USD → valuta del conto (usd2eur dichiarato in config; USD = 1:1)
        fx = 1.0 if str(ccy).upper() == "USD" else c.usd2eur
        new_risk = new_risk_usd * fx
        committed = sum((getattr(p, "max_loss", 0) or 0)
                        * (p.legs[0].size if p.legs else 0)
                        for p in self.store.get_open()) * fx
        total_after = committed + new_risk
        info = {"balance": bal, "available": avail, "currency": ccy,
                "committed": round(committed, 0),
                "total_after": round(total_after, 0),
                "cap": round(c.max_account_frac * bal, 0)}
        if total_after > c.max_account_frac * bal:
            self.audit.error("margin_gate_REFUSE", **info)
            return False, (f"MARGINE: impegno {total_after:.0f} {ccy} > "
                           f"{c.max_account_frac:.0%} del conto ({bal:.0f}) — skip"), info
        if new_risk > (avail or bal):
            self.audit.error("margin_gate_REFUSE_available", **info)
            return False, (f"MARGINE: rischio {new_risk:.0f} {ccy} > fondi "
                           f"disponibili ({avail:.0f}) — skip"), info
        self.audit.info("margin_gate_ok", **info)
        return True, None, info

    # -------------------------------------------------------- costruzione
    def _quote(self, code: str, strike: int, kind: str):
        epic = build_epic(code, strike, kind)
        m = self.client.get_market(epic)
        if not m:
            return None
        s = m.get("snapshot", {}) or {}
        b, o = s.get("bid"), s.get("offer")
        if b is None or o is None:
            return None
        return {"epic": epic, "strike": float(strike), "bid": b, "offer": o}

    def plan_spread(self, strat: str, vix_now: float, vix_src: str = "?",
                    vix10max: Optional[float] = None,
                    ts_ratio: Optional[float] = None,
                    sma200: Optional[float] = None,
                    guard: Optional[dict] = None,
                    strict_margin: bool = False) -> dict:
        """guard (opzionale) = decisione della GUARDIA SOFT (src/guard):
        {'level', 'params': {...}, ...}. MODULA strike/size, NON blocca mai.
        strict_margin=True (percorso ARMATO): conto non leggibile → rifiuto."""
        c = self.scfg
        g_ps = (guard or {}).get("params", {}).get("putspread", {})
        g_cs = (guard or {}).get("params", {}).get("callspread", {})
        ps_a = g_ps.get("a", c.ps_short_sig)
        ps_b = g_ps.get("b", c.ps_wing_sig)
        cs_m1 = g_cs.get("m1", c.cs_long_sig)
        cs_m2 = g_cs.get("m2", c.cs_short_sig)
        size_mult = (g_ps if strat == "putspread" else g_cs).get("size_mult", 1.0)
        # gate posizioni (per strategia: il DB è condiviso col condor)
        n_open = len([x for x in self.store.get_open()
                      if getattr(x, "strategy", "condor") == strat])
        if n_open >= c.max_positions_per_strat:
            return {"ok": False, "action": "skip",
                    "reason": f"posizioni aperte {n_open} >= max {c.max_positions_per_strat}"}
        exp = self._pick_expiry()
        if exp is None:
            return {"ok": False, "reason": f"nessuna scadenza standard con DTE in "
                    f"[{c.dte_min},{c.dte_max}]"}
        expiry, dte = exp
        code = self._discover_code(expiry)
        if not code:
            return {"ok": False, "reason": f"codice epic non trovato per {expiry}"}
        spot, spot_src = self._spot_from_monthly(code)
        if spot is None:
            return {"ok": False, "reason": f"spot non disponibile ({spot_src})"}

        sig = self.signal(strat, vix_now, vix10max, ts_ratio, spot, sma200)
        if not sig["ok"]:
            return {"ok": False, "action": "skip", "spot": spot, "vix": vix_now,
                    "reason": sig["reason"]}

        sT = (vix_now / 100.0) * math.sqrt(max(dte, 1) / 365.0)   # mossa implicita
        if strat == "putspread":
            k_short = int(round_strike(spot * (1 - ps_a * sT), 50))
            k_long = int(round_strike(spot * (1 - ps_b * sT), 50))
            if k_long >= k_short:
                k_long = k_short - 50
            q_short = self._quote(code, k_short, "PUT")
            q_long = self._quote(code, k_long, "PUT")
            if not (q_short and q_long):
                return {"ok": False, "reason": "quote mancanti sulle gambe"}
            credit = q_short["bid"] - q_long["offer"]      # vendi al bid, compri all'ask
            width = k_short - k_long
            maxloss = width - credit
            if credit < c.min_credit_pts:
                return {"ok": False, "reason": f"credito reale {credit:.1f}pt < "
                        f"min {c.min_credit_pts} — non vale il rischio"}
            legs_meta = [("long_put_wing", "BUY", "PUT", q_long),
                         ("short_put", "SELL", "PUT", q_short)]
            risk_pts, reward_pts = maxloss, credit
        else:   # callspread
            k_long = int(round_strike(spot * (1 + cs_m1 * sT), 50))
            k_short = int(round_strike(spot * (1 + cs_m2 * sT), 50))
            if k_short <= k_long:
                k_short = k_long + 50
            q_long = self._quote(code, k_long, "CALL")
            q_short = self._quote(code, k_short, "CALL")
            if not (q_short and q_long):
                return {"ok": False, "reason": "quote mancanti sulle gambe"}
            debit = q_long["offer"] - q_short["bid"]       # compri all'ask, vendi al bid
            width = k_short - k_long
            if debit <= 0:
                return {"ok": False, "reason": "debito <= 0: quote sospette"}
            if debit > c.max_debit_frac * width:
                return {"ok": False, "reason": f"debito {debit:.1f}pt > "
                        f"{c.max_debit_frac:.0%} dell'ampiezza {width} — call troppo care ora"}
            legs_meta = [("long_call", "BUY", "CALL", q_long),
                         ("short_call", "SELL", "CALL", q_short)]
            risk_pts, reward_pts = debit, width - debit

        # sizing: contratti interi, 1 ogni eur_per_contract di capitale;
        # la guardia può RIDURRE la size (mai sotto 1: si opera sempre)
        size = max(1, int((c.capital_eur // c.eur_per_contract) * size_mult))
        risk_eur = risk_pts * c.usd2eur * size

        # gate MARGINE (issue #7): impegno vs conto REALE, in valuta del conto
        # ($1/pt → il rischio in punti È il rischio in USD sul conto opzioni)
        new_risk_ccy = risk_pts * size
        m_ok, m_reason, m_info = self._margin_gate(new_risk_ccy,
                                                   strict=strict_margin)
        if not m_ok:
            return {"ok": False, "action": "skip", "reason": m_reason,
                    "margin": m_info}

        legs = [Leg(role=r, epic=q["epic"], direction=d, kind=k,
                    strike=q["strike"], size=size) for r, d, k, q in legs_meta]
        spread = Condor(underlying_epic=self.cfg.underlying_epic, expiry=expiry,
                        entry_spot=spot, entry_vix=vix_now, legs=legs,
                        target_credit=reward_pts if strat == "putspread" else -risk_pts,
                        max_loss=risk_pts)
        spread.strategy = strat
        plan = {"ok": True, "strat": strat, "spread": spread, "expiry": expiry,
                "dte": dte, "code": code, "spot": spot, "spot_src": spot_src,
                "vix": vix_now, "vix_src": vix_src, "signal": sig["reason"],
                "width_pts": width, "risk_pts": round(risk_pts, 1),
                "reward_pts": round(reward_pts, 1), "size": size,
                "risk_eur": round(risk_eur, 0),
                "quotes": {r: {"bid": q["bid"], "offer": q["offer"],
                               "strike": q["strike"]} for r, _, _, q in legs_meta}}
        plan["margin"] = m_info
        if guard:
            plan["guard"] = {"level": guard.get("level"),
                             "eff_score": guard.get("eff_score"),
                             "reasons": guard.get("reasons")}
        self.audit.info("spread_plan", strat=strat, desc=spread.describe(),
                        risk_pts=plan["risk_pts"], reward_pts=plan["reward_pts"],
                        size=size, risk_eur=plan["risk_eur"], signal=sig["reason"],
                        guard=(guard or {}).get("level", "nessuna"))
        return plan

    # ------------------------------------------------------------- run
    def run_spread(self, strat: str, armed: bool = False,
                   guard: Optional[dict] = None, **signals) -> dict:
        # armato → margine STRICT (conto non leggibile = rifiuto, fail-closed)
        plan = self.plan_spread(strat, guard=guard, strict_margin=armed,
                                **signals)
        if not plan.get("ok"):
            self.audit.info("spread_skip", strat=strat, reason=plan.get("reason"))
            return plan
        if not armed:
            plan["action"] = "PLAN_ONLY (nessun ordine inviato)"
            return plan
        spread = plan["spread"]
        self.audit.warn("ARMED_spread_open", strat=strat, desc=spread.describe())
        res = self.executor.open_condor(spread)     # longs-first: prima la comprata
        cid = self.store.record(spread)
        plan["opened"] = res.get("ok")
        plan["store_id"] = cid
        plan["exec"] = res
        return plan
