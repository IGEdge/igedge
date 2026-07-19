"""
Orari di mercato USA (RTH cash: 09:30-16:00 America/New_York, lun-ven).

DST gestito da zoneinfo (issue #12): 15:30 o 14:30 UTC a seconda della stagione,
qui è sempre 09:30 New York. FESTIVITÀ USA non gestite (documentato): in un
festivo il bot vede "RTH" ma IG rifiuta gli ordini e le barre daily sono ferme —
fail-safe accettabile per il demo; da rifinire prima del live CFD.

Tutte le funzioni accettano `now` opzionale (test senza orologio reale).
"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def now_ny(now: datetime = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(NY)


def is_rth(now: datetime = None) -> bool:
    """True se siamo nella sessione cash USA (lun-ven 09:30-16:00 NY)."""
    t = now_ny(now)
    return t.weekday() < 5 and RTH_OPEN <= t.time() < RTH_CLOSE


def minutes_to_close(now: datetime = None):
    """Minuti alla chiusura RTH; None se il mercato è chiuso."""
    t = now_ny(now)
    if not is_rth(t):
        return None
    return (RTH_CLOSE.hour * 60 + RTH_CLOSE.minute) - (t.hour * 60 + t.minute)
