"""
IGEdge — bot.py, entrypoint. Loop: reconcile → decide → esegui.

Modulare: le strategie abilitate (DIP_BUY_ENABLED, ...) si caricano da un
registry; aggiungerne una = 1 modulo + 1 flag nel .env.

SICUREZZA prima di tutto (docs/ARCHITETTURA-BOT.md):
  - reconcile con IG a OGNI ciclo (position_store) prima di operare;
  - kill switch giornaliero + cap esposizione (risk_manager);
  - conferma di ogni ordine + idempotenza (order_manager).

Uso:
  python bot.py            # loop live (demo/live secondo IG_ACC_TYPE)
  python bot.py --once     # un solo ciclo (per test)
"""
import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv

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
        RotatingFileHandler("logs/bot.log", maxBytes=5 * 1024 * 1024, backupCount=3),
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
        }))
    return strats


def cycle(ig, store, risk, om, strategies):
    """Un ciclo: reconcile, poi per ogni strategia decide ed esegue."""
    # 1. RECONCILE (mai operare alla cieca)
    rep = store.reconcile(ig.get_positions())
    if not rep["ok"]:
        logger.warning(f"[bot] reconcile: chiuse-esterne="
                       f"{len(rep['closed_externally'])} orfani="
                       f"{len(rep['orphans_on_ig'])}")

    for strat in strategies:
        try:
            open_pos = store.get_open(strat.name)
            has = len(open_pos) > 0
            action, info = strat.decide(has, n_units=len(open_pos))
            price = info.get("close", 0.0)
            logger.info(f"[{strat.name}] action={action} "
                        f"close={info.get('close')} rsi2={info.get('rsi2', 0):.1f}")

            if action in ("ENTER", "ADD"):
                size = risk.size_for(price, strat.leverage)
                ok, why = risk.can_open(open_pos, price, size)
                if not ok:
                    logger.info(f"[{strat.name}] ingresso bloccato: {why}")
                    continue
                r = om.open(strat.epic, "BUY", size, strat.name)
                logger.info(f"[{strat.name}] {action} -> {r.get('ok')} "
                            f"{r.get('reason', '')}")
            elif action == "EXIT":
                for p in open_pos:
                    om.close(p, exit_reason="signal")
        except Exception as e:
            logger.error(f"[{strat.name}] errore ciclo: {e}", exc_info=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="un solo ciclo")
    ap.add_argument("--interval", type=int,
                    default=int(os.getenv("MONITORING_INTERVAL_MINUTES", 15)) * 60)
    args = ap.parse_args()

    load_dotenv()
    ig = IGClient(os.getenv("IG_API_KEY"), os.getenv("IG_IDENTIFIER"),
                  os.getenv("IG_PASSWORD"), os.getenv("IG_ACC_TYPE", "DEMO"),
                  os.getenv("IG_ACCOUNT_ID") or None)
    if not ig.login():
        logger.error("login IG fallito"); return 1

    store = PositionStore(os.getenv("POSITIONS_DB", "data/positions.db"))
    risk = RiskManager(
        ig,
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", 0.03)),
        max_open_trades=int(os.getenv("MAX_OPEN_TRADES", 3)),
        max_gross_exposure=float(os.getenv("MAX_GROSS_EXPOSURE", 3.0)),
    )
    om = OrderManager(ig, store)
    strategies = load_strategies(ig)
    logger.info(f"bot avviato — strategie: {[s.name for s in strategies]} "
                f"| equity {risk.equity():.2f}")

    try:
        while True:
            cycle(ig, store, risk, om, strategies)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("stop richiesto")
    finally:
        store.close()
        ig.logout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
