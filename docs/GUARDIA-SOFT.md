# GUARDIA SOFT — contesto di mercato che MODULA, mai blocca

Integrazione del **Gamma-Regime-Divergence-Scanner** (repo dell'utente) + la
**stagionalità storica** come guardia del programma opzioni.

> **I 3 principi (inviolabili, decisi 14 lug 2026):**
> 1. **Si opera OGNI mese.** La guardia non dice mai "non operare": nei regimi
>    brutti passa a "regimi più larghi" (strike più difensivi) e/o size ridotta
>    — mai a zero. Vietato aspettare crolli per mesi/anni.
> 2. **Il codice dello scanner è la fonte.** Si legge il suo output giornaliero
>    (`data/cache/market_state_spy.json`); l'eventuale refresh usa il SUO
>    run_engine (il suo ingestion Yahoo con cache anti-ban). Mai fetch nostri.
> 3. **Guasto = neutro.** Scanner assente o stantio → nessuna modulazione +
>    warning. La guardia non può mai fermare il trading system.

## Come decide

```
score effettivo = risk_score scanner (0-100)
                + 10 se regime UNWIND
                + 10 se mese di ESPOSIZIONE storicamente debole
                −  5 se mese storicamente forte
```

Il **mese di esposizione** = oggi + 18 giorni (il centro-vita di un mensile
aperto oggi): un trade aperto a metà luglio viene giudicato sulla stagionalità
di AGOSTO — è il mese in cui vive davvero.

| Score effettivo | Livello | Put-spread (EDGE #2) | Call spread (EDGE #3) | Size |
|---|---|---|---|---|
| < 40 | **NORMALE** | short 1.5σ / ala 2.5σ | ATM / +1σ | piena |
| 40-70 | **PRUDENTE** | short 2.0σ / ala 3.0σ (più lontano) | +0.5σ / +1.5σ (meno premio a rischio) | piena |
| > 70 | **DIFENSIVO** | come PRUDENTE | come PRUDENTE | ×0.5 (**mai sotto 1 contratto**) |

Ogni decisione è loggata con le sue ragioni ("risk score 42, regime TRANSITION ·
stagionalità agosto debole (+10) → PRUDENTE").

## La stagionalità — la TABELLA CANONICA 1950-2024 (75 anni), non i nostri 19

Fonte primaria del bias = le statistiche storiche PUBBLICHE e note dell'S&P
(75 anni): **deboli feb/giu/ago/set** (settembre il peggiore: positivo solo 45%,
media −0.7%) · **forti mar/apr/nov/dic** (aprile +1.5% e 70% positivi, dicembre
73% positivi). I nostri dati IG 2007-2026 compaiono nella nota come CONTROPROVA
(e confermano: set −0.7% anche da noi) ma non decidono il bias.
Regole dichiarate: debole = media <+0.3% E positivi <57%; forte = media ≥+1.0%
E positivi ≥60%. Tabella completa: `python src/guard/seasonality.py`.
*(L'intuizione dell'utente sul trade di agosto è confermata da 75 anni di
storia: agosto media +0.0%, positivi 54% → la guardia lo rende PRUDENTE.)*

## Dove gira e come si configura

- Modulo: `src/guard/` (`gamma_guard.py` + `seasonality.py`); collegato in
  `run_spread.py` → il blocco `GUARDIA` compare in ogni run (anche nel container).
- Lo scanner viene cercato in `GAMMA_SCANNER_DIR` (default: cartella sorella
  `../Gamma-Regime-Divergence-Scanner`). **Sul Raspberry**, dove lo scanner ha
  già il suo cron, basta montare la sua cache in sola lettura nel container
  opzioni (riga già predisposta in `deploy/sampler-opzioni/docker-compose.yml`).
- `GUARD_MODE=shadow` → la guardia LOGGA la sua decisione ma non modula
  (utile per confrontare cosa avrebbe fatto).

## Cosa resta da fare (onestà)

1. **Calibrazione delle soglie col backtest** (40/70, +10 stagionale, i
   parametri PRUDENTE): i valori v1 sono ragionevoli e dichiarati, non
   ottimizzati. Serve la serie storica del risk score (lo scanner la
   accumula in `signal_history_*.json`) per validarli come si deve.
2. ~~COPERTURA REATTIVA in-trade~~ — **TESTATA E FALSIFICATA (14 lug 2026)**
   in tutte le varianti (trigger 1.0-1.5σ, exit raffreddamento/scadenza,
   ±chiusura coordinata, con e senza 2008): l'85-90% delle rotture recupera
   (falsi allarmi) e comprare put durante il panico = pagare il pedaggio che
   normalmente incassiamo. Dettagli in [EDGE-falsificati.md](EDGE-falsificati.md).
   **La protezione resta: ala comprata all'ingresso + sizing + questa guardia.**
   Unico angolo non testato: trigger intraday (servono dati che non abbiamo).
3. Il pilot reale resta il giudice finale di tutto.
