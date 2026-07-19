"""
Strutture dati per spread / multi-leg opzioni (generico, N gambe).

Usato dal path vivo putspread / callspread (e, in legacy, iron condor 4 gambe).
Nessuna logica di rete: solo descrizione della struttura e ordine di apertura
sicuro (LONG prima, SHORT dopo).

Naming: OptionSpread (non "Condor") — issue #16. Alias retrocompat in condor.py.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Leg:
    role: str              # es. long_put | short_put | long_put_wing | ...
    epic: str
    direction: str         # BUY (long) | SELL (short)
    kind: str              # PUT | CALL
    strike: float
    size: float
    status: str = "PENDING"        # PENDING | OPEN | CLOSED | FAILED
    deal_id: Optional[str] = None
    fill_level: Optional[float] = None
    reason: Optional[str] = None

    @property
    def is_long(self) -> bool:
        return self.direction.upper() == "BUY"


@dataclass
class OptionSpread:
    """Struttura multi-gamba generica (2+ legs). strategy = putspread|callspread|…"""
    underlying_epic: str
    expiry: str
    entry_spot: float
    entry_vix: float
    legs: List[Leg] = field(default_factory=list)
    target_credit: float = 0.0
    max_loss: float = 0.0
    status: str = "PLANNED"
    deal_ref_group: Optional[str] = None
    opened_ts: Optional[str] = None
    strategy: Optional[str] = None

    def open_order(self) -> List[Leg]:
        """APERTURA: prima LONG (protezione), poi SHORT."""
        longs = [l for l in self.legs if l.is_long]
        shorts = [l for l in self.legs if not l.is_long]
        return longs + shorts

    def close_order(self) -> List[Leg]:
        """CHIUSURA: prima SHORT (togli rischio), poi LONG."""
        longs = [l for l in self.legs if l.is_long]
        shorts = [l for l in self.legs if not l.is_long]
        return shorts + longs

    def open_legs(self) -> List[Leg]:
        return [l for l in self.legs if l.status == "OPEN"]

    def by_role(self, role: str) -> Optional[Leg]:
        for l in self.legs:
            if l.role == role:
                return l
        return None

    def describe(self) -> str:
        parts = []
        for l in self.open_order():
            parts.append(f"{l.role}[{l.direction} {l.kind} {l.strike:.0f} x{l.size}]")
        tag = self.strategy or "spread"
        return (f"Spread[{tag}] {self.expiry} spot={self.entry_spot:.0f} "
                f"vix={self.entry_vix:.1f} credit~{self.target_credit:.1f} "
                f"maxloss~{self.max_loss:.1f} | " + " ".join(parts))


# Ordine classico iron-condor 4 gambe (solo builder legacy)
ROLES_ORDER_IRON = ["long_put_wing", "long_call_wing", "short_put", "short_call"]


def build_spread(underlying_epic: str, expiry: str, spot: float, vix: float,
                 legs: List[Leg], target_credit: float = 0.0,
                 max_loss: float = 0.0,
                 strategy: Optional[str] = None) -> OptionSpread:
    """Factory generica: passa già le Leg costruite."""
    return OptionSpread(
        underlying_epic=underlying_epic, expiry=expiry, entry_spot=spot,
        entry_vix=vix, legs=list(legs), target_credit=target_credit,
        max_loss=max_loss, strategy=strategy)


def build_iron_condor(underlying_epic: str, expiry: str, spot: float, vix: float,
                      epics: dict, size: float, target_credit: float = 0.0,
                      max_loss: float = 0.0) -> OptionSpread:
    """Builder 4 gambe (legacy iron condor / test). Preferire build_spread sul path vivo."""
    role_meta = {
        "long_put_wing":  ("BUY", "PUT"),
        "short_put":      ("SELL", "PUT"),
        "short_call":     ("SELL", "CALL"),
        "long_call_wing": ("BUY", "CALL"),
    }
    legs = []
    for role in ROLES_ORDER_IRON:
        if role not in epics:
            raise ValueError(f"manca l'epic per la gamba '{role}'")
        direction, kind = role_meta[role]
        legs.append(Leg(role=role, epic=epics[role]["epic"], direction=direction,
                        kind=kind, strike=float(epics[role]["strike"]), size=size))
    return OptionSpread(
        underlying_epic=underlying_epic, expiry=expiry, entry_spot=spot,
        entry_vix=vix, legs=legs, target_credit=target_credit, max_loss=max_loss,
        strategy="condor")


# Alias storico del builder 4-gamba
build_condor = build_iron_condor
ROLES_ORDER = ROLES_ORDER_IRON
Condor = OptionSpread  # issue #16 retrocompat
