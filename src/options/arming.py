"""
Policy di armamento per-strategia (modulare).

Il gate globale (--arm + --live + --i-understand-live-risk, o env demone)
apre la possibilità di inviare ordini. QUALI strategie possono davvero aprire
lo decide un allowlist da config/CLI — nessuna strategia è hardcodata come
"quella buona" nel demone o nell'orchestratore.

Default sicuro: allowlist VUOTA → anche con --arm, nessun ordine
(plan-only totale finché non elenchi esplicitamente le strategie).

Esempi:
  OPTIONS_ARMED_STRATEGIES=putspread
  OPTIONS_ARMED_STRATEGIES=putspread,callspread
  CLI: --arm-strategies putspread
"""
from __future__ import annotations

import os
from typing import Iterable, Optional, Set

# Nomi noti degli edge opzioni a 2 gambe. Aggiungerne uno = qui + orchestrator.
KNOWN_OPTION_STRATEGIES = frozenset({"putspread", "callspread"})
ENV_ARMED = "OPTIONS_ARMED_STRATEGIES"


def parse_strategy_list(raw: Optional[str]) -> Set[str]:
    """Parse 'a,b,c' → set normalizzato. Ignota vuoti e sconosciuti (log a parte)."""
    if not raw:
        return set()
    out: Set[str] = set()
    unknown: Set[str] = set()
    for part in str(raw).replace(";", ",").split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name in KNOWN_OPTION_STRATEGIES:
            out.add(name)
        else:
            unknown.add(name)
    return out


def unknown_in(raw: Optional[str]) -> Set[str]:
    if not raw:
        return set()
    found: Set[str] = set()
    for part in str(raw).replace(";", ",").split(","):
        name = part.strip().lower()
        if name and name not in KNOWN_OPTION_STRATEGIES:
            found.add(name)
    return found


def resolve_armed_allowlist(cli_value: Optional[str] = None,
                            env: Optional[dict] = None) -> Set[str]:
    """CLI `--arm-strategies` vince su env `OPTIONS_ARMED_STRATEGIES`."""
    env = env or os.environ
    if cli_value is not None and str(cli_value).strip() != "":
        return parse_strategy_list(cli_value)
    return parse_strategy_list(env.get(ENV_ARMED, ""))


def is_strategy_armed(strategy: str, *, gate_open: bool,
                      allowlist: Iterable[str]) -> bool:
    """True solo se il gate globale è aperto E la strategia è in allowlist."""
    if not gate_open:
        return False
    return strategy.strip().lower() in set(allowlist)
