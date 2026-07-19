# Architettura del bot IG — modulare, sicuro, monitorabile

Obiettivo: un bot che fa girare **strategie separate in moduli** (facile
aggiungerne), con esecuzione IG, gestione rischio, e **zero perdita di
tracciamento delle posizioni**. Riprende la filosofia di cryptoquantix
(registry, reconcile, kill switch) adattata a IG CFD.

> **Indice docs:** [INDICE.md](INDICE.md) · **Fix 19 lug:** [FIXLOG-2026-07-19.md](FIXLOG-2026-07-19.md)

> **Evoluzione multi-broker:** oggi l’esecuzione è accoppiata a IG. Il piano per
> astrarre il cuore e accettare **qualsiasi** broker conforme (adapter aperti;
> IBKR/tastytrade come prime prove) è in
> [PIANO-ASTRAZIONE-BROKER.md](PIANO-ASTRAZIONE-BROKER.md).

---

## 1. Modularità — aggiungere una strategia = 1 file

```
src/
├── core/
│   ├── ig_client.py        connessione + esecuzione IG (open/close/confirm/prezzi)
│   ├── order_manager.py    piazza ordini, conferma fill, retry, idempotenza
│   ├── position_store.py   stato persistente posizioni (SQLite) + reconcile IG
│   ├── risk_manager.py     sizing CFD, leva, kill switch, cap esposizione
│   ├── market_hours.py     RTH USA (09:30–16:00 NY) per il bot CFD
│   ├── health_check.py     ping IG + allarme LOG (no flat automatico) — #9
│   └── scheduler.py        loop: quando valutare segnali / gestire posizioni
├── strategies/
│   ├── base_strategy.py    INTERFACCIA (già esiste): scan() / manage() / exits
│   ├── dip_buy.py          EDGE #1 (mean-reversion intraday, exit su segnale)
│   └── <nuova>.py          basta implementare BaseStrategy + registrare in config
├── monitoring/
│   ├── dashboard.py        Streamlit: posizioni live, P&L, reconcile, storico
│   └── alerts.py           Telegram/log su eventi critici
└── bot.py                  entrypoint: carica strategie abilitate, avvia loop
```

**Aggiungere una strategia:** crei `src/strategies/mia.py` che estende
`BaseStrategy` (definisce `scan()` → segnali, `manage_positions()` → uscite), la
abiliti nel `.env` (`STRAT_MIA_ENABLED=true`), fine. Il bot la carica da un
**registry** che mappa config→classe. Nessun'altra modifica.

**Uscite flessibili (ogni strategia sceglie la sua):** il framework supporta
tutte — **signal-exit** (dip-buy: esci sul rimbalzo), **SL/TP nativi IG**
(attaccati all'apertura via `/positions/otc`), **trailing stop** (per trend).
La strategia dichiara quale usa. ⚠️ Il dip-buy NON usa stop stretti (peggiorano
la MR, testato) — usa signal-exit + protezione a livello di CONTO (kill switch).

---

## 2. LE COSE IMPORTANTI — checklist di sicurezza (non perdere il controllo)

Questo è ciò che separa un bot che sopravvive da uno che ti svuota il conto.

### A. Tracciamento posizioni (mai perderle)
- [ ] **Stato persistente** (`position_store.py`, SQLite): ogni posizione salvata
      con `dealId`, strategia, entry, size, timestamp. Sopravvive ai riavvii.
- [ ] **Reconcile all'avvio e ogni ciclo**: confronta il nostro stato con
      `GET /positions` di IG. Discrepanze → allarme, non trading alla cieca.
- [ ] **Orfani**: posizione su IG non nostra (chiudere/allarme) o nostra non su
      IG (già chiusa → aggiorna stato). Mai assumere.
- [ ] **Conferma OGNI ordine**: `dealReference` → `GET /confirms/{ref}`. Non dare
      per scontato il fill; gestisci REJECTED / partial / requote.
- [ ] **Idempotenza**: un segnale non deve generare 2 ordini (chiave anti-doppione,
      controllo "ho già una posizione per questa strategia").

### B. Rischio (non saltare)
- [ ] **Kill switch giornaliero**: −X% in un giorno → stop nuovi ingressi.
- [ ] **Cap esposizione lorda** aggregata di TUTTE le strategie (leva totale ≤ N).
- [ ] **Sizing per-rischio** coerente con la leva scelta (2-3x), size min IG.
- [ ] **Max posizioni aperte** contemporanee.
- [x] **Protezione API-down** (issue #9): se IG non risponde per > T secondi →
      allarme forte in LOG. Flat automatico **escluso** (solo telemetria).

### C. Operatività
- [ ] **Orari di mercato**: il dip-buy è intraday RTH — non piazzare a mercato
      chiuso (IG rifiuta / EDITS_ONLY). Rispetta apertura/chiusura + DST.
- [ ] **Retry con backoff** su errori transitori (già in `ig_client`); non su
      errori logici (ordine rifiutato per regola).
- [ ] **Slippage/spread reale vs backtest**: logga spread e fill reali, confronta.
      Se lo spread IG reale è > assunto (1pt) l'edge si assottiglia → monitorare.
- [ ] **Audit log**: ogni azione (segnale, ordine, fill, uscita, errore) su file
      + SQLite. Per debugging e per fidarti dei numeri.
- [ ] **Clock/sync**: usa timestamp UTC coerenti (segnali su barre chiuse).

### D. Dashboard (monitoraggio)
- [ ] Posizioni live + P&L non realizzato; **reconcile in rosso** se orfani/mismatch.
- [ ] Stato kill switch, esposizione/leva usata, per-strategia on/off.
- [ ] Storico trade con P&L, R, motivo uscita; equity curve; export CSV.
- [ ] Azioni manuali (doppia conferma): kill switch, chiusura reduce-only.

---

## 3. Stato di costruzione

1. ✅ **`ig_client` esecuzione** (open/close/confirm/get_positions/prezzi).
2. ✅ **`position_store` + reconcile** — spina dorsale sicurezza (SQLite).
3. ✅ **`order_manager`** (conferma fill, retry, idempotenza) + **`risk_manager`**
   (sizing CFD leva, kill switch, cap esposizione).
4. ✅ **`dip_buy.py`** (EDGE #1) — prima strategia modulare.
5. ✅ **`bot.py`** — loop reconcile → decide → esegui (gira end-to-end su demo).
6. ✅ **dashboard** (`src/monitoring/dashboard.py`): operativo + analisi regime.
7. ⏳ **Paper trading su demo** (a mercato aperto) → confronto col backtest → live.
8. ⏳ (opzionale) alert Telegram; nuove strategie da INDICE-EDGE.md.

Deploy: Docker (`docker compose up -d --build`), guida in [DEPLOY.md](DEPLOY.md).

**Principio:** prima la SICUREZZA (2A/2B), poi le strategie. Un bot con leva che
perde il tracciamento delle posizioni è più pericoloso di nessun bot.
