# Dati US500 (conversione IG)

Questi dataset sono **parte del progetto** e vanno conservati: i backtest li
leggono da qui e **non serve riscaricarli** ogni volta. I downloader sono
idempotenti (vedi sotto).

## Dataset primari (US500)

| File / cartella | Cosa | Fonte | Dimensione |
|---|---|---|---|
| `us500_daily.csv` | Barre **daily** OHLC 2007→2026 (~5000) | IG `/prices` (mid bid/ask) | ~350 KB |
| `duka_cache/USA500IDXUSD/` | **Cache tick** grezza (file `.bi5` per ora) | Dukascopy | ~164 MB → ~500 MB a fine download |
| `us500_h1.csv` | Barre **orarie** 2022→2026 (per TB backtest) | aggregato dalla cache tick | ~1.7 MB |
| `us500_1m.pkl` | Barre **1 minuto** 2022→2026 (cache veloce, pickle) | aggregato dalla cache tick | ~85 MB |

Il `us500_1m.pkl` è la cache 1m per la ricerca sessioni/intraday: si costruisce
la prima volta (decomprime la cache tick, ~10 min) poi carica in <1s. Cancellarlo
per forzare la ricostruzione dopo aver esteso il download.

### Struttura della cache Dukascopy
```
duka_cache/USA500IDXUSD/{ANNO}/{MESE-1}/{GIORNO}/{ORA}h.bi5
```
Il **mese è 0-indicizzato** (00=gennaio … 11=dicembre), convenzione Dukascopy.
Ogni file è LZMA-compresso (tick: ms, ask, bid, volAsk, volBid; prezzo /1000).
File da 0 byte = ora di mercato chiusa (marcatore per non riscaricare).

## Perché NON si riscarica

- **Dukascopy** (`scripts/download_us500_dukascopy.py`): prima di scaricare
  un'ora controlla se esiste già il `.bi5` in cache → se c'è, la salta.
  Riprendere/estendere è sicuro e veloce:
  ```
  python scripts/download_us500_dukascopy.py --from 2022-01-01 --to 2026-07-11
  ```
- **IG daily** (`scripts/download_us500_ig.py`): sovrascrive `us500_daily.csv`.
  Consuma quota dati IG (10k punti/settimana) → **rilanciare solo se serve**
  aggiornare, non a ogni run.
- Le barre orarie/1m si rigenerano dalla cache **senza rete**:
  `src/data/dukascopy_cache.py` → `load_bars(from, to, tf="1m"|"1h")`.

## Come i backtest leggono i dati
- `backtest_macro_core_us500.py` → `us500_daily.csv`
- `backtest_trend_breakdown_us500.py` → `us500_h1.csv` (orario) + `us500_daily.csv` (macro gate)
- `session_research_us500.py` → barre 1m via `dukascopy_cache.load_bars()` (dalla cache)

## Residui crypto (rimovibili, ~115 MB)
Dataset del vecchio progetto crypto, non più usati:
`btc_1m_4y/`, `eth_1m_4y/`, `btc_1m_research.json.gz`, `btc_funding*.json`,
`eth_funding_4y.json`, `c4_trades_cache.pkl`, `new_strategies_results.json`,
i vari `*_report.txt` (+ in `data/`: `btc_1m_cache.json`, `positioning_history.db`,
`journal_test.db`, `smart_money_state.json`, `raw/`). Si possono eliminare.
