"""
Strutture dati dell'iron condor (EDGE #2). Nessuna logica di rete qui — solo la
descrizione della struttura e delle 4 gambe, con l'ORDINE DI APERTURA sicuro.

Iron condor = 4 gambe:
  - long_put_wing   (BUY  put a 2σ)  ← protezione
  - short_put       (SELL put a 1σ)  ← rischio
  - short_call      (SELL call a 1σ) ← rischio
  - long_call_wing  (BUY  call a 2σ) ← protezione

Regola di sicurezza (executor.py): si aprono PRIMA le 2 gambe LONG (protezione),
POI le 2 SHORT. Così non si è mai short senza la protezione già a mercato.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Leg:
    role: str              # long_put_wing | short_put | short_call | long_call_wing
    epic: str
    direction: str         # BUY (long) | SELL (short)
    kind: str              # PUT | CALL
    strike: float
    size: float
    # stato dopo l'apertura:
    status: str = "PENDING"        # PENDING | OPEN | CLOSED | FAILED
    deal_id: Optional[str] = None
    fill_level: Optional[float] = None
    reason: Optional[str] = None    # motivo se FAILED

    @property
    def is_long(self) -> bool:
        return self.direction.upper() == "BUY"


@dataclass
class Condor:
    underlying_epic: str            # epic del sottostante (per il monitoraggio)
    expiry: str                     # es. "31-AUG-26"
    entry_spot: float               # sottostante all'ingresso
    entry_vix: float
    legs: List[Leg] = field(default_factory=list)
    # economia attesa (dal modello / dalle quote):
    target_credit: float = 0.0      # credito atteso (punti)
    max_loss: float = 0.0           # perdita massima (punti) = ampiezza − credito
    # runtime:
    status: str = "PLANNED"         # PLANNED | OPEN | ABORTED | CLOSED | PARTIAL_ERROR
    deal_ref_group: Optional[str] = None   # id logico dell'intera struttura
    opened_ts: Optional[str] = None

    # --- ordinamenti sicuri --------------------------------------------------
    def open_order(self) -> List[Leg]:
        """Ordine di APERTURA: prima le LONG (protezione), poi le SHORT."""
        longs = [l for l in self.legs if l.is_long]
        shorts = [l for l in self.legs if not l.is_long]
        return longs + shorts

    def close_order(self) -> List[Leg]:
        """Ordine di CHIUSURA (normale, a scadenza o manuale): prima chiudi le
        SHORT (togli il rischio), poi le LONG. È l'inverso dell'apertura."""
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
        return f"Condor {self.expiry} spot={self.entry_spot:.0f} vix={self.entry_vix:.1f} " \
               f"credit~{self.target_credit:.1f} maxloss~{self.max_loss:.1f} | " + " ".join(parts)


ROLES_ORDER = ["long_put_wing", "long_call_wing", "short_put", "short_call"]


def build_condor(underlying_epic: str, expiry: str, spot: float, vix: float,
                 epics: dict, size: float, target_credit: float = 0.0,
                 max_loss: float = 0.0) -> Condor:
    """Costruisce un Condor dai 4 epic (dict role->{epic,strike}).

    epics = {
      'long_put_wing':  {'epic':..., 'strike':...},
      'short_put':      {'epic':..., 'strike':...},
      'short_call':     {'epic':..., 'strike':...},
      'long_call_wing': {'epic':..., 'strike':...},
    }
    """
    role_meta = {
        "long_put_wing":  ("BUY", "PUT"),
        "short_put":      ("SELL", "PUT"),
        "short_call":     ("SELL", "CALL"),
        "long_call_wing": ("BUY", "CALL"),
    }
    legs = []
    for role in ROLES_ORDER:
        if role not in epics:
            raise ValueError(f"manca l'epic per la gamba '{role}'")
        direction, kind = role_meta[role]
        legs.append(Leg(role=role, epic=epics[role]["epic"], direction=direction,
                        kind=kind, strike=float(epics[role]["strike"]), size=size))
    return Condor(underlying_epic=underlying_epic, expiry=expiry, entry_spot=spot,
                  entry_vix=vix, legs=legs, target_credit=target_credit,
                  max_loss=max_loss)
