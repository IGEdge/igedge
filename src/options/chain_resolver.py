"""
Risoluzione della catena opzioni US500 in modo FRUGALE (anti rate-limit).

Trova i 4 epic del condor SENZA interrogare get_market su tutta la catena: usa
poche `search_markets` (che tornano molti epic in una volta) e parsa lo strike +
tipo dagli EPIC (es. OP.D.OTCSPXEMO.5000P.IP → 5000 PUT). Poi il chiamante farà
get_market SOLO sui 4 epic scelti.

Passi:
  1. list_option_epics(): elenco {epic, strike, kind, expiry} per una scadenza.
  2. resolve_condor_epics(): dati spot/iv/dte/a/b, calcola i 4 strike target
     (1σ/2σ) e sceglie gli strike DISPONIBILI più vicini → 4 epic per il condor.
"""
import math
import re
from typing import Dict, List, Optional

# strike+tipo dall'epic: ...<numero><C|P>.IP   (es. 5000P, 7260.0C)
_EPIC_STRIKE = re.compile(r"\.(\d+(?:\.\d+)?)([CP])\.[A-Z]+$")
_SEARCH_TERMS = ["US 500", "US 500 Options", "Daily US 500", "US 500 Monthly",
                 "Monthly US 500", "US 500 Weekly", "S&P 500 Options"]


def _parse_strike_kind(epic: str, name: str):
    """(strike, 'PUT'|'CALL') dall'epic (preferito) o dal nome. None se non parsabile."""
    m = _EPIC_STRIKE.search(epic or "")
    if m:
        return float(m.group(1)), ("PUT" if m.group(2) == "P" else "CALL")
    up = (name or "").upper()
    kind = "PUT" if "PUT" in up else ("CALL" if "CALL" in up else None)
    strike = None
    for tok in (name or "").replace("(", " ").replace(")", " ").split():
        try:
            v = float(tok)
            if 500 < v < 30000:
                strike = v; break
        except ValueError:
            continue
    if strike is not None and kind:
        return strike, kind
    return None


def list_option_epics(client, expiry: Optional[str] = None,
                      cache: Optional[dict] = None) -> List[Dict]:
    """Elenco opzioni US500 [{epic,strike,kind,expiry,name}], filtrato per scadenza
    se data. `cache` (dict) opzionale: se contiene la chiave 'all', la riusa (gli
    epic di una scadenza non cambiano nella sua vita → risparmia search)."""
    if cache is not None and "all" in cache:
        markets = cache["all"]
    else:
        seen, markets = set(), []
        for term in _SEARCH_TERMS:
            for m in client.search_markets(term):
                epic = m.get("epic")
                if not epic or epic in seen:
                    continue
                it = str(m.get("instrumentType", "")).upper()
                nm = str(m.get("instrumentName", ""))
                if "OPT" not in it and "CALL" not in nm.upper() and "PUT" not in nm.upper():
                    continue
                sk = _parse_strike_kind(epic, nm)
                if sk is None:
                    continue
                seen.add(epic)
                markets.append({"epic": epic, "strike": sk[0], "kind": sk[1],
                                "expiry": m.get("expiry"), "name": nm})
        if cache is not None:
            cache["all"] = markets
    if expiry:
        markets = [m for m in markets if str(m.get("expiry")) == str(expiry)]
    return markets


def list_expiries(client, cache: Optional[dict] = None) -> List[str]:
    """Scadenze disponibili (per scegliere la mensile giusta)."""
    seen = {}
    for m in list_option_epics(client, cache=cache):
        seen[m["expiry"]] = seen.get(m["expiry"], 0) + 1
    return sorted(seen, key=lambda e: (seen[e]), reverse=True)


def expiry_code(client, expiry: str, cache: Optional[dict] = None) -> Optional[str]:
    """Codice epic di una scadenza (es. 'OTCSPXEMO' per la mensile) da un campione
    di search. Basta UN epic di quella scadenza (la search lo dà anche se tronca
    la griglia strike). Ritorna il codice o None."""
    for m in list_option_epics(client, expiry=expiry, cache=cache):
        parts = m["epic"].split(".")
        if len(parts) >= 3:
            return parts[2]
    return None


def build_epic(code: str, strike: float, kind: str) -> str:
    """Costruisce l'epic opzione: OP.D.<code>.<strike><P|C>.IP."""
    return f"OP.D.{code}.{int(round(strike))}{'P' if kind == 'PUT' else 'C'}.IP"


def round_strike(x: float, gran: int = 50) -> int:
    return int(round(x / gran) * gran)


def resolve_condor_epics_direct(client, code: str, spot: float, iv: float, dte: int,
                                a: float = 1.0, b: float = 2.0, gran: int = 50):
    """Costruisce i 4 epic del condor dagli strike target (1σ/2σ) e li VERIFICA con
    get_market (con nudge ±gran se un epic non quota). Ritorna quote incluse.
    NON usa la search della catena (che tronca) né la navigation (404)."""
    import math as _m
    sT = iv * _m.sqrt(max(dte, 1) / 365.0)
    targets = {
        "long_put_wing":  ("PUT",  spot * (1 - b * sT)),
        "short_put":      ("PUT",  spot * (1 - a * sT)),
        "short_call":     ("CALL", spot * (1 + a * sT)),
        "long_call_wing": ("CALL", spot * (1 + b * sT)),
    }

    def _quote(epic):
        m = client.get_market(epic)
        if not m:
            return None
        s = m.get("snapshot", {}) or {}
        b_, o_ = s.get("bid"), s.get("offer")
        if b_ is None or o_ is None or (s.get("marketStatus") != "TRADEABLE"):
            return None
        return {"bid": b_, "offer": o_}

    epics = {}
    for role, (kind, tgt) in targets.items():
        base = round_strike(tgt, gran)
        found = None
        for nudge in (0, gran, -gran, 2 * gran, -2 * gran):   # prova near, poi ±
            strike = base + nudge
            epic = build_epic(code, strike, kind)
            q = _quote(epic)
            if q:
                found = {"epic": epic, "strike": strike, **q}
                break
        if not found:
            return {"ok": False, "reason": f"nessun epic quotato per {role} (~{base})"}
        epics[role] = found

    kp2, kp1 = epics["long_put_wing"]["strike"], epics["short_put"]["strike"]
    kc1, kc2 = epics["short_call"]["strike"], epics["long_call_wing"]["strike"]
    if not (kp2 < kp1 < spot < kc1 < kc2):
        return {"ok": False, "reason": f"strike non ordinati {kp2}<{kp1}<{spot:.0f}<{kc1}<{kc2}"}
    if len({kp2, kp1, kc1, kc2}) < 4:
        return {"ok": False, "reason": "strike coincidenti"}
    return {"ok": True, "epics": epics, "sigma_pts": round(spot * sT, 1),
            "targets": {r: round(t[1], 1) for r, t in targets.items()}}


def _nearest(avail: List[Dict], kind: str, target: float) -> Optional[Dict]:
    cand = [m for m in avail if m["kind"] == kind]
    if not cand:
        return None
    return min(cand, key=lambda m: abs(m["strike"] - target))


def resolve_condor_epics(client, expiry: str, spot: float, iv: float, dte: int,
                         a: float = 1.0, b: float = 2.0,
                         cache: Optional[dict] = None) -> Dict:
    """Calcola i 4 strike target (1σ/2σ) e sceglie gli epic disponibili più vicini.

    Ritorna {'ok':True, 'epics': {role:{epic,strike}}, 'targets':{...}} oppure
    {'ok':False, 'reason':...}. NON apre nulla, NON fa get_market."""
    avail = list_option_epics(client, expiry=expiry, cache=cache)
    if len(avail) < 4:
        return {"ok": False, "reason": f"catena scarsa per {expiry} ({len(avail)} epic)"}

    sT = iv * math.sqrt(max(dte, 1) / 365.0)
    targets = {
        "long_put_wing":  ("PUT",  spot * (1 - b * sT)),
        "short_put":      ("PUT",  spot * (1 - a * sT)),
        "short_call":     ("CALL", spot * (1 + a * sT)),
        "long_call_wing": ("CALL", spot * (1 + b * sT)),
    }
    epics, chosen = {}, {}
    for role, (kind, tgt) in targets.items():
        pick = _nearest(avail, kind, tgt)
        if pick is None:
            return {"ok": False, "reason": f"nessuno strike {kind} per {role}"}
        epics[role] = {"epic": pick["epic"], "strike": pick["strike"]}
        chosen[role] = pick["strike"]

    # sanità: ordine corretto e strike distinti
    kp2, kp1 = chosen["long_put_wing"], chosen["short_put"]
    kc1, kc2 = chosen["short_call"], chosen["long_call_wing"]
    if not (kp2 < kp1 < spot < kc1 < kc2):
        return {"ok": False, "reason": f"strike non ordinati: {kp2}<{kp1}<{spot}<{kc1}<{kc2}"}
    if len({kp2, kp1, kc1, kc2}) < 4:
        return {"ok": False, "reason": "strike coincidenti (catena troppo rada)"}

    return {"ok": True, "epics": epics,
            "targets": {r: round(t[1], 1) for r, t in targets.items()},
            "sigma_pts": round(spot * sT, 1)}


# Alias generici (issue #16) — preferire questi nel codice nuovo
resolve_spread_epics = resolve_condor_epics
resolve_spread_epics_direct = resolve_condor_epics_direct
