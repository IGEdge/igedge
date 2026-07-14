"""
Orchestrator — la colla dell'EDGE #2 (short-vol condor) sul live.

Un ciclo:
  1. Stato mercato: spot (sottostante) + VIX (→ iv).
  2. Gate SEGNALE: VIX ∈ [vix_min, vix_max] (banda §4b), altrimenti skip.
  3. Gate POSIZIONI: sotto il max di condor aperti.
  4. Scadenza: la mensile con DTE nella finestra voluta.
  5. Catena: risolvi i 4 epic (frugale, chain_resolver).
  6. Quote reali dei 4 leg (get_market) → credito NETTO e max perdita reali.
  7. Gate RISCHIO: sizing (1 contratto su capitale piccolo) + credito minimo.
  8. DEFAULT plan-only: mostra/logga il condor che APRIREBBE, NON apre.
     Con armed=True (+ conto live + ok esplicito): preflight → executor → store.

Anti rate-limit: il client è ThrottledClient (intervallo minimo tra chiamate) e la
catena si risolve con poche search + get_market solo sui 4 leg scelti.
"""
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from scipy.stats import norm

from .audit_log import AuditLog
from .chain_resolver import (build_epic, expiry_code, list_expiries,
                             list_option_epics, resolve_condor_epics_direct,
                             round_strike)
from .condor import build_condor
from .monitor import parse_expiry, upcoming_standard_expiries


def _bs(S, K, T, sig, kind):
    if T <= 0 or sig <= 0:
        return max(K - S, 0.0) if kind == "PUT" else max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sig ** 2 * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    if kind == "PUT":
        return K * norm.cdf(-d2) - S * norm.cdf(-d1)
    return S * norm.cdf(d1) - K * norm.cdf(d2)


def _implied_vol(price, S, K, T, kind):
    """IV per bisezione (robusta) dal prezzo dell'opzione. None se non invertibile."""
    if price is None or price <= 0 or T <= 0:
        return None
    lo, hi = 0.01, 3.0
    if _bs(S, K, T, hi, kind) < price:      # prezzo oltre il massimo modellabile
        return None
    for _ in range(64):
        mid = (lo + hi) / 2
        if _bs(S, K, T, mid, kind) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


@dataclass
class OrchConfig:
    underlying_epic: str = "IX.D.SPTRD.IFE.IP"
    a: float = 1.0
    b: float = 2.0
    vix_min: float = 14.0
    vix_max: float = 30.0
    dte_min: int = 20
    dte_max: int = 45
    capital: float = 1000.0
    risk_frac: float = 0.10
    value_per_point: float = 1.0
    max_positions: int = 1
    min_credit_pts: float = 5.0
    currency: str = "USD"


class Orchestrator:
    def __init__(self, client, store, executor, audit: AuditLog = None,
                 config: OrchConfig = None):
        self.client = client
        self.store = store
        self.executor = executor
        self.audit = audit or AuditLog(dry_run=not getattr(executor, "live", False))
        self.cfg = config or OrchConfig()
        self._cache = {}                    # cache epic per scadenza (anti rate-limit)

    # ------------------------------------------------------------------
    def _mid(self, epic):
        m = self.client.get_market(epic)
        if not m:
            return None, None, None
        s = m.get("snapshot", {}) or {}
        b, o = s.get("bid"), s.get("offer")
        mid = (b + o) / 2.0 if (b is not None and o is not None) else None
        return b, o, mid

    def _fetch_vix(self, override=None):
        if override is not None:
            return float(override), "override"
        # fallback: ultimo VIX in cache CSV (per il live serve il valore corrente;
        # qui restiamo prudenti e usiamo l'ultimo noto, marcandolo).
        try:
            import pandas as pd
            df = pd.read_csv("data/research/vix_daily.csv")
            return float(df["close"].iloc[-1]), f"csv:{df['ts'].iloc[-1]}"
        except Exception:
            return None, "unavailable"

    def _chain_atm_iv(self, chain, spot, dte):
        """IV corrente ricavata dalla CATENA (autonoma): opzione con strike più
        vicino a spot → mid → inversione BS. È la vol che il bot usa ogni ciclo
        senza dipendere da input esterni. Ritorna (iv, sorgente) o (None, motivo)."""
        if not chain or spot is None:
            return None, "no_chain"
        atm = min(chain, key=lambda m: abs(m["strike"] - spot))
        _, _, mid = self._mid(atm["epic"])
        if mid is None:
            return None, "no_atm_quote"
        iv = _implied_vol(mid, spot, atm["strike"], max(dte, 1) / 365.0, atm["kind"])
        if iv is None:
            return None, "iv_inversion_failed"
        return iv, f"atm_iv:{atm['kind']}{atm['strike']:.0f}"

    def _spot_via_parity(self):
        """Spot dalla scadenza con la griglia strike PIÙ COMPLETA (tipicamente la
        weekly, che la search restituisce intera) via put-call parity S ≈ K+C−P.
        Il sottostante USD non quota, ma le opzioni sì."""
        allm = list_option_epics(self.client, cache=self._cache)
        by_exp = {}
        for m in allm:
            d = by_exp.setdefault(m["expiry"], {"C": {}, "P": {}})
            d["C" if m["kind"] == "CALL" else "P"][m["strike"]] = m["epic"]
        best = None
        for exp, d in by_exp.items():
            common = set(d["C"]) & set(d["P"])
            if best is None or len(common) > len(best[1]):
                best = (exp, common, d)
        if not best or len(best[1]) < 3:
            return None, "no_full_grid"
        exp, common, d = best
        k = sorted(common)[len(common) // 2]
        _, _, c = self._mid(d["C"][k])
        _, _, p = self._mid(d["P"][k])
        if c is None or p is None:
            return None, "no_parity_quotes"
        return k + (c - p), f"parity@{exp}:{k:.0f}"

    def _atm_iv_construct(self, code, spot, dte):
        """IV ATM costruendo l'opzione ATM della scadenza target e invertendo BS."""
        strike = round_strike(spot, 50)
        for kind in ("PUT", "CALL"):
            _, _, mid = self._mid(build_epic(code, strike, kind))
            if mid:
                iv = _implied_vol(mid, spot, strike, max(dte, 1) / 365.0, kind)
                if iv:
                    return iv, f"atm_iv:{kind}{strike}"
        return None, "no_atm_quote"

    def _pick_expiry(self):
        """Scadenza STANDARD (3° venerdì) più vicina a ~30gg nella finestra —
        CALCOLATA (niente search, che su IG tronca). MAI le fine-mese né weekly."""
        today = datetime.now(timezone.utc).date()
        best = None
        for exp_str, d in upcoming_standard_expiries():
            dte = (d - today).days
            if self.cfg.dte_min <= dte <= self.cfg.dte_max:
                if best is None or abs(dte - 30) < abs(best[1] - 30):
                    best = (exp_str, dte)
        return best        # (expiry_str 'MON-YY', dte) o None

    # candidati codici epic delle scadenze standard IG (OTCSPX1..5); si scopre
    # quale corrisponde alla scadenza target leggendo la expiry da get_market.
    _STD_CODES = ["OTCSPX1", "OTCSPX2", "OTCSPX3", "OTCSPX4", "OTCSPX5"]

    def _discover_code(self, expiry_str, boot_strike=7500):
        """Trova il CODICE epic della scadenza target sondando get_market su pochi
        codici candidati e leggendo la loro `expiry`. Robusto: non usa la search."""
        target = parse_expiry(expiry_str)
        if target is None:
            return None
        for code in self._STD_CODES:
            m = self.client.get_market(build_epic(code, boot_strike, "PUT"))
            if not m:
                continue
            e = (m.get("instrument", {}) or {}).get("expiry")
            d = parse_expiry(e) if e else None
            # deve combaciare col 3° venerdì target ED essere standard (MON-YY)
            if d and len(str(e).split("-")) == 2 and d.date() == target.date():
                return code
        return None

    def _spot_from_monthly(self, code, boot=7500):
        """Spot dalla scadenza target via put-call parity S ≈ K + C − P (r≈0),
        costruendo call+put a uno strike noto. Niente sottostante, niente search."""
        _, _, c = self._mid(build_epic(code, boot, "CALL"))
        _, _, p = self._mid(build_epic(code, boot, "PUT"))
        if c is None or p is None:
            return None, "no_parity_quotes"
        return boot + (c - p), f"parity@{boot}"

    # ------------------------------------------------------------------
    def plan(self, vix_override=None):
        """Calcola il condor che si APRIREBBE ora. Non apre nulla."""
        cfg = self.cfg
        # gate posizioni (subito, prima di scaricare la catena)
        n_open = len(self.store.get_open())
        if n_open >= cfg.max_positions:
            return {"ok": False, "action": "skip",
                    "reason": f"max posizioni raggiunto ({n_open}/{cfg.max_positions})"}
        # scadenza
        exp = self._pick_expiry()
        if exp is None:
            return {"ok": False, "reason": f"nessuna scadenza con DTE in "
                    f"[{cfg.dte_min},{cfg.dte_max}]"}
        expiry, dte = exp

        # CODICE della scadenza standard target — scoperto via get_market (no search)
        code = self._discover_code(expiry)
        if not code:
            return {"ok": False, "reason": f"codice non trovato per scadenza standard {expiry}"}
        # SPOT dalla mensile via parità (il sottostante USD non quota)
        spot, spot_src = self._spot_from_monthly(code)
        if spot is None:
            return {"ok": False, "reason": f"spot non disponibile ({spot_src})"}

        # VOLATILITÀ AUTONOMA: IV ATM dell'opzione ATM costruita (self-consistent)
        iv, iv_src = self._atm_iv_construct(code, spot, dte)
        if vix_override is not None:            # override esplicito ha precedenza
            iv, iv_src = vix_override / 100.0, "override"
        if iv is None:
            return {"ok": False, "reason": f"IV non disponibile ({iv_src})"}
        vix = iv * 100.0

        # gate segnale (banda VIX ≈ IV ATM)
        if not (cfg.vix_min <= vix <= cfg.vix_max):
            return {"ok": False, "action": "skip", "spot": spot, "vix": vix,
                    "reason": f"VIX≈{vix:.1f} fuori banda [{cfg.vix_min},{cfg.vix_max}]"}

        # COSTRUZIONE DIRETTA dei 4 epic (verificati con get_market, quote incluse)
        res = resolve_condor_epics_direct(self.client, code, spot, iv, dte, cfg.a, cfg.b)
        if not res["ok"]:
            return {"ok": False, "reason": f"catena: {res['reason']}"}
        epics = res["epics"]
        # credito reale dalle quote: vendi short al BID, compra ali all'ASK
        credit = (epics["short_put"]["bid"] + epics["short_call"]["bid"]
                  - epics["long_put_wing"]["offer"] - epics["long_call_wing"]["offer"])
        width = max(epics["short_put"]["strike"] - epics["long_put_wing"]["strike"],
                    epics["long_call_wing"]["strike"] - epics["short_call"]["strike"])
        max_loss = width - credit
        if credit < cfg.min_credit_pts:
            return {"ok": False, "reason": f"credito reale {credit:.1f}pt < minimo "
                    f"{cfg.min_credit_pts} (skew/spread) — non vale il rischio"}
        q = {r: {"bid": epics[r]["bid"], "offer": epics[r]["offer"]} for r in epics}

        # sizing (gate rischio)
        risk_budget = cfg.capital * cfg.risk_frac
        maxloss_ccy = max_loss * cfg.value_per_point
        size = max(1, int(math.floor(risk_budget / maxloss_ccy))) if maxloss_ccy > 0 else 1
        risk_pct = maxloss_ccy * size / cfg.capital * 100
        warn = None
        if maxloss_ccy > risk_budget:
            warn = (f"1 contratto rischia {maxloss_ccy:.0f} = {risk_pct:.0f}% del capitale "
                    f"(> {cfg.risk_frac:.0%} target). OK per test, size forzata a 1.")

        condor = build_condor(cfg.underlying_epic, expiry, spot, vix, epics,
                              size=size, target_credit=credit, max_loss=max_loss)
        plan = {"ok": True, "condor": condor, "spot": spot, "spot_src": spot_src,
                "vix": vix, "vix_src": iv_src, "dte": dte, "expiry": expiry,
                "credit_pts": round(credit, 1), "maxloss_pts": round(max_loss, 1),
                "size": size, "risk_ccy": round(maxloss_ccy * size, 0),
                "risk_pct": round(risk_pct, 0), "targets": res["targets"],
                "sigma_pts": res["sigma_pts"], "warn": warn, "quotes": q}
        self.audit.info("plan", desc=condor.describe(), spot=spot, vix=vix,
                        dte=dte, credit=round(credit, 1), maxloss=round(max_loss, 1),
                        size=size, risk_pct=round(risk_pct, 0), warn=warn)
        return plan

    # ------------------------------------------------------------------
    def run_once(self, armed: bool = False, vix_override=None):
        """Un ciclo. armed=False (default) = plan-only, NON apre. armed=True apre
        davvero (richiede conto live + ok esplicito a monte)."""
        plan = self.plan(vix_override=vix_override)
        if not plan.get("ok"):
            self.audit.info("run_skip", reason=plan.get("reason"),
                            plan_action=plan.get("action"))
            return plan
        if not armed:
            plan["action"] = "PLAN_ONLY (nessun ordine inviato)"
            return plan
        # ARMATO: apri davvero
        condor = plan["condor"]
        self.audit.warn("ARMED_open_start", desc=condor.describe())
        res = self.executor.open_condor(condor)
        cid = self.store.record(condor)      # registra sempre lo stato (anche parziale)
        plan["opened"] = res.get("ok")
        plan["store_id"] = cid
        plan["exec"] = res
        return plan
