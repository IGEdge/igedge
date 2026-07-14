"""
IGClient — REST client for the IG dealing API (session auth v2).

Scope of THIS module (adapter bootstrap): authentication and read-only
account/market queries. Order execution (open/close positions with native
attached stop/limit) is added in a later phase once the connection and the
US500 epic are confirmed on the demo account.

IG auth model (differs from Deribit OAuth):
  - POST /session (Version 2) with header X-IG-API-KEY + JSON {identifier,
    password, encryptedPassword:false}.
  - Success returns two auth tokens in the RESPONSE HEADERS: CST and
    X-SECURITY-TOKEN. Every authenticated request must resend both, plus
    X-IG-API-KEY.
  - DEMO and LIVE are different hosts AND need different API keys.

Docs: https://labs.ig.com/rest-trading-api-reference
"""
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Windows/proxy environments intercept TLS with a corporate CA that certifi's
# bundle doesn't contain, so requests' default verification fails. truststore
# routes verification through the OS trust store (where that CA is already
# trusted) — the secure fix, no verify=False needed. Best-effort: if the
# package is missing we leave default verification in place.
try:
    import truststore as _truststore

    _truststore.inject_into_ssl()
    logger.debug("[IG] truststore injected — using OS certificate store")
except Exception:  # pragma: no cover - truststore optional
    pass

DEMO_BASE = "https://demo-api.ig.com/gateway/deal"
LIVE_BASE = "https://api.ig.com/gateway/deal"


class IGClient:
    """Minimal IG dealing-API client: login + account/market reads."""

    def __init__(
        self,
        api_key: str,
        identifier: str,
        password: str,
        acc_type: str = "DEMO",
        account_id: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key
        self.identifier = identifier
        self.password = password
        self.acc_type = (acc_type or "DEMO").upper()
        self.base_url = DEMO_BASE if self.acc_type == "DEMO" else LIVE_BASE
        self.account_id = account_id or None
        self.timeout = timeout

        self.cst: Optional[str] = None
        self.security_token: Optional[str] = None
        self.session_info: Dict[str, Any] = {}
        self.lightstreamer_endpoint: Optional[str] = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _headers(self, version: str = "1", auth: bool = True) -> Dict[str, str]:
        h = {
            "X-IG-API-KEY": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json; charset=UTF-8",
            "Version": str(version),
        }
        if auth and self.cst and self.security_token:
            h["CST"] = self.cst
            h["X-SECURITY-TOKEN"] = self.security_token
        if auth and self.account_id:
            h["IG-ACCOUNT-ID"] = self.account_id
        return h

    @staticmethod
    def _error_code(resp: requests.Response) -> str:
        try:
            return resp.json().get("errorCode", "")
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Open a dealing session. Populates CST + X-SECURITY-TOKEN.

        Returns True on success. On failure logs the IG errorCode (e.g.
        error.security.invalid-details, error.security.api-key-invalid).
        """
        url = f"{self.base_url}/session"
        body = {
            "identifier": self.identifier,
            "password": self.password,
            "encryptedPassword": False,
        }
        try:
            resp = requests.post(
                url, json=body,
                headers=self._headers(version="2", auth=False),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] login request failed: {e}")
            return False

        if resp.status_code != 200:
            logger.error(
                f"[IG] login failed HTTP {resp.status_code}: "
                f"{self._error_code(resp) or resp.text[:200]}"
            )
            return False

        self.cst = resp.headers.get("CST")
        self.security_token = resp.headers.get("X-SECURITY-TOKEN")
        self.session_info = resp.json() if resp.content else {}
        self.lightstreamer_endpoint = self.session_info.get("lightstreamerEndpoint")
        if not self.account_id:
            self.account_id = self.session_info.get("currentAccountId")

        ok = bool(self.cst and self.security_token)
        if ok:
            logger.info(
                f"[IG] logged in — account {self.account_id} "
                f"({self.session_info.get('accountType', '?')})"
            )
        else:
            logger.error("[IG] login returned 200 but no CST/security token")
        return ok

    def apply_tokens(self, cst: str, security_token: str,
                     account_id: Optional[str] = None,
                     lightstreamer_endpoint: Optional[str] = None) -> None:
        """Riusa token di sessione già ottenuti (da una sessione persistente),
        senza rifare il login. Vedi src/options/session.py."""
        self.cst = cst
        self.security_token = security_token
        if account_id:
            self.account_id = account_id
        if lightstreamer_endpoint:
            self.lightstreamer_endpoint = lightstreamer_endpoint

    def is_session_valid(self) -> bool:
        """I token attuali sono ancora validi? (GET /session → 200). Usato dalla
        sessione persistente per riusare invece di ri-loggare (evita il lockout
        da troppi login ravvicinati)."""
        if not (self.cst and self.security_token):
            return False
        try:
            r = requests.get(f"{self.base_url}/session",
                             headers=self._headers(version="1"), timeout=self.timeout)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def logout(self) -> None:
        """Close the dealing session (best-effort)."""
        if not (self.cst and self.security_token):
            return
        try:
            requests.delete(
                f"{self.base_url}/session",
                headers=self._headers(version="1"),
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException:
            pass
        self.cst = self.security_token = None

    # ------------------------------------------------------------------
    # Read-only queries
    # ------------------------------------------------------------------

    def get_accounts(self) -> List[Dict[str, Any]]:
        """All accounts on the login (id, type, balance, currency, preferred)."""
        try:
            resp = requests.get(
                f"{self.base_url}/accounts",
                headers=self._headers(version="1"),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("accounts", [])
            logger.error(f"[IG] get_accounts HTTP {resp.status_code}: "
                         f"{self._error_code(resp)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] get_accounts failed: {e}")
        return []

    def search_markets(self, search_term: str) -> List[Dict[str, Any]]:
        """Find epics by free-text term (e.g. 'US 500')."""
        try:
            resp = requests.get(
                f"{self.base_url}/markets",
                params={"searchTerm": search_term},
                headers=self._headers(version="1"),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("markets", [])
            logger.error(f"[IG] search_markets HTTP {resp.status_code}: "
                         f"{self._error_code(resp)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] search_markets failed: {e}")
        return []

    def get_prices(
        self,
        epic: str,
        resolution: str = "DAY",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        max_points: int = 0,
    ) -> Dict[str, Any]:
        """Historical price bars (Version 3).

        resolution: SECOND, MINUTE, MINUTE_2/3/5/10/15/30, HOUR, HOUR_2/3/4,
                    DAY, WEEK, MONTH.
        date_from/date_to: 'yyyy-MM-ddTHH:mm:ss' (UTC). max_points: cap (0=API default).

        Returns {"bars": [ {ts, open, high, low, close, volume} ... ] (mid prices,
        oldest first), "allowance": {remaining, total, expiry_sec}}. Prices are
        the MID of IG bid/ask. Consumes the account's historical-data allowance.
        """
        params: Dict[str, Any] = {"resolution": resolution}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if max_points:
            params["max"] = max_points

        try:
            resp = requests.get(
                f"{self.base_url}/prices/{epic}",
                params=params,
                headers=self._headers(version="3"),
                timeout=max(self.timeout, 60),
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] get_prices failed: {e}")
            return {"bars": [], "allowance": {}}

        if resp.status_code != 200:
            logger.error(f"[IG] get_prices HTTP {resp.status_code}: "
                         f"{self._error_code(resp) or resp.text[:200]}")
            return {"bars": [], "allowance": {}}

        return self._parse_prices(resp.json())

    def get_prices_v2(
        self, epic: str, resolution: str = "DAY", num_points: int = 2000,
    ) -> Dict[str, Any]:
        """Historical bars via the Version-2 numPoints form:
        GET /prices/{epic}/{resolution}/{numPoints} → the most recent
        numPoints bars in ONE response (the v3 endpoint silently caps at 20).
        Returns the same {"bars", "allowance"} shape as get_prices()."""
        try:
            resp = requests.get(
                f"{self.base_url}/prices/{epic}/{resolution}/{num_points}",
                headers=self._headers(version="2"),
                timeout=max(self.timeout, 60),
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] get_prices_v2 failed: {e}")
            return {"bars": [], "allowance": {}}

        if resp.status_code != 200:
            logger.error(f"[IG] get_prices_v2 HTTP {resp.status_code}: "
                         f"{self._error_code(resp) or resp.text[:200]}")
            return {"bars": [], "allowance": {}}
        return self._parse_prices(resp.json())

    @staticmethod
    def _parse_prices(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalise an IG prices payload (v2 or v3) to mid-price bars."""
        def _mid(p):
            bid, ask = p.get("bid"), p.get("ask")
            if bid is not None and ask is not None:
                return (bid + ask) / 2.0
            if bid is not None or ask is not None:
                return bid if bid is not None else ask
            return p.get("lastTraded")

        bars = []
        for row in data.get("prices", []):
            o = _mid(row.get("openPrice", {}) or {})
            h = _mid(row.get("highPrice", {}) or {})
            low = _mid(row.get("lowPrice", {}) or {})
            c = _mid(row.get("closePrice", {}) or {})
            if None in (o, h, low, c):
                continue
            bars.append({
                "ts": row.get("snapshotTime") or row.get("snapshotTimeUTC"),
                "open": o, "high": h, "low": low, "close": c,
                "volume": row.get("lastTradedVolume") or 0,
            })

        alw = ((data.get("metadata", {}) or {}).get("allowance", {})
               or data.get("allowance", {}) or {})
        return {
            "bars": bars,
            "allowance": {
                "remaining": alw.get("remainingAllowance"),
                "total": alw.get("totalAllowance"),
                "expiry_sec": alw.get("allowanceExpiry"),
            },
        }

    def get_market(self, epic: str) -> Optional[Dict[str, Any]]:
        """Full market details for an epic (dealing rules, min size, currency,
        value of one point) — needed later for CFD position sizing."""
        try:
            resp = requests.get(
                f"{self.base_url}/markets/{epic}",
                headers=self._headers(version="3"),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"[IG] get_market({epic}) HTTP {resp.status_code}: "
                         f"{self._error_code(resp)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] get_market failed: {e}")
        return None

    # ------------------------------------------------------------------
    # Execution (OTC positions). Every deal returns a dealReference that MUST
    # be confirmed via confirm() — do not assume the fill. See BOT_ARCHITECTURE.
    # ------------------------------------------------------------------

    def get_positions(self) -> List[Dict[str, Any]]:
        """All open positions (Version 2). Each item: {position:{dealId, size,
        direction, level, ...}, market:{epic, instrumentName, ...}}."""
        try:
            resp = requests.get(
                f"{self.base_url}/positions",
                headers=self._headers(version="2"),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json().get("positions", [])
            logger.error(f"[IG] get_positions HTTP {resp.status_code}: "
                         f"{self._error_code(resp)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] get_positions failed: {e}")
        return []

    def confirm(self, deal_reference: str) -> Optional[Dict[str, Any]]:
        """Confirm the outcome of a deal (Version 1). Returns the confirm dict:
        {dealStatus: ACCEPTED|REJECTED, dealId, status, reason, level, size...}."""
        try:
            resp = requests.get(
                f"{self.base_url}/confirms/{deal_reference}",
                headers=self._headers(version="1"),
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"[IG] confirm HTTP {resp.status_code}: "
                         f"{self._error_code(resp)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] confirm failed: {e}")
        return None

    def open_position(
        self,
        epic: str,
        direction: str,
        size: float,
        currency: str = "EUR",
        order_type: str = "MARKET",
        level: Optional[float] = None,
        stop_distance: Optional[float] = None,
        limit_distance: Optional[float] = None,
        guaranteed_stop: bool = False,
        expiry: str = "-",
    ) -> Optional[Dict[str, Any]]:
        """Open a position via POST /positions/otc (Version 2).

        direction: 'BUY' | 'SELL'. size in contracts (min per epic). MARKET or
        LIMIT (needs level). stop/limit_distance in points (attached natively —
        no separate orphan order). Returns the CONFIRM dict (already confirmed),
        or None. Check dealStatus == 'ACCEPTED' + dealId before trusting it."""
        body: Dict[str, Any] = {
            "epic": epic,
            "expiry": expiry,
            "direction": direction.upper(),
            "size": str(size),
            "orderType": order_type.upper(),
            "currencyCode": currency,
            "forceOpen": True,
            "guaranteedStop": guaranteed_stop,
        }
        if order_type.upper() == "LIMIT" and level is not None:
            body["level"] = level
        if stop_distance is not None:
            body["stopDistance"] = str(stop_distance)
        if limit_distance is not None:
            body["limitDistance"] = str(limit_distance)

        ref = self._deal(f"{self.base_url}/positions/otc", body, version="2")
        return self.confirm(ref) if ref else None

    def close_position(
        self,
        deal_id: str,
        open_direction: str,
        size: float,
        order_type: str = "MARKET",
        level: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Close a position by dealId via POST /positions/otc + _method=DELETE
        (Version 1). Sends the OPPOSITE direction. Returns the confirm dict."""
        close_dir = "SELL" if open_direction.upper() == "BUY" else "BUY"
        body: Dict[str, Any] = {
            "dealId": deal_id,
            "direction": close_dir,
            "size": str(size),
            "orderType": order_type.upper(),
        }
        if order_type.upper() == "LIMIT" and level is not None:
            body["level"] = level
        ref = self._deal(f"{self.base_url}/positions/otc", body,
                         version="1", delete=True)
        return self.confirm(ref) if ref else None

    def _deal(self, url: str, body: Dict[str, Any], version: str,
              delete: bool = False) -> Optional[str]:
        """POST a deal, return its dealReference (or None). `delete` sends the
        IG _method=DELETE override used to close positions."""
        headers = self._headers(version=version)
        if delete:
            headers["_method"] = "DELETE"
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json().get("dealReference")
            logger.error(f"[IG] deal HTTP {resp.status_code}: "
                         f"{self._error_code(resp) or resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[IG] deal failed: {e}")
        return None
