# PIANO RISCRITTURA BOT — quali strategie e come (modulare, pulito, riusabile)

> Scritto il 15 lug 2026 su richiesta di Antonio, PRIMA della riscrittura, così
> le decisioni non si perdono. Da leggere insieme a
> [OPTION-CHAIN-IG.md](OPTION-CHAIN-IG.md) (metodo obbligatorio catena) e
> [STATO-PROGETTO.md](STATO-PROGETTO.md).

---

## 1. QUALI strategie entrano nel bot (e quali NO)

### ✅ DENTRO (in ordine di attivazione)

| # | Strategia | Conto | Regole (doc di riferimento) | Quando si attiva |
|---|---|---|---|---|
| 1 | **Put-spread post-panico** (EDGE #2) | opzioni (TVYYM) | entry: VIX≥20 in raffreddamento + VIX/VIX3M≤1 · short 1.5σ/ala 2.5σ · **HOLD-TO-EXPIRY SEMPRE** (C8-put: uscite anticipate falsificate) · guardia modula strike/size | dopo gate skew + pilot ok |
| 2 | **Call spread in uptrend** (EDGE #3) | opzioni (TVYYM) | entry: mensile se spot>SMA200 · ATM/+1σ · **uscita C8: chiudi a ≥60% ampiezza (≈2× debito)**, rientra se uptrend · guardia modula | stesso gate + pilot |
| 3 | **Dip-buy ensemble** (EDGE #1 + C1) | CFD (separato!) | trigger union t1-t5 + satellite short t6 · scale-in · niente stop stretti · intraday flat-overnight per leverare | quando equity CFD ≥ ~€2.500 |

### ❌ FUORI (mai implementare — già falsificati)
**Iron condor** (il lato call IG perde — `run_condor.py` marcato DEPRECATO, resta
solo come storia) · coperture reattive in-trade · uscite anticipate sul
put-spread · pre-FOMC (C4/C9) · weekly · tail-hedge preventivo. Lista completa
con i numeri: [EDGE-falsificati.md](EDGE-falsificati.md).

---

## 2. ARCHITETTURA MODULARE — i 4 strati (riusare, non riscrivere)

```
┌─ STRATO 4: SCHEDULER ─────────────────────────────────────────┐
│ un loop giornaliero: segnali → guardia → strategie → gates →  │
│ esecuzione (se armato) → gestione posizioni → log/persistenza │
├─ STRATO 3: STRATEGIE (un modulo per strategia, stessa API) ───┤
│ PutSpreadPostPanico · CallSpreadUptrend · DipBuyEnsemble      │
│ ogni modulo espone: signal() · build() · manage() · size()    │
├─ STRATO 2: CONTESTO (agnostico dalle strategie) ──────────────┤
│ src/guard/ (scanner gamma + stagionalità → modula, MAI blocca)│
│ segnali dati: CBOE (VIX/VIX3M), SMA200 locale, scanner cache  │
├─ STRATO 1: INFRASTRUTTURA IG (già pronta e collaudata) ───────┤
│ session (login 1 volta) · throttle (2.5s) · chain (costruz.   │
│ diretta epic) · executor (compra-prima, ritenta, mai nudi) ·  │
│ store SQLite (col. strategy) · monitor · audit log            │
└───────────────────────────────────────────────────────────────┘
```

**Il principio:** gli strati 1-2 sono GIÀ scritti e collaudati e sono
**agnostici**: qualunque strategia nuova li riusa senza toccarli. La
riscrittura riguarda solo lo strato 3 (interfaccia comune) e 4 (loop unico).

### L'interfaccia comune delle strategie (strato 3)

```python
class OptionStrategy:                      # una classe per strategia
    name: str                              # "putspread" | "callspread" | ...
    account: str                           # "options" | "cfd" (conti SEPARATI)

    def signal(self, ctx) -> Signal        # ctx = vix, ts_ratio, sma200, guardia…
                                           # → ok/skip + motivo (loggato sempre)
    def build(self, ctx, guard) -> list[Leg]   # gambe con strike/direzione
                                           # (guardia può allargare/ridurre)
    def size(self, ctx, capital) -> int    # contratti interi (1/€1000, mai 0)
    def manage(self, position, ctx) -> Action  # HOLD | CLOSE(reason)
                                           # putspread: sempre HOLD (a scadenza)
                                           # callspread: CLOSE se val ≥60% width
```

Oggi `spread_orchestrator.py` fa già plan/build/size per #1 e #2 in un'unica
classe: la riscrittura la SPACCA in moduli per-strategia quando se ne aggiunge
una terza — non prima (niente astrazione prematura).

### Cosa MANCA ancora da scrivere (la vera to-do della riscrittura)

1. **`manage()` nel monitor giornaliero**: oggi il monitor fa mark-to-market;
   deve anche applicare la regola d'uscita C8 della call (chiudi a ≥60%
   ampiezza — `close_condor` shorts-first già esiste e va bene per 2 gambe)
   e loggare valore reale vs modello (valida i mark mid-life).
2. **Check MARGINE pre-apertura**: leggere i fondi disponibili dal conto
   (API `/accounts`) e rifiutare l'apertura se l'impegno totale supererebbe
   il **50% del conto** (protezione anche se IG marginasse per-gamba).
3. **Allocazione per CONTO**: config esplicita `{options: €X, cfd: €Y}` —
   i conti IG sono separati, i trasferimenti li fa Antonio a mano, il bot
   deve sapere quanto ha DOVE e dimensionare per-conto.
4. **Scheduler unico** (estensione di `sampler_daemon.py`): oggi fa
   sampler+segnali plan-only; il bot vero aggiunge: esecuzione (se armato),
   `manage()` sulle posizioni aperte, reconcile collo store, alert (Telegram
   c'è già nel bot CFD).
5. **Ritiro del condor dai percorsi operativi**: `run_condor.py` deprecato
   (fatto, banner ⛔); alla riscrittura, `orchestrator.plan()` condor resta
   solo per i test dell'infrastruttura.

### Invarianti di sicurezza (NON negoziabili, in OGNI strato)

- Plan-only di DEFAULT; ordini solo con `--arm --i-understand-live-risk` + ok esplicito.
- Gamba COMPRATA sempre prima (mai short nudi) — è nell'executor, non toccarlo.
- Catena SOLO col metodo di [OPTION-CHAIN-IG.md](OPTION-CHAIN-IG.md) (checklist!).
- Guardia MODULA, mai blocca: si opera ogni mese.
- Nessuna strategia è "provata" senza pilot reale — il bot nasce con size pilot.
- Hold-to-expiry per tutto ciò che VENDE premio; gestione attiva solo dove
  validata (call, C8).

---

## 3. Ordine dei lavori (quando si parte, dopo il gate)

1. Pilot manuale (run_spread --arm) → valida fill/margini/mark → 2-4 settimane
2. `manage()` + check margine + allocazione conti (punti 1-3 sopra)
3. Scheduler unico con esecuzione (punto 4) → il bot opzioni è autonomo
4. Quando equity CFD ≥€2.5k: estendere `src/strategies/dip_buy.py` ai trigger
   ensemble (il codice dei segnali è già in `mean_reversion_us500.py`) → bot CFD
5. Refactor strato 3 (interfaccia comune) SOLO a quel punto (3 strategie vive)
