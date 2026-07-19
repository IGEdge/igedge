# Rename Condor → Spread (issue #16)

> Aggiornato: **19 luglio 2026**. Indice: [INDICE.md](INDICE.md).

## Perché

L’iron condor come **strategia** è falsificato. L’infrastruttura multi-gamba
serve a put/call spread. I nomi “condor” erano fuorvianti.

## Fatto (senza cambiare la logica di trading)

| Nuovo | Alias vecchio (compat) |
|-------|-------------------------|
| `OptionSpread` (`spread.py`) | `Condor` |
| `SpreadStore` | `CondorStore` |
| `SpreadExecutor` / `open_spread` / `close_spread` | `CondorExecutor` / `open_condor` / `close_condor` |
| `SpreadMonitor` | `CondorMonitor` |
| `scripts/monitor_spreads.py` | stub `monitor_condors.py` (deprecato) |
| log `options.log` + `options_audit.jsonl` | dual-write anche su `condor.*` |
| DB file default `spreads.db` | fallback automatico a `condors.db` se esiste |

Test mock: `test_condor_executor.py`, `test_condor_monitor.py`, `test_arming_policy.py` → OK.

## Ancora da fare (issue #16 resta aperta)

- Tabelle SQL ancora `condors` / `condor_legs` (scelta anti-regressione sul Pi)
- `run_condor.py` / `orchestrator.py` non spostati in `legacy/`
- Nomi funzione `resolve_condor_epics*` ancora presenti (aggiunti alias `resolve_spread_epics*`)
- Docs storiche OK così; docs operative da ripulire progressivamente
- Rimuovere alias dopo un ciclo di stabilità

## Comandi

```bash
python scripts/monitor_spreads.py --live
python scripts/run_spread.py --strat both --live   # usa SpreadStore/Executor
```
