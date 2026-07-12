"""
Read Dukascopy tick files already cached by scripts/download_us500_dukascopy.py
and aggregate them to OHLC bars at any timeframe — WITHOUT re-downloading.

The download caches raw per-hour tick .bi5 files under data/research/duka_cache/.
Because those hold ticks, we can build 1-MINUTE bars (needed for intraday
session research: sweeps and reclaims live below the hour) from the exact same
files that produced the hourly TB dataset. Network-free: only reads the cache.
"""
import lzma
import os
import struct
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pandas as pd

INSTR = "USA500IDXUSD"
CACHE = os.path.join("data", "research", "duka_cache")
_REC = struct.Struct(">IIIff")
_SCALE = 1000.0


def _cache_path(dt: datetime) -> str:
    return os.path.join(CACHE, INSTR, str(dt.year), f"{dt.month - 1:02d}",
                        f"{dt.day:02d}", f"{dt.hour:02d}h.bi5")


def _minute_bars(raw: bytes, hour_start_ms: int) -> List[dict]:
    """Aggregate one hour's ticks into up to 60 one-minute mid-price bars."""
    if not raw:
        return []
    try:
        buf = lzma.decompress(raw)
    except Exception:
        return []
    n = len(buf) // 20
    bucket = {}  # minute_ms -> [o, h, l, c, vol, ntick]
    for i in range(n):
        ms, ask, bid, av, bv = _REC.unpack_from(buf, i * 20)
        mid = (ask + bid) / 2.0 / _SCALE
        m_ms = hour_start_ms + (ms // 60_000) * 60_000
        b = bucket.get(m_ms)
        if b is None:
            bucket[m_ms] = [mid, mid, mid, mid, av + bv, 1]
        else:
            if mid > b[1]:
                b[1] = mid
            if mid < b[2]:
                b[2] = mid
            b[3] = mid
            b[4] += av + bv
            b[5] += 1
    return [{"ts_ms": k, "open": v[0], "high": v[1], "low": v[2],
             "close": v[3], "volume": v[4], "n_ticks": v[5]}
            for k, v in bucket.items()]


def load_bars(date_from: str, date_to: str, tf: str = "1m",
              instr: str = INSTR) -> pd.DataFrame:
    """Build OHLC bars from cached ticks for [date_from, date_to).

    date_from/date_to: 'YYYY-MM-DD'. tf: '1m' or '1h'. Missing (not-yet-
    downloaded) hours are skipped silently. Returns a UTC-indexed DataFrame
    with columns open/high/low/close/volume/n_ticks (oldest first)."""
    global INSTR
    saved = INSTR
    INSTR = instr
    try:
        start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        rows: List[dict] = []
        cur = start
        while cur < end:
            cp = _cache_path(cur)
            if os.path.exists(cp):
                with open(cp, "rb") as f:
                    raw = f.read()
                hour_ms = int(cur.timestamp() * 1000)
                rows.extend(_minute_bars(raw, hour_ms))
            cur += timedelta(hours=1)
    finally:
        INSTR = saved

    if not rows:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "n_ticks"],
            index=pd.DatetimeIndex([], tz="UTC", name="ts"))

    df = pd.DataFrame(rows).drop_duplicates("ts_ms").sort_values("ts_ms")
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df.set_index("ts")[["open", "high", "low", "close", "volume", "n_ticks"]]

    if tf == "1m":
        return df
    if tf == "1h":
        agg = df.resample("1h").agg(
            open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"),
            volume=("volume", "sum"), n_ticks=("n_ticks", "sum")).dropna()
        return agg
    raise ValueError(f"unsupported tf {tf!r} (use '1m' or '1h')")


# Full span of the downloaded US500 tick cache (adjust if extended)
_FULL_FROM, _FULL_TO = "2022-01-01", "2026-07-11"
_PKL = os.path.join("data", "research", "us500_1m.pkl")


def load_1m_cached(date_from: str, date_to: str,
                   cache_file: str = _PKL) -> pd.DataFrame:
    """Fast 1m loader: decompress the whole tick cache ONCE into a pickle, then
    slice. First call is slow (builds the pickle); later calls load in <1s.
    Delete the pickle after extending the download to force a rebuild."""
    if os.path.exists(cache_file):
        df = pd.read_pickle(cache_file)
    else:
        df = load_bars(_FULL_FROM, _FULL_TO, "1m")
        try:
            df.to_pickle(cache_file)
        except Exception:
            pass
    lo = pd.Timestamp(date_from, tz="UTC")
    hi = pd.Timestamp(date_to, tz="UTC")
    return df[(df.index >= lo) & (df.index < hi)]
