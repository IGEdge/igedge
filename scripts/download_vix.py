#!/usr/bin/env python3
"""
Download the CBOE VIX daily history (free, official) for the VRP probe.
Uses truststore (OS trust store) for the corporate-proxy TLS on this machine.
Saves data/research/vix_daily.csv (ts, open, high, low, close).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import io
import pandas as pd
import requests

URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
OUT = "data/research/vix_daily.csv"


def main():
    print(f"Scarico VIX da CBOE...\n  {URL}")
    try:
        r = requests.get(URL, timeout=60,
                         headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        print(f"❌ download fallito (proxy/TLS?): {e}")
        print("  → scaricalo a mano dal browser e salvalo come", OUT)
        return 1
    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}")
        return 1
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = [c.strip().lower() for c in df.columns]
    # CBOE columns: DATE, OPEN, HIGH, LOW, CLOSE
    df = df.rename(columns={"date": "ts"})
    df["ts"] = pd.to_datetime(df["ts"])
    df = df[["ts", "open", "high", "low", "close"]].sort_values("ts")
    os.makedirs("data/research", exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"✅ salvato {OUT}  ({len(df)} righe, {df['ts'].min().date()} → "
          f"{df['ts'].max().date()})  ultimo VIX close={df['close'].iloc[-1]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
