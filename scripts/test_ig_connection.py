#!/usr/bin/env python3
"""
Smoke test: confirm the IG demo credentials in .env actually work.

Runs a real login against the IG demo API, then lists your accounts and
searches for the US 500 epic. Prints NO secrets (API key is masked).

Usage:
    python scripts/test_ig_connection.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows console defaults to cp1252 → force UTF-8 so arrows/emoji don't crash
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

from src.core.ig_client import IGClient


def mask(s: str, keep: int = 4) -> str:
    if not s:
        return "(vuoto)"
    return f"...{s[-keep:]} (len {len(s)})"


def main() -> int:
    load_dotenv()

    api_key = os.getenv("IG_API_KEY", "")
    identifier = os.getenv("IG_IDENTIFIER", "")
    password = os.getenv("IG_PASSWORD", "")
    acc_type = os.getenv("IG_ACC_TYPE", "DEMO")
    account_id = os.getenv("IG_ACCOUNT_ID", "") or None
    epic = os.getenv("IG_EPIC", "")

    print("=" * 60)
    print("IG CONNECTION SMOKE TEST")
    print("=" * 60)
    print(f"  Env type   : {acc_type}")
    print(f"  API key    : {mask(api_key)}")
    print(f"  Identifier : {mask(identifier)}")
    print(f"  Password   : {'set' if password else '(vuoto)'}")
    print(f"  Account ID : {account_id or '(auto dal login)'}")
    print(f"  Epic (env) : {epic or '(non impostato)'}")
    print("-" * 60)

    missing = [k for k, v in {
        "IG_API_KEY": api_key,
        "IG_IDENTIFIER": identifier,
        "IG_PASSWORD": password,
    }.items() if not v]
    if missing:
        print(f"❌ Mancano nel .env: {', '.join(missing)}")
        return 1

    client = IGClient(api_key, identifier, password, acc_type, account_id)

    print("→ Login...")
    if not client.login():
        print("❌ Login FALLITO. Controlla API key (deve essere quella DEMO), "
              "username (non email) e password nel .env.")
        return 1
    print("✅ Login OK")
    print(f"   Account attivo   : {client.account_id}")
    print(f"   Account type     : {client.session_info.get('accountType')}")
    print(f"   Lightstreamer    : {client.lightstreamer_endpoint}")

    print("\n→ Conti disponibili:")
    accounts = client.get_accounts()
    for a in accounts:
        bal = a.get("balance", {}) or {}
        star = " *preferito*" if a.get("preferred") else ""
        print(f"   - {a.get('accountId')} | {a.get('accountName')} "
              f"| {a.get('accountType')} | saldo {bal.get('balance')} "
              f"{a.get('currency')} | disponibile {bal.get('available')}{star}")

    print("\n→ Ricerca strumento 'US 500':")
    markets = client.search_markets("US 500")
    if not markets:
        print("   (nessun risultato — provo 'S&P 500')")
        markets = client.search_markets("S&P 500")
    for m in markets[:12]:
        print(f"   - {m.get('epic'):28s} | {m.get('instrumentName')} "
              f"| {m.get('instrumentType')} | expiry={m.get('expiry')}")

    if epic:
        print(f"\n→ Dettagli epic configurato ({epic}):")
        det = client.get_market(epic)
        if det:
            instr = det.get("instrument", {})
            rules = det.get("dealingRules", {})
            snap = det.get("snapshot", {})
            print(f"   nome        : {instr.get('name')}")
            print(f"   tipo        : {instr.get('type')}")
            print(f"   valuta      : {instr.get('currencies')}")
            print(f"   min size    : {rules.get('minDealSize')}")
            print(f"   status      : {snap.get('marketStatus')} "
                  f"| bid={snap.get('bid')} offer={snap.get('offer')}")
        else:
            print("   ⚠️ epic non trovato/valido — useremo uno dei risultati "
                  "della ricerca qui sopra.")

    client.logout()
    print("\n✅ Connessione IG verificata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
