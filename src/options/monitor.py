"""
SpreadMonitor — monitoraggio spread multi-gamba a mercato (issue #16).

Ex CondorMonitor. Alias: CondorMonitor = SpreadMonitor.
Read-only: mark, DTE, reconcile. NON opera.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .audit_log import AuditLog
from .spread import OptionSpread

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def third_friday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    first_friday = 1 + (4 - d.weekday()) % 7
    return datetime(year, month, first_friday + 14, tzinfo=timezone.utc)


def parse_expiry(expiry: str) -> Optional[datetime]:
    try:
        parts = expiry.strip().upper().split("-")
        if len(parts) == 3:
            d, mon, yy = parts
            year = 2000 + int(yy) if len(yy) == 2 else int(yy)
            return datetime(year, _MONTHS[mon[:3]], int(d), tzinfo=timezone.utc)
        if len(parts) == 2:
            mon, yy = parts
            year = 2000 + int(yy) if len(yy) == 2 else int(yy)
            return third_friday(year, _MONTHS[mon[:3]])
    except Exception:
        return None
    return None


def is_standard_expiry(expiry: str) -> bool:
    return len(str(expiry).strip().split("-")) == 2


_MON_ABBR = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
             "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def upcoming_standard_expiries(n_months: int = 8):
    now = datetime.now(timezone.utc)
    out, y, m = [], now.year, now.month
    for _ in range(n_months + 1):
        out.append((f"{_MON_ABBR[m - 1]}-{y % 100:02d}", third_friday(y, m).date()))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


class SpreadMonitor:
    def __init__(self, client, store, audit: AuditLog = None,
                 value_per_point: float = 1.0):
        self.client = client
        self.store = store
        self.audit = audit or AuditLog()
        self.vpp = value_per_point

    def _mid(self, epic: str) -> Optional[float]:
        m = self.client.get_market(epic)
        if not m:
            return None
        snap = m.get("snapshot", {}) or {}
        bid, offer = snap.get("bid"), snap.get("offer")
        if bid is None or offer is None:
            return None
        return (bid + offer) / 2.0

    def _dte(self, expiry: str) -> Optional[int]:
        exp = parse_expiry(expiry)
        if exp is None:
            return None
        return (exp.date() - datetime.now(timezone.utc).date()).days

    def mark(self, c: OptionSpread) -> Dict[str, Any]:
        spot = self._mid(c.underlying_epic)
        legs_mid, missing_quote = {}, []
        short_cost = long_credit = 0.0
        for leg in c.legs:
            if leg.status != "OPEN":
                continue
            mid = self._mid(leg.epic)
            legs_mid[leg.role] = mid
            if mid is None:
                missing_quote.append(leg.role)
                continue
            if leg.is_long:
                long_credit += mid
            else:
                short_cost += mid
        net_close = short_cost - long_credit
        size = c.legs[0].size if c.legs else 1.0
        unreal_pts = c.target_credit - net_close
        unreal_ccy = unreal_pts * size * self.vpp
        sp = c.by_role("short_put")
        sc = c.by_role("short_call")
        dist = {}
        if spot is not None:
            if sp:
                dist["put"] = spot - sp.strike
            if sc:
                dist["call"] = sc.strike - spot
        return {"spot": spot, "dte": self._dte(c.expiry), "legs_mid": legs_mid,
                "missing_quote": missing_quote, "net_close": net_close,
                "unreal_pts": unreal_pts, "unreal_ccy": unreal_ccy,
                "max_profit": c.target_credit * size * self.vpp,
                "max_loss": c.max_loss * size * self.vpp, "dist": dist}

    def reconcile(self, c: OptionSpread) -> Dict[str, Any]:
        try:
            ig = self.client.get_positions()
        except Exception as e:
            return {"ok": False, "error": f"get_positions:{e}"}
        ig_by_deal = {}
        for it in ig:
            pos = it.get("position", {}) or {}
            if pos.get("dealId"):
                ig_by_deal[pos["dealId"]] = it
        our_deals = set()
        missing = []
        for leg in c.legs:
            if leg.status == "OPEN" and leg.deal_id:
                our_deals.add(leg.deal_id)
                if leg.deal_id not in ig_by_deal:
                    missing.append(leg.role)
        our_epics = {l.epic for l in c.legs}
        orphans = [d for d, it in ig_by_deal.items()
                   if (it.get("market", {}) or {}).get("epic") in our_epics
                   and d not in our_deals]
        dte = self._dte(c.expiry)
        expired_ctx = dte is not None and dte <= 0
        return {"ok": not missing and not orphans, "missing": missing,
                "orphans": orphans, "expired_context": expired_ctx}

    def report(self) -> str:
        spreads = self.store.get_open()
        if not spreads:
            return "Nessuno spread aperto."
        out = [f"=== {len(spreads)} spread aperti  "
               f"({datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}) ==="]
        for c in spreads:
            m = self.mark(c)
            rec = self.reconcile(c)
            cid = getattr(c, "store_id", "?")
            strat = getattr(c, "strategy", None) or "?"
            out.append(f"\n#{cid}  [{strat}]  scad {c.expiry}  DTE {m['dte']}  "
                       f"spot {m['spot']}  stato {c.status}")
            for leg in c.legs:
                mid = m["legs_mid"].get(leg.role)
                out.append(f"   {leg.role:15s} {leg.direction} {leg.kind} "
                           f"{leg.strike:.0f} x{leg.size:g}  mid={mid}  "
                           f"deal={leg.deal_id}  [{leg.status}]")
            d = m["dist"]
            out.append(f"   distanza short:  put {d.get('put')}   "
                       f"call {d.get('call')}  (>0 = al sicuro)")
            out.append(f"   P&L non realizz.: {m['unreal_ccy']:+.1f}  "
                       f"(max profit {m['max_profit']:+.0f} / "
                       f"max loss {m['max_loss']:+.0f})")
            if m["missing_quote"]:
                out.append(f"   ⚠️ quote mancanti: {m['missing_quote']}")
            if not rec["ok"]:
                lvl = "info" if rec.get("expired_context") else "warn"
                tag = ("ℹ️ (scadenza)" if rec.get("expired_context")
                       else "⚠️ ANOMALIA")
                out.append(f"   {tag} reconcile: gambe mancanti su IG="
                           f"{rec['missing']}  orfani={rec['orphans']}")
                getattr(self.audit, "warn" if lvl == "warn" else "info")(
                    "reconcile_mismatch", spread_id=cid, missing=rec["missing"],
                    orphans=rec["orphans"], expired=rec.get("expired_context"))
            else:
                out.append("   reconcile: ✓ tutte le gambe presenti su IG")
        return "\n".join(out)


CondorMonitor = SpreadMonitor
