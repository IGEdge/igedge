"""
Log rotativo minuzioso per l'esecuzione dei condor. Due sbocche:

  1. logs/condor.log       — leggibile dall'uomo, rotativo (5MB × 10 file).
  2. logs/condor_audit.jsonl — audit trail STRUTTURATO: una riga JSON per ogni
     evento (ingresso richiesta, risposta IG, decisione, unwind, errore). È la
     verità a prova di debug/contestazione: NON si sovrascrive, si accoda e ruota.

Ogni azione critica passa da qui. In dry-run è identico (marcato dry_run=True) così
il collaudo produce lo stesso audit del live.
"""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

_LOG_DIR = "logs"
_AUDIT_PATH = os.path.join(_LOG_DIR, "condor_audit.jsonl")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Logger dedicato all'esecuzione condor: umano + JSONL."""

    def __init__(self, name: str = "condor", dry_run: bool = False):
        os.makedirs(_LOG_DIR, exist_ok=True)
        self.dry_run = dry_run
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self.logger.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                "%(asctime)s %(levelname)-8s [condor] %(message)s")
            rot = RotatingFileHandler(os.path.join(_LOG_DIR, "condor.log"),
                                      maxBytes=5 * 1024 * 1024, backupCount=10,
                                      encoding="utf-8")
            rot.setFormatter(fmt)
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self.logger.addHandler(rot)
            self.logger.addHandler(sh)
        # audit JSONL rotativo (via un secondo RotatingFileHandler dedicato)
        self._audit = logging.getLogger(name + ".audit")
        if not self._audit.handlers:
            self._audit.setLevel(logging.INFO)
            ah = RotatingFileHandler(_AUDIT_PATH, maxBytes=10 * 1024 * 1024,
                                     backupCount=20, encoding="utf-8")
            ah.setFormatter(logging.Formatter("%(message)s"))
            self._audit.addHandler(ah)
            self._audit.propagate = False

    # ------------------------------------------------------------------
    def event(self, action: str, level: str = "INFO", **fields: Any) -> None:
        """Registra un evento: riga umana + riga JSONL strutturata."""
        rec: Dict[str, Any] = {"ts": _utc(), "action": action,
                               "dry_run": self.dry_run, **fields}
        self._audit.info(json.dumps(rec, default=str, ensure_ascii=False))
        human = " ".join(f"{k}={v}" for k, v in fields.items()
                         if k not in ("raw_response",))
        msg = f"{action}  {human}" + ("  [DRY-RUN]" if self.dry_run else "")
        getattr(self.logger, level.lower(), self.logger.info)(msg)

    def info(self, action: str, **f): self.event(action, "INFO", **f)
    def warn(self, action: str, **f): self.event(action, "WARNING", **f)
    def error(self, action: str, **f): self.event(action, "ERROR", **f)

    def critical(self, action: str, **f):
        """Evento CRITICO (es. unwind fallito): serve intervento manuale."""
        self.event(action, "CRITICAL", **f)
