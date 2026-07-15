# STATO DEL PROGETTO — checkpoint del 15 luglio 2026

> **Perché questo file:** fotografia di dove siamo, cosa gira da solo, e cosa
> fare quando riprendiamo (~5 agosto 2026, dopo 3 settimane di campioni).

---

## COSA GIRA DA SOLO, ADESSO (nessuna azione richiesta)

Sul **Raspberry** (`antonio@raspberrypi`, repo in `~/Documents/igedge`):
container **igedge-sampler** attivo — ogni giorno di borsa alle **16:30** fa:

1. **Refresh VIX + VIX3M** dal CBOE (2 chiamate);
2. **Campione dello SKEW IG** (~14 chiamate throttlate, read-only) →
   `data/research/skew_samples.csv`. **È IL GATE**: decide se gli edge opzioni
   vanno al pilot;
3. **Controllo segnali** dei 2 edge (plan-only, MAI ordini) con la **GUARDIA
   SOFT** attiva: scanner gamma dell'utente (`/home/antonio/gamma-data/cache`,
   montato ro) + stagionalità canonica 1950-2024.

**Verificato dal vivo il 15 lug:** guardia → risk 51 + agosto debole = PRUDENTE
→ call spread spostato da 7600/8000 (rischio €107) a 7800/8200 (rischio €32),
**operando comunque** (mai blocchi — principio fondante).

**Campioni skew finora: 3** — atm_ratio 0.775/0.788/0.797 (modello: 0.77),
put_slope 0.30-0.33 (modello: 0.30) → **il modello regge**.

---

## GLI EDGE — stato al 15 lug 2026 (dettagli: INDICE-EDGE.md)

| Edge | Stato | Numeri chiave | Cosa manca |
|---|---|---|---|
| **#2 vendi put post-panico** | 🟡 validato | ~4/anno, +2.7%/trade, 1 perdita in 59 (2009-26) | gate skew + pilot |
| **#3 compra call in uptrend** | 🟨 backtest forte | ~11/anno, t=+3.0, €110/anno su €1k | stesso gate + pilot |
| **#1 dip-buy + ensemble C1** | ✅ validato | +27%/anno a 3x, maxDD 30% | ⚠️ capital-gated: serve ≥€2.5k |
| Guardia soft | ✅ attiva | modula, mai blocca | calibrare soglie (v1 non calibrate) |
| Copertura reattiva | ❌ falsificata (15 lug) | +2.7%→≈0 in tutte le varianti | (angolo intraday = solo col pilot) |

Falsificati e chiusi: iron condor, tail-hedge, 13 idee CFD — lista in EDGE-falsificati.md.

---

## ✅ CHECKLIST ALLA RIPRESA (~5 agosto 2026)

1. **Dal PC:** `deploy\sampler-opzioni\pull-data.bat` → scarica campioni + log
   dal Pi e stampa il **verdetto del gate** (`--report`).
2. **Gate CHIUSO se:** ~15+ campioni E atm_ratio medio ≤ 0.82 E put_slope ~0.30.
   - Se sì → **PILOT**: 1 contratto vero (rischio ~€30-110) con
     `python scripts/run_spread.py --strat <...> --live --arm --i-understand-live-risk`
     — solo con autorizzazione esplicita di Antonio. È **la prova vera**:
     fill/spread/settlement reali vs modello. Nessun edge è "provato" prima.
   - Se atm_ratio medio > 0.82 → rifare i conti dei backtest coi rapporti medi
     veri prima di ogni pilot.
3. **Controllare che il demone abbia girato davvero** ogni giorno:
   `tail logs/sampler-pi.log` (scaricato dal pull) — buchi = giorni festivi ok,
   buchi lunghi = container fermo.
4. **Verificare freschezza scanner** (la guardia lo dice da sola nei log:
   "stato scanner VECCHIO" = il cron del gamma scanner è fermo).
5. **Lavori paralleli disponibili per Claude:** calibrazione soglie guardia con
   `signal_history_*.json` dello scanner · integrazione più profonda dei dati
   scanner (muri, confluence) come modulatori · se capitale ≥€2.5k: attivazione
   ensemble CFD (EDGE #1).

---

## PRINCIPI PERMANENTI (non rinegoziabili, decisi da Antonio)

- **Capitale**: €1.000 = pilot; obiettivo = edge che scala a €10k+ (reddito reale).
- **Si opera OGNI mese**: le guardie modulano (strike più larghi / size ridotta),
  MAI bloccano. Vietato aspettare crolli per mesi.
- **Nessun edge è provato senza fill reali** (lezione condor). Il backtest non basta.
- **Broker = IG e basta.** Yahoo solo attraverso il codice dello scanner (IP!).
- **Niente ordini senza `--arm --i-understand-live-risk`** + ok esplicito.
- I conti IG sono SEPARATI (CFD vs opzioni) → il sistema dovrà gestirli entrambi.
