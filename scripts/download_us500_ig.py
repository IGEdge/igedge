#!/usr/bin/env python3
"""
Download US500 daily history from the IG demo /prices API and cache it to disk.

Why IG (not Yahoo/stooq): it is the EXACT instrument we will trade (no basis
mismatch), it is our own authenticated API (no third-party IP blocking), and
the weekly data allowance (10k points) comfortably covers ~21y of daily bars
(~5.3k). Run ONCE — the cached CSV is the source of truth for backtests.

Output: data/research/us500_daily.csv  (cols: ts, open, high, low, close, volume)
        mid prices (IG bid/ask averaged), oldest first.

Usage: python scripts/download_us500_ig.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

from src.core.ig_client import IGClient

OUT = "data/research/us500_daily.csv"
DATE_FROM = "2005-01-01T00:00:00"


def main() -> int:
    load_dotenv()
    epic = os.getenv("IG_EPIC")
    c = IGClient(
        os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
        os.getenv("IG_PASSWORD"), os.getenv("IG_ACC_TYPE", "DEMO"),
        os.getenv("IG_ACCOUNT_ID") or None,
    )
    if not c.login():
        print("❌ login failed")
        return 1

    # The v3 /prices endpoint silently caps at 20 bars/response; the v2
    # numPoints form returns the most-recent N in one shot. 5000 daily ≈ 20y.
    print(f"Fetching DAILY {epic}  (v2, last 5000 points) ...")
    res = c.get_prices_v2(epic, resolution="DAY", num_points=5000)
    bars = res["bars"]
    print(f"  bars: {len(bars)}   allowance: {res['allowance']}")
    if not bars:
        print("❌ no bars returned")
        c.logout()
        return 1

    df = pd.DataFrame(bars)
    # normalise IG 'YYYY/MM/DD HH:MM:SS' timestamps to UTC
    df["ts"] = pd.to_datetime(df["ts"], format="%Y/%m/%d %H:%M:%S", utc=True,
                              errors="coerce")
    df = df.dropna(subset=["ts"]).drop_duplicates("ts").sort_values("ts")
    df = df[["ts", "open", "high", "low", "close", "volume"]]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"✅ saved {len(df)} daily bars → {OUT}")
    print(f"   range: {df['ts'].iloc[0].date()} → {df['ts'].iloc[-1].date()}")
    print(f"   close: {df['close'].iloc[0]:.1f} → {df['close'].iloc[-1]:.1f}")
    c.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
