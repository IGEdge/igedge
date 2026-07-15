"""
GUARDIA SOFT — integrazione del Gamma-Regime-Divergence-Scanner (repo dell'utente)
come contesto di mercato per gli edge opzioni.

PRINCIPI INVIOLABILI (decisi dall'utente, 14 lug 2026):
  1. La guardia MODULA, NON BLOCCA MAI: si opera ogni mese; nei regimi brutti si
     passa a strutture più difensive ("regimi più larghi") e/o size ridotta —
     mai a zero. Vietato "aspettare il crollo" per mesi/anni.
  2. Il codice dello scanner è la FONTE: qui si LEGGE il suo output
     (data/cache/market_state_spy.json, prodotto dal suo cron giornaliero).
     L'eventuale refresh usa il SUO run_engine (il suo ingestion Yahoo con
     cache/anti-ban) — MAI fetch nostri verso Yahoo.
  3. Fallback NEUTRO: se lo scanner non c'è / è stantio, la guardia risponde
     NORMALE (nessuna modulazione) + warning. Un guasto della guardia non deve
     mai fermare il trading system.

Uso:
    g = read_guard_state()           # stato dallo scanner (o neutro)
    d = decide(g)                    # livello + parametri modulati per gli edge
"""
import json
import os
import subprocess
import sys
from datetime import datetime

from .seasonality import month_bias

# dove sta il repo dello scanner: env GAMMA_SCANNER_DIR, altrimenti cartella
# sorella del repo igedge (layout standard sia sul PC che sul Raspberry)
_DEF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "..", "Gamma-Regime-Divergence-Scanner")

GUARD_LEVELS = ("NORMALE", "PRUDENTE", "DIFENSIVO")

# parametri per livello — v1 PRUDENTE-DI-DEFAULT, da CALIBRARE col backtest:
# la modulazione allarga gli strike e riduce la size, MAI a zero (min 1 contratto)
MODULATION = {
    "NORMALE":   {"putspread": {"a": 1.5, "b": 2.5, "size_mult": 1.0},
                  "callspread": {"m1": 0.0, "m2": 1.0, "size_mult": 1.0}},
    "PRUDENTE":  {"putspread": {"a": 2.0, "b": 3.0, "size_mult": 1.0},
                  "callspread": {"m1": 0.5, "m2": 1.5, "size_mult": 1.0}},
    "DIFENSIVO": {"putspread": {"a": 2.0, "b": 3.0, "size_mult": 0.5},
                  "callspread": {"m1": 0.5, "m2": 1.5, "size_mult": 0.5}},
}


def scanner_dir():
    return os.path.normpath(os.getenv("GAMMA_SCANNER_DIR", _DEF))


def read_guard_state(asset: str = "spy", max_age_days: int = 7) -> dict:
    """Legge market_state_<asset>.json prodotto dallo scanner. Mai eccezioni:
    qualunque problema → stato NEUTRO con warning dentro."""
    base = scanner_dir()
    neutral = {"available": False, "risk_score": None, "regime": None,
               "stress_index": None, "prob_drop_5": None, "age_days": None,
               "warning": None, "source": None}
    for name in (f"market_state_{asset}.json", "market_state.json"):
        path = os.path.join(base, "data", "cache", name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            regime_raw = str(st.get("regime", ""))
            regime = next((r for r in ("STABLE", "SQUEEZE", "DISTRIBUTION",
                                       "UNWIND", "TRANSITION") if r in regime_raw),
                          "UNKNOWN")
            age = None
            lu = st.get("last_update")
            if lu:
                try:
                    age = (datetime.now()
                           - datetime.strptime(lu[:19], "%Y-%m-%d %H:%M:%S")).days
                except ValueError:
                    age = None
            out = {"available": True, "source": path,
                   "risk_score": st.get("risk_score"),
                   "regime": regime, "regime_raw": regime_raw,
                   "stress_index": st.get("stress_index"),
                   "prob_drop_5": st.get("probability_drop_5"),
                   "age_days": age, "warning": None}
            if age is not None and age > max_age_days:
                out["warning"] = (f"stato scanner VECCHIO di {age}gg → guardia "
                                  f"NEUTRA (aggiorna lo scanner sul Pi)")
                out["available"] = False
            return out
        except Exception as e:
            neutral["warning"] = f"lettura stato scanner fallita: {e}"
            return neutral
    neutral["warning"] = (f"scanner non trovato in {base} (env GAMMA_SCANNER_DIR) "
                          "→ guardia NEUTRA")
    return neutral


def refresh_guard(timeout: int = 900) -> bool:
    """OPZIONALE: invoca il run_engine DELLO SCANNER (il suo ingestion, il suo
    anti-ban). Da usare solo a mano o dove lo scanner non ha già il suo cron."""
    base = scanner_dir()
    eng = os.path.join(base, "engine", "run_engine.py")
    if not os.path.exists(eng):
        return False
    env = dict(os.environ, SKIP_WHALES_UPDATE="1")
    try:
        p = subprocess.run([sys.executable, eng], cwd=base, env=env,
                           capture_output=True, timeout=timeout)
        return p.returncode == 0
    except Exception:
        return False


def decide(state: dict, when: datetime = None) -> dict:
    """Stato scanner + stagionalità → livello di modulazione. SEMPRE si opera."""
    when = when or datetime.now()
    reasons = []
    score = state.get("risk_score") if state.get("available") else None
    if score is None:
        eff = 0
        reasons.append(state.get("warning") or "scanner non disponibile → NEUTRO")
    else:
        eff = float(score)
        reasons.append(f"risk score scanner {score}/100, regime {state.get('regime')}")
        if state.get("regime") == "UNWIND":
            eff += 10
            reasons.append("regime UNWIND: +10")
    bias, note = month_bias(when.month)
    if bias == "debole":
        eff += 10
        reasons.append(f"stagionalità {when:%B}: debole (+10) — {note}")
    elif bias == "forte":
        eff -= 5
        reasons.append(f"stagionalità {when:%B}: forte (−5) — {note}")
    else:
        reasons.append(f"stagionalità {when:%B}: neutra — {note}")

    level = "NORMALE" if eff < 40 else ("PRUDENTE" if eff < 70 else "DIFENSIVO")
    return {"level": level, "eff_score": round(eff, 0), "reasons": reasons,
            "params": MODULATION[level],
            "note": "modulazione SOFT: si opera comunque (mai blocco)"}
