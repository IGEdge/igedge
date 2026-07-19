"""
Shim di compatibilità (issue #16).

Il modello generico vive in `spread.py` (`OptionSpread`). Questo modulo espone
ancora i vecchi nomi `Condor` / `build_condor` così il legacy (`run_condor`,
test iron) non si rompe. Codice nuovo: importare da `src.options.spread`.
"""
from .spread import (  # noqa: F401
    Leg,
    OptionSpread,
    ROLES_ORDER,
    ROLES_ORDER_IRON,
    build_condor,
    build_iron_condor,
    build_spread,
)

# Alias storico
Condor = OptionSpread

__all__ = [
    "Leg", "OptionSpread", "Condor",
    "build_spread", "build_iron_condor", "build_condor",
    "ROLES_ORDER", "ROLES_ORDER_IRON",
]
