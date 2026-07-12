#!/usr/bin/env python3
"""
Download US500 (USA500IDXUSD) intraday history from Dukascopy and aggregate to
HOURLY OHLC bars. Free, deep history, no IP blocking — the source the idea doc
recommends. Node's dukascopy-node couldn't connect here (undici), but Python +
truststore reaches the datafeed fine.

Dukascopy serves LZMA-compressed tick files, one per hour:
  {BASE}/{INSTR}/{YYYY}/{MM0}/{DD}/{HH}h_ticks.bi5   (MM0 = month-1, 0-indexed)
Each 20-byte record (big-endian): ms_in_hour, ask, bid, askVol, bidVol.
Index prices are integers scaled by 1000. We aggregate mid=(bid+ask)/2 per hour.

Files are cached under data/research/duka_cache/ (0-byte marker for closed
hours) so re-runs are instant and resumable.

Usage:
  python scripts/download_us500_dukascopy.py --from 2019-01-01 --to 2026-07-10
  python scripts/download_us500_dukascopy.py --from 2024-06-03 --to 2024-06-04 --out data/research/us500_h1_sample.csv
"""
import argparse
import lzma
import os
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import truststore  # noqa: E402

truststore.inject_into_ssl()
import pandas as pd  # noqa: E402
import requests  # noqa: E402

INSTR = "USA500IDXUSD"
BASE = "https://datafeed.dukascopy.com/datafeed"
CACHE = os.path.join("data", "research", "duka_cache")
REC = struct.Struct(">IIIff")
SCALE = 1000.0

_tls = threading.local()


def _session() -> requests.Session:
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        _tls.s = s
    return s


def _url(dt: datetime) -> str:
    return f"{BASE}/{INSTR}/{dt.year}/{dt.month - 1:02d}/{dt.day:02d}/{dt.hour:02d}h_ticks.bi5"


def _cache_path(dt: datetime) -> str:
    return os.path.join(CACHE, INSTR, str(dt.year), f"{dt.month - 1:02d}",
                        f"{dt.day:02d}", f"{dt.hour:02d}h.bi5")


def _fetch_raw(dt: datetime, tries: int = 5) -> bytes:
    """Return raw bi5 bytes (b'' = closed hour). Cached, resumable."""
    cp = _cache_path(dt)
    if os.path.exists(cp):
        with open(cp, "rb") as f:
            return f.read()
    url = _url(dt)
    for k in range(tries):
        try:
            r = _session().get(url, timeout=25)
            if r.status_code == 404:
                data = b""
            elif r.status_code == 200:
                data = r.content
            else:
                raise requests.exceptions.RequestException(f"HTTP {r.status_code}")
            os.makedirs(os.path.dirname(cp), exist_ok=True)
            with open(cp, "wb") as f:
                f.write(data)
            return data
        except Exception:
            if k == tries - 1:
                return b"\x00"  # transient failure sentinel (not cached)
            time.sleep(1.0 + k)
    return b"\x00"


def _agg_hour(dt: datetime):
    """One hourly OHLC bar (mid prices) or None if the hour is closed/empty."""
    raw = _fetch_raw(dt)
    if raw == b"\x00":
        return ("ERR", dt)
    if not raw:
        return None
    try:
        buf = lzma.decompress(raw)
    except Exception:
        return None
    n = len(buf) // 20
    if n == 0:
        return None
    o = h = low = c = None
    vol = 0.0
    for i in range(n):
        _ms, ask, bid, av, bv = REC.unpack_from(buf, i * 20)
        mid = (ask + bid) / 2.0 / SCALE
        if o is None:
            o = h = low = mid
        h = mid if mid > h else h
        low = mid if mid < low else low
        c = mid
        vol += av + bv
    ts_ms = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return {"ts_ms": ts_ms, "open": o, "high": h, "low": low,
            "close": c, "volume": vol, "n_ticks": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="dfrom", required=True)
    ap.add_argument("--to", dest="dto", required=True)
    ap.add_argument("--out", default="data/research/us500_h1.csv")
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    start = datetime.strptime(args.dfrom, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.dto, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    hours = []
    cur = start
    while cur < end:
        hours.append(cur)
        cur += timedelta(hours=1)

    print(f"Dukascopy {INSTR} h1: {args.dfrom} → {args.dto}  "
          f"({len(hours):,} hour-slots, {args.workers} workers)")
    t0 = time.time()
    bars, errs, done = [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(_agg_hour, hours):
            done += 1
            if res is None:
                pass
            elif isinstance(res, tuple):
                errs += 1
            else:
                bars.append(res)
            if done % 2000 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done:,}/{len(hours):,}  bars={len(bars):,}  "
                      f"errs={errs}  {rate:.0f}/s", flush=True)

    if errs:
        print(f"⚠️  {errs} hours failed after retries (transient) — re-run to fill "
              f"(cached hours are skipped).")
    if not bars:
        print("❌ no bars collected")
        return 1

    df = pd.DataFrame(bars).drop_duplicates("ts_ms").sort_values("ts_ms")
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df[["ts", "open", "high", "low", "close", "volume", "n_ticks"]]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"✅ {len(df):,} hourly bars → {args.out}")
    print(f"   range: {df['ts'].iloc[0]} → {df['ts'].iloc[-1]}")
    print(f"   close: {df['close'].iloc[0]:.1f} → {df['close'].iloc[-1]:.1f}")
    print(f"   elapsed: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
