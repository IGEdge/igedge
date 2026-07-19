"""
Log rotativo per l'esecuzione opzioni / spread multi-gamba (issue #16).

  1. logs/options.log         — leggibile (dual-write anche su condor.log)
  2. logs/options_audit.jsonl — audit JSONL (dual-write su condor_audit.jsonl)

Ogni azione critica passa da qui. In dry-run è identico (marcato dry_run=True).
"""
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

_LOG_DIR = "logs"
_AUDIT_PATH = os.path.join(_LOG_DIR, "options_audit.jsonl")
_AUDIT_PATH_LEGACY = os.path.join(_LOG_DIR, "condor_audit.jsonl")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    """Logger dedicato all'esecuzione spread/opzioni: umano + JSONL."""

    def __init__(self, name: str = "options", dry_run: bool = False):
        os.makedirs(_LOG_DIR, exist_ok=True)
        self.dry_run = dry_run
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            self.logger.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                "%(asctime)s %(levelname)-8s [options] %(message)s")
            for path in (os.path.join(_LOG_DIR, "options.log"),
                         os.path.join(_LOG_DIR, "condor.log")):
                rot = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024,
                                          backupCount=10, encoding="utf-8")
                rot.setFormatter(fmt)
                self.logger.addHandler(rot)
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            self.logger.addHandler(sh)
        self._audit = logging.getLogger(name + ".audit")
        if not self._audit.handlers:
            self._audit.setLevel(logging.INFO)
            for path in (_AUDIT_PATH, _AUDIT_PATH_LEGACY):
                ah = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024,
                                         backupCount=20, encoding="utf-8")
                ah.setFormatter(logging.Formatter("%(message)s"))
                self._audit.addHandler(ah)
            self._audit.propagate = False

    def event(self, action: str, level: str = "INFO", **fields: Any) -> None:
        rec: Dict[str, Any] = {"ts": _utc(), "action": action,
                               "dry_run": self.dry_run, **fields}
        self._audit.info(json.dumps(rec, default=str, ensure_ascii=False))
        human = " ".join(f"{k}={v}" for k, v in fields.items()
                         if k not in ("raw_response",))
        msg = f"{action}  {human}" + ("  [DRY-RUN]" if self.dry_run else "")
        getattr(self.logger, level.lower(), self.logger.info)(msg)

    def info(self, action: str, **f):
        self.event(action, "INFO", **f)

    def warn(self, action: str, **f):
        self.event(action, "WARNING", **f)

    def error(self, action: str, **f):
        self.event(action, "ERROR", **f)

    def critical(self, action: str, **f):
        self.event(action, "CRITICAL", **f)
