"""
PersistentIGSession — login UNA volta, token riusati per TUTTO (discovery +
apertura + monitoraggio) e anche tra riavvii del processo. Nuovo login SOLO se i
token salvati sono scaduti/invalidi.

Perché: IG limita la FREQUENZA di login → tanti login ravvicinati causano
`invalid-client-security-token` (lockout temporaneo). Riusando la sessione si fa
al massimo UN login per volta che scade davvero, mai login a raffica.

Uso:
  sess = PersistentIGSession(client, "data/ig_session_live.json", audit)
  if not sess.ensure(): ...      # riusa o logga una volta
  # ... tutte le operazioni sullo stesso client ...
  # nel loop lungo, periodicamente: sess.keep_alive()

Il file di sessione contiene i token di auth → è git-ignorato (dati/segreti).
"""
import json
import os
import time
from typing import Optional


class PersistentIGSession:
    def __init__(self, client, session_file: str, audit=None):
        self.client = client                 # IGClient non ancora loggato
        self.session_file = session_file
        self.audit = audit

    # ------------------------------------------------------------------
    def ensure(self, force_login: bool = False) -> bool:
        """Garantisce una sessione valida sul client. Riusa i token salvati se
        validi; altrimenti UN login. Ritorna True se la sessione è pronta."""
        if not force_login:
            tok = self._load()
            if tok and tok.get("base") == self.client.base_url:
                self.client.apply_tokens(tok.get("cst"), tok.get("x"),
                                         tok.get("acc"), tok.get("ls"))
                if self.client.is_session_valid():
                    self._log("session_reused", account=self.client.account_id,
                              age_s=int(time.time() - tok.get("ts", 0)))
                    return True
                self._log("session_expired", note="token non validi → un login")
        # UN login (e salva i nuovi token)
        if not self.client.login():
            self._log("login_failed", level="error")
            return False
        self._save()
        self._log("session_new_login", account=self.client.account_id)
        return True

    def keep_alive(self) -> bool:
        """Per il loop lungo: se la sessione è ancora valida non fa nulla (evita
        login inutili); se è scaduta ne apre UNA nuova."""
        if self.client.cst and self.client.is_session_valid():
            return True
        return self.ensure()

    def invalidate_file(self):
        """Cancella il file di sessione (per forzare un login pulito al prossimo giro)."""
        try:
            os.remove(self.session_file)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def _load(self) -> Optional[dict]:
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save(self):
        data = {"cst": self.client.cst, "x": self.client.security_token,
                "acc": self.client.account_id,
                "ls": getattr(self.client, "lightstreamer_endpoint", None),
                "base": self.client.base_url, "ts": time.time()}
        os.makedirs(os.path.dirname(self.session_file) or ".", exist_ok=True)
        tmp = self.session_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.session_file)     # scrittura atomica
        try:
            os.chmod(self.session_file, 0o600)  # solo owner (contiene token)
        except OSError:
            pass

    def _log(self, action, level="info", **f):
        if self.audit:
            getattr(self.audit, level, self.audit.info)(action, **f)
