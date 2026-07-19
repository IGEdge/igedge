#!/usr/bin/env python3
"""
Demone giornaliero del programma OPZIONI (per il container sul Raspberry).

Ogni giorno di borsa (lun-ven) alle SAMPLER_RUN_AT (default 16:30 Europe/Rome,
= 10:30 ET, mercato USA aperto) esegue in sequenza:

  1. refresh VIX + VIX3M dal CBOE  → data/research/{vix,vix3m}_daily.csv
  2. SAMPLER SKEW (gate edge #2/#3) → data/research/skew_samples.csv
  3. run_spread (--strat both --live) → controlla i segnali dei due edge.
     DEFAULT plan-only. Per aprire: OPTIONS_DAEMON_ARM=true +
     OPTIONS_DAEMON_I_UNDERSTAND_LIVE_RISK=true + allowlist
     OPTIONS_ARMED_STRATEGIES=... (es. putspread). Il demone NON hardcoda
     quale strategia aprire — lo decide la config.

Log: logs/sampler.log. Heartbeat per l'healthcheck: logs/sampler.heartbeat.
Retry: se il sampler fallisce (rete/festivo) ritenta ogni 30 min, max 3 volte.

  python scripts/sampler_daemon.py           # demone (loop infinito)
  python scripts/sampler_daemon.py --once    # esegue subito i job ed esce (test)
"""
import argparse
import io
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:                       # TLS via store di sistema (fix proxy/AV Windows; no-op su Linux)
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.getenv("TZ", "Europe/Rome"))
except Exception:
    TZ = None

LOG = "logs/sampler.log"
HEARTBEAT = "logs/sampler.heartbeat"
CBOE_H = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{sym}_History.csv"
PY = sys.executable


def now():
    return datetime.now(TZ) if TZ else datetime.now()


def log(msg):
    line = f"{now().isoformat(timespec='seconds')}  {msg}"
    print(line, flush=True)
    os.makedirs("logs", exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def heartbeat():
    os.makedirs("logs", exist_ok=True)
    with open(HEARTBEAT, "w") as f:
        f.write(now().isoformat())


def refresh_cboe():
    """VIX + VIX3M freschi dal CBOE (nessuna chiamata IG)."""
    import pandas as pd
    import requests
    ok = True
    for sym, path in [("VIX", "data/research/vix_daily.csv"),
                      ("VIX3M", "data/research/vix3m_daily.csv")]:
        try:
            r = requests.get(CBOE_H.format(sym=sym), timeout=30,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = [c.strip().lower() for c in df.columns]
            df = df.rename(columns={"date": "ts"})[["ts", "close"]].dropna()
            df.to_csv(path, index=False)
            log(f"refresh {sym}: {len(df)} righe (ultimo {df['ts'].iloc[-1]} = {df['close'].iloc[-1]})")
        except Exception as e:
            log(f"⚠️ refresh {sym} FALLITO: {e}")
            ok = False
    return ok


def run_script(args, name):
    log(f"── {name}: {' '.join(args)}")
    try:
        p = subprocess.run([PY] + args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
        for ln in (p.stdout or "").strip().splitlines():
            log(f"   {ln}")
        if p.returncode != 0:
            for ln in (p.stderr or "").strip().splitlines()[-8:]:
                log(f"   [err] {ln}")
            log(f"⚠️ {name} exit={p.returncode}")
            return False
        return True
    except Exception as e:
        log(f"⚠️ {name} eccezione: {e}")
        return False


def daily_jobs():
    log("════════ JOB GIORNALIERO — inizio ════════")
    refresh_cboe()
    retries = int(os.getenv("SAMPLER_RETRIES", "3"))
    ok = False
    for attempt in range(1, retries + 1):
        ok = run_script(["scripts/sample_skew_us500.py", "--live"],
                        f"sampler skew (tentativo {attempt}/{retries})")
        if ok:
            break
        if attempt < retries:
            log("   riprovo tra 30 minuti…")
            for _ in range(30):
                heartbeat(); time.sleep(60)
    if not ok:
        log("❌ sampler skew fallito oggi (festivo? rete?) — riproverò domani")
    # Gate demone: flag env generici. Quali strategie aprono = allowlist in
    # OPTIONS_ARMED_STRATEGIES (letta da run_spread) — zero hardcode qui.
    spread_args = ["scripts/run_spread.py", "--strat", "both", "--live"]
    daemon_arm = os.getenv("OPTIONS_DAEMON_ARM", "false").lower() == "true"
    daemon_ok = os.getenv("OPTIONS_DAEMON_I_UNDERSTAND_LIVE_RISK",
                          "false").lower() == "true"
    if daemon_arm and daemon_ok:
        spread_args += ["--arm", "--i-understand-live-risk"]
        allow = os.getenv("OPTIONS_ARMED_STRATEGIES", "").strip() or "(vuota→plan-only)"
        log(f"gate demone ARMATO — allowlist={allow}")
    else:
        if daemon_arm and not daemon_ok:
            log("⚠️ OPTIONS_DAEMON_ARM=true ma manca "
                "OPTIONS_DAEMON_I_UNDERSTAND_LIVE_RISK — resto plan-only")
        log("gate demone plan-only (nessun ordine)")
    run_script(spread_args, "run_spread (segnali edge #2/#3)")
    log("════════ JOB GIORNALIERO — fine ════════")


def next_run():
    hh, mm = (os.getenv("SAMPLER_RUN_AT", "16:30")).split(":")
    t = now().replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if t <= now():
        t += timedelta(days=1)
    while t.weekday() >= 5:          # sab/dom → lunedì
        t += timedelta(days=1)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="esegui subito ed esci")
    args = ap.parse_args()
    if args.once:
        heartbeat()
        daily_jobs()
        return 0
    log(f"demone avviato — orario giornaliero: {os.getenv('SAMPLER_RUN_AT', '16:30')} "
        f"({os.getenv('TZ', 'Europe/Rome')}), solo lun-ven")
    while True:
        t = next_run()
        log(f"prossima esecuzione: {t.isoformat(timespec='minutes')}")
        while now() < t:
            heartbeat()
            time.sleep(60)
        daily_jobs()


if __name__ == "__main__":
    raise SystemExit(main())
