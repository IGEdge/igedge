"""
IGEdge — bot.py, entrypoint. Loop: reconcile → decide → esegui.

Modulare: le strategie abilitate (DIP_BUY_ENABLED, ...) si caricano da un
registry; aggiungerne una = 1 modulo + 1 flag nel .env.

SICUREZZA prima di tutto (docs/ARCHITETTURA-BOT.md):
  - DEFAULT PLAN-ONLY: logga cosa farebbe, NESSUN ordine (issue #5 — parità col
    path opzioni). Ordini solo armando: --arm (demo) / --arm
    --i-understand-live-risk (LIVE); equivalenti env: BOT_ARM,
    BOT_I_UNDERSTAND_LIVE_RISK (per il container).
  - reconcile con IG a OGNI ciclo (position_store) prima di operare;
  - kill switch giornaliero + cap esposizione (risk_manager);
  - conferma di ogni ordine + idempotenza (order_manager);
  - health-check API (issue #9): ping periodico + allarme LOG se down;
    MAI flat automatico (solo telemetria).

Uso:
  python bot.py            # loop PLAN-ONLY (nessun ordine, logga il piano)
  python bot.py --once     # un solo ciclo (per test)
  python bot.py --arm                            # DEMO: invia ordini
  python bot.py --arm --i-understand-live-risk   # LIVE: invia ordini
"""
import argparse
import logging
import os
import sys

for _s in (sys.stdout, sys.stderr):    # console Windows cp1252 → UTF-8 (emoji nei log)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

from src.core.health_check import HealthCheck
from src.core.ig_client import IGClient
from src.core.order_manager import OrderManager
from src.core.position_store import PositionStore
from src.core.risk_manager import RiskManager
from src.strategies.dip_buy import DipBuyStrategy

os.makedirs("logs", exist_ok=True)
from logging.handlers import RotatingFileHandler  # noqa: E402
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        RotatingFileHandler("logs/bot.log", maxBytes=5 * 1024 * 1024,
                            backupCount=3, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("bot")


def _env_bool(k, d=False):
    return os.getenv(k, str(d)).lower() == "true"


def load_strategies(ig) -> list:
    """Registry: flag env -> istanza strategia. Aggiungerne una qui + nel .env."""
    strats = []
    if _env_bool("DIP_BUY_ENABLED", True):
        strats.append(DipBuyStrategy(ig, {
            "epic": os.getenv("DIP_EPIC", os.getenv("IG_EPIC")),
            "entry_rsi": os.getenv("DIP_ENTRY_RSI", 10),
            "exit_rsi": os.getenv("DIP_EXIT_RSI", 70),
            "exit_ma": os.getenv("DIP_EXIT_MA", 10),
            "add_rsi": os.getenv("DIP_ADD_RSI", 5),
            "scale_in": os.getenv("DIP_SCALE_IN", 2),
            "leverage": os.getenv("DIP_LEVERAGE", 3.0),
            # issue #4: ora CABLATI (il loop li applica: eod-flat + time-exit)
            "intraday": os.getenv("DIP_INTRADAY", "true"),
            "max_hold_days": os.getenv("DIP_MAX_HOLD_DAYS", 10),
        }))
    return strats


def _held_days(open_pos, now=None):
    """Giorni dall'inizio EPISODIO = entry_ts più vecchio tra le unità aperte."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    days = 0
    for p in open_pos:
        try:
            ts = datetime.fromisoformat(p["entry_ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            days = max(days, (now - ts).days)
        except (KeyError, TypeError, ValueError):
            continue
    return days


def _close_all(om, open_pos, reason, armed, name):
    if not armed:
        logger.warning(f"[{name}] 🟢 PLAN-ONLY: avrebbe CHIUSO {len(open_pos)} "
                       f"unità (reason={reason}) — nessun ordine. Se hai posizioni "
                       f"vere aperte, riavvia ARMATO o chiudi a mano!")
        return
    for p in open_pos:
        om.close(p, exit_reason=reason)


def cycle(ig, store, risk, om, strategies, armed=False, now=None):
    """Un ciclo: reconcile → orari → decide → esegui.

    armed=False (DEFAULT) = PLAN-ONLY: nessun ordine (issue #5).
    Orari (issue #12): niente ENTER/ADD fuori RTH (09:30-16:00 New York).
    Intraday (issue #4): flat a fine giornata (eod_flat) + rientro mattutino
    finché l'exit-signal non scatta; time-exit a max_hold_days dall'inizio
    episodio. `now` iniettabile per i test."""
    from src.core.market_hours import is_rth, minutes_to_close
    flat_before_min = int(os.getenv("DIP_FLAT_BEFORE_CLOSE_MIN", 10))

    # 1. RECONCILE (mai operare alla cieca)
    rep = store.reconcile(ig.get_positions())
    if not rep["ok"]:
        logger.warning(f"[bot] reconcile: chiuse-esterne="
                       f"{len(rep['closed_externally'])} orfani="
                       f"{len(rep['orphans_on_ig'])}")

    rth = is_rth(now)
    m2c = minutes_to_close(now)

    for strat in strategies:
        try:
            open_pos = store.get_open(strat.name)
            intraday = bool(getattr(strat, "intraday", False))
            max_hold = int(getattr(strat, "max_hold_days", 0))

            # A. FLAT DI FINE GIORNATA (issue #4): in intraday, con posizioni
            #    aperte, fuori RTH o negli ultimi minuti → flat. Prima di tutto.
            if intraday and open_pos and (not rth or (m2c is not None
                                                      and m2c <= flat_before_min)):
                logger.info(f"[{strat.name}] EOD/fuori-RTH con {len(open_pos)} "
                            f"unità aperte → flat (intraday)")
                _close_all(om, open_pos, "eod_flat", armed, strat.name)
                continue

            has = len(open_pos) > 0
            action, info = strat.decide(has, n_units=len(open_pos))
            price = info.get("close", 0.0)
            logger.info(f"[{strat.name}] action={action} "
                        f"close={info.get('close')} rsi2={info.get('rsi2', 0):.1f}")

            # B. TIME-EXIT (issue #4): episodio più vecchio di max_hold_days
            if has and max_hold > 0 and action in ("HOLD", "ADD") \
                    and _held_days(open_pos, now) >= max_hold:
                logger.info(f"[{strat.name}] max_hold_days={max_hold} raggiunto "
                            f"→ EXIT forzata")
                action = "EXIT"

            if action in ("ENTER", "ADD"):
                # C. GATE ORARI (issue #12): mai aprire fuori RTH; in intraday
                #    non aprire a ridosso della chiusura
                if not rth:
                    logger.info(f"[{strat.name}] {action} SALTATO: fuori RTH "
                                f"(mercato USA chiuso)")
                    continue
                if intraday and m2c is not None and m2c <= flat_before_min:
                    logger.info(f"[{strat.name}] {action} SALTATO: mancano "
                                f"{m2c}' alla chiusura (flat imminente)")
                    continue
                # sizing per UNITÀ (issue #8): notional target spalmato su
                # 1+scale_in unità uguali, come nel backtest validato
                units_total = 1 + int(getattr(strat, "scale_in", 0))
                size = risk.size_for(price, strat.leverage, units=units_total)
                ok, why = risk.can_open(open_pos, price, size)
                if not ok:
                    logger.info(f"[{strat.name}] ingresso bloccato: {why}")
                    continue
                if not armed:
                    logger.info(f"[{strat.name}] 🟢 PLAN-ONLY: avrebbe fatto "
                                f"{action} BUY size={size} @~{price} "
                                f"(unità {len(open_pos)+1}/{units_total}) — "
                                f"nessun ordine (arma con --arm)")
                    continue
                # ADD = nuova unità distinta (issue #3); ENTER anti-doppione
                r = om.open(strat.epic, "BUY", size, strat.name,
                            allow_stack=(action == "ADD"))
                logger.info(f"[{strat.name}] {action} -> {r.get('ok')} "
                            f"{r.get('reason', '')}")

            elif action == "EXIT":
                _close_all(om, open_pos, "signal", armed, strat.name)

            elif action == "FLAT" and intraday and not has and rth \
                    and not (m2c is not None and m2c <= flat_before_min):
                # D. RIENTRO MATTUTINO (issue #4): l'episodio flattato ieri sera
                #    continua stamattina, finché l'EXIT-signal non scatta
                batch = store.last_eod_batch(strat.name, strat.epic)
                if batch:
                    a2, _ = strat.decide(True, n_units=len(batch))
                    if a2 == "EXIT":
                        logger.info(f"[{strat.name}] episodio intraday CONCLUSO "
                                    f"(exit-signal al mattino): nessun rientro")
                    else:
                        ep_start = min(p["entry_ts"] for p in batch)
                        n = len(batch)
                        units_total = 1 + int(getattr(strat, "scale_in", 0))
                        size = risk.size_for(price, strat.leverage,
                                             units=units_total)
                        ok, why = risk.can_open([], price, size * n)
                        if not ok:
                            logger.info(f"[{strat.name}] rientro bloccato: {why}")
                            continue
                        if not armed:
                            logger.info(f"[{strat.name}] 🟢 PLAN-ONLY: avrebbe "
                                        f"RIENTRATO {n} unità (episodio dal "
                                        f"{ep_start[:10]}) — nessun ordine")
                            continue
                        for i in range(n):
                            r = om.open(strat.epic, "BUY", size, strat.name,
                                        allow_stack=(i > 0), entry_ts=ep_start)
                            logger.info(f"[{strat.name}] RIENTRO unità {i+1}/{n} "
                                        f"-> {r.get('ok')} {r.get('reason', '')}")
        except Exception as e:
            logger.error(f"[{strat.name}] errore ciclo: {e}", exc_info=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="un solo ciclo")
    ap.add_argument("--arm", action="store_true",
                    help="INVIA ordini (default: plan-only). Su LIVE serve anche "
                         "--i-understand-live-risk")
    ap.add_argument("--i-understand-live-risk", action="store_true")
    ap.add_argument("--interval", type=int,
                    default=int(os.getenv("MONITORING_INTERVAL_MINUTES", 15)) * 60)
    args = ap.parse_args()

    load_dotenv()
    # ── gate di sicurezza (issue #5): DEFAULT plan-only; ordini solo armando.
    # Env equivalenti (container): BOT_ARM, BOT_I_UNDERSTAND_LIVE_RISK.
    acc_type = os.getenv("IG_ACC_TYPE", "DEMO").upper()
    is_live = acc_type == "LIVE"
    want_arm = args.arm or _env_bool("BOT_ARM")
    understood = args.i_understand_live_risk or _env_bool("BOT_I_UNDERSTAND_LIVE_RISK")
    armed = want_arm and (understood if is_live else True)
    if want_arm and not armed:
        logger.warning("⛔ arm IGNORATO: su LIVE serve anche --i-understand-live-risk "
                       "(o BOT_I_UNDERSTAND_LIVE_RISK=true). Resto in PLAN-ONLY.")
    logger.info(f"modalità: {'🔴 ARMATO (invierà ordini)' if armed else '🟢 PLAN-ONLY (nessun ordine)'}"
                f" — conto {acc_type}")

    ig = IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                  os.getenv("IG_PASSWORD"), os.getenv("IG_ACC_TYPE", "DEMO"),
                  os.getenv("IG_ACCOUNT_ID") or None)
    # issue #10: sessione PERSISTENTE (token riusati tra riavvii, mai login a
    # raffica → niente lockout) + THROTTLE su tutte le chiamate IG del ciclo.
    # File di sessione DEDICATO al login CFD (diverso dal login opzioni live).
    from src.options.session import PersistentIGSession
    from src.options.throttle import ThrottledClient
    sess = PersistentIGSession(
        ig, f"data/ig_session_cfd_{acc_type.lower()}.json")
    if not sess.ensure():
        logger.error("sessione IG non disponibile (login/token)"); return 1
    igt = ThrottledClient(ig, min_interval=float(os.getenv("CFD_THROTTLE_SEC", 2.5)))

    store = PositionStore(os.getenv("POSITIONS_DB", "data/positions.db"))
    risk = RiskManager(
        igt,
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", 0.03)),
        max_open_trades=int(os.getenv("MAX_OPEN_TRADES", 3)),
        max_gross_exposure=float(os.getenv("MAX_GROSS_EXPOSURE", 3.0)),
    )
    om = OrderManager(igt, store)
    strategies = load_strategies(igt)

    # issue #9: telemetria API — ping + CRITICAL in log se down oltre soglia.
    # Nessun flat / nessun blocco ingressi (falsi positivi di rete = danni).
    def _ig_probe() -> bool:
        try:
            accs = igt.get_accounts()
            return isinstance(accs, list) and len(accs) > 0
        except Exception:
            return False

    health = HealthCheck(
        _ig_probe,
        interval_sec=float(os.getenv("HEALTH_CHECK_INTERVAL_SEC", 5)),
        max_down_sec=float(os.getenv("MAX_API_DOWN_SEC", 30)),
    )
    health.tick(force=True)

    logger.info(f"bot avviato — strategie: {[s.name for s in strategies]} "
                f"| equity {risk.equity():.2f} "
                f"| health ogni {health.interval_sec:.0f}s "
                f"(allarme log @{health.max_down_sec:.0f}s, no flat)")

    try:
        while True:
            sess.keep_alive()          # issue #10: rinnova SOLO se serve
            health.tick()
            cycle(igt, store, risk, om, strategies, armed=armed)
            if args.once:
                break
            health.sleep_while_monitoring(args.interval)
    except KeyboardInterrupt:
        logger.info("stop richiesto")
    finally:
        store.close()
        # NIENTE logout (issue #10): la sessione resta viva e riusabile al
        # prossimo avvio — come nel path opzioni (evita login ripetuti/lockout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
