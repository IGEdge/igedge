#!/usr/bin/env python3
"""
Read-only reader of the IG US500 option chain (per EDGE_SHORTVOL.md).

SOLO LETTURA: fa login, cerca/naviga le opzioni US500, e stampa la catena
(strike, bid/ask, spread per gamba) + i contract details (settlement, size,
commissioni). NON piazza NESSUN ordine — usa esclusivamente login/search/
get_market/marketnavigation/logout.

Demo o Live (le mensili vanilla stanno sul REALE, vedi EDGE_SHORTVOL.md §6):
  python scripts/read_ig_option_chain.py            # demo (IG_* — set daily/knockout)
  python scripts/read_ig_option_chain.py --live     # reale (IG_LIVE_* — catena mensile)

⚠️ Gli spread del DEMO sono più stretti del reale: per i COSTI usa sempre il reale.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests
from dotenv import load_dotenv

# carica il .env del progetto in modo esplicito (funziona anche da fuori cartella)
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from src.core.ig_client import IGClient


def make_client(live: bool) -> IGClient:
    if live:
        key = os.getenv("IG_LIVE_API_KEY")
        ident = os.getenv("IG_LIVE_IDENTIFIER")
        pwd = os.getenv("IG_LIVE_PASSWORD")
        acc = os.getenv("IG_LIVE_ACCOUNT_ID") or None
        if not key or not ident or not pwd:
            print("❌ Mancano le credenziali LIVE nel .env (IG_LIVE_API_KEY / "
                  "IG_LIVE_IDENTIFIER / IG_LIVE_PASSWORD). Compilale e riprova.")
            return None
        return IGClient(key, ident, pwd, "LIVE", acc)
    return IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                    os.getenv("IG_PASSWORD"), "DEMO",
                    os.getenv("IG_OPT_ACCOUNT_ID") or os.getenv("IG_ACCOUNT_ID") or None)


def find_option_markets(ig: IGClient) -> list:
    """Cerca le opzioni US500 via search (più termini) + prova marketnavigation.
    Ritorna una lista di market dict (deduplicati per epic)."""
    seen, out = set(), []
    terms = ["US 500", "US 500 Options", "Daily US 500", "US 500 Monthly",
             "US 500 Future", "Monthly US 500", "US 500 Weekly", "S&P 500 Options"]
    for term in terms:
        for m in ig.search_markets(term):
            it = str(m.get("instrumentType", "")).upper()
            nm = str(m.get("instrumentName", ""))
            epic = m.get("epic")
            if epic in seen:
                continue
            if "OPT" in it or "CALL" in nm.upper() or "PUT" in nm.upper():
                seen.add(epic)
                out.append(m)
    return out


def parse_option_name(nm: str):
    """'... 7580.0 CALL ...' -> (7580.0, 'CALL'). Best-effort."""
    up = nm.upper()
    kind = "CALL" if "CALL" in up else ("PUT" if "PUT" in up else "?")
    strike = None
    for tok in nm.replace("(", " ").replace(")", " ").split():
        try:
            v = float(tok)
            if 1000 < v < 20000:
                strike = v
                break
        except ValueError:
            continue
    return strike, kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="usa il conto REALE (IG_LIVE_*)")
    ap.add_argument("--expiry", default=None,
                    help="filtra per scadenza (sottostringa, es. 'AUG'); default = quella con più strike")
    ap.add_argument("--center", type=float, default=7570.0, help="strike centrale (~sottostante)")
    ap.add_argument("--width", type=float, default=1200.0, help="±punti attorno al centro da interrogare")
    ap.add_argument("--strike-list", default=None,
                    help="lista sparsa di strike da interrogare (es. '6700,7130,7550,8000,8430') — pochi call")
    ap.add_argument("--sleep", type=float, default=0.8, help="pausa tra le richieste (allowance)")
    ap.add_argument("--max-details", type=int, default=30,
                    help="tetto di opzioni interrogate in dettaglio (allowance)")
    args = ap.parse_args()

    ig = make_client(args.live)
    if ig is None:
        return 1
    env = "LIVE (REALE)" if args.live else "DEMO"
    print(f"Ambiente: {env}  — host {ig.base_url}")
    if not ig.login():
        print("❌ login fallito (key giusta per questo ambiente? IG rate-limita i "
              "login ravvicinati: se hai appena provato, aspetta qualche minuto).")
        return 1
    print(f"✅ login OK — account {ig.account_id}\n")

    # market navigation (spesso funziona sul live, 404 sul demo)
    try:
        r = requests.get(f"{ig.base_url}/marketnavigation",
                         headers=ig._headers(version="1"), timeout=20)
        print(f"marketnavigation root: HTTP {r.status_code}"
              + (f"  nodi: {[n.get('name') for n in r.json().get('nodes', [])][:12]}"
                 if r.status_code == 200 else ""))
    except Exception as e:
        print(f"marketnavigation: errore {e}")

    import time
    mkts = find_option_markets(ig)
    print(f"\nOpzioni US500 trovate: {len(mkts)}")
    if not mkts:
        print("  Nessuna opzione via search. Controlla che il conto abbia le opzioni "
              "abilitate.")
        ig.logout()
        return 0

    # arricchisco ogni market con (strike, kind, expiry) dal NOME (no get_market)
    for m in mkts:
        st, kd = parse_option_name(str(m.get("instrumentName", "")))
        m["_strike"], m["_kind"], m["_exp"] = st, kd, m.get("expiry")

    # scelgo la scadenza: --expiry (sottostringa) o quella con più strike
    from collections import Counter
    if args.expiry:
        target_exp = args.expiry
        pool = [m for m in mkts if args.expiry.upper() in str(m.get("expiry", "")).upper()]
    else:
        cnt = Counter(str(m.get("expiry")) for m in mkts if m.get("_strike"))
        target_exp = cnt.most_common(1)[0][0] if cnt else None
        pool = [m for m in mkts if str(m.get("expiry")) == target_exp]
    print(f"Scadenza scelta: {target_exp}  ({len(pool)} opzioni)")

    # selezione strike: lista sparsa (--strike-list) o finestra attorno al centro
    if args.strike_list:
        want = [float(x) for x in args.strike_list.split(",")]
        pool = [m for m in pool if m.get("_strike") and
                any(abs(m["_strike"] - w) < 5 for w in want)]
        print(f"Interrogo gli strike richiesti: {sorted({m['_strike'] for m in pool})}")
    else:
        lo, hi = args.center - args.width, args.center + args.width
        pool = [m for m in pool if m.get("_strike") and lo <= m["_strike"] <= hi]
        print(f"Interrogo strike in [{lo:.0f}, {hi:.0f}]")
    pool.sort(key=lambda m: (m["_strike"], m["_kind"]))
    pool = pool[:args.max_details]
    print(f"  ({len(pool)} opzioni, pausa {args.sleep}s)\n")

    rows, stop = [], False
    for m in pool:
        det = ig.get_market(m["epic"])
        if det is None:
            print("  ⚠️ allowance/errore su get_market — mi fermo qui.")
            stop = True
            break
        snap = det.get("snapshot", {}) or {}
        bid, off = snap.get("bid"), snap.get("offer")
        spread = (off - bid) if (bid is not None and off is not None) else None
        rows.append(dict(strike=m["_strike"], kind=m["_kind"], bid=bid, offer=off,
                         spread=spread, epic=m["epic"], det=det))
        time.sleep(args.sleep)

    print(f"=== {target_exp} — bid/ask reali ({len(rows)} strike) ===")
    print(f"   {'strike':>8} {'tipo':4s}  {'bid':>9} {'offer':>9} {'spread':>7}")
    for r in rows:
        sp = f"{r['spread']:.2f}" if r["spread"] is not None else "-"
        print(f"   {r['strike']:>8.0f} {r['kind']:4s}  {str(r['bid']):>9} "
              f"{str(r['offer']):>9} {sp:>7}")
    sset = [r["spread"] for r in rows if r["spread"] is not None]
    if sset:
        print(f"\n   spread: min {min(sset):.2f}  medio {sum(sset)/len(sset):.2f}  "
              f"max {max(sset):.2f} pt/gamba")

    # contract details / settlement (guardato)
    if rows:
        inst = (rows[0]["det"] or {}).get("instrument", {}) or {}
        ed = inst.get("expiryDetails") or {}
        print(f"\n=== CONTRACT DETAILS ({rows[0]['epic']}) ===")
        print(f"  type={inst.get('type')}  expiry={inst.get('expiry')}")
        print(f"  settlementInfo={ed.get('settlementInfo')!r}")
        print(f"  lastDealingDate={ed.get('lastDealingDate')}")
        print(f"  currencies={[c.get('code') for c in (inst.get('currencies') or [])]}")
        print(f"  lotSize={inst.get('lotSize')}  valueOfOnePip={inst.get('valueOfOnePip')}")

    ig.logout()
    print(f"\n(Solo lettura: nessun ordine inviato.{' Allowance esaurita: riprova tra ~1 min.' if stop else ''})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
