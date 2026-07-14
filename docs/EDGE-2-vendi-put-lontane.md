# EDGE #2 (rivisto) — Put-spread far-OTM su US500 (premio dello skew)

L'unico edge su opzioni IG che **sopravvive al pricing reale**. Vende il premio
ricco delle **put OTM** (skew azionario, strutturale e persistente) con una
struttura a **rischio definito**, tenuta **a scadenza**. Sostituisce l'iron condor
(❌ falsificato — vedi [STORIA-iron-condor.md](STORIA-iron-condor.md): il lato call, a sconto
su IG, faceva perdere l'intera struttura).

> **Documento vivo.** Stato in cima, dettagli sotto.

**STATO (14 lug 2026): edge REALE ma MODESTO, validato col pricing reale.** Non è
un motore di compounding aggressivo: è **reddito sicuro** (+1.5% CAGR a size
prudente, scalabile a ~6% a size moderata; WR 92-100%, maxDD 1-4%, coda cappata).
⚠️ **Prima del live serve un passo di validazione:** i rapporti dello smile sono
calibrati su UNA istantanea (oggi) — vanno **confermati campionando lo skew IG su
più giorni** (§7). L'infrastruttura d'esecuzione è già pronta (§6).

---

## 0. Comandi per riprendere

```bash
# config raccomandata (short −7%≈1.5σ, ala 3σ), pricing reale dello skew, banda VIX
python scripts/short_vol_us500.py --strat putspread --a 1.5 --b 3.0 \
       --spread-leg 1.0 --vix-min 14 --vix-max 30 --real-smile

# più sicuro (ala più lontana, meno rendimento):  --a 1.5 --b 4.0
# più aggressivo (short più vicino):               --a 1.0 --b 3.0
# far-OTM stile "-10%" (2σ): WR ~100% ma rende poco: --a 2.0 --b 3.0

# ► CAPITALE PICCOLO + TIMING POST-PANICO (config OPERATIVA raccomandata, §4b/§4c):
python scripts/short_vol_us500.py --strat putspread --a 1.5 --b 2.5 \
       --spread-leg 1.0 --real-smile --risk-frac 0.35 \
       --entry-mode postspike --spike-min 20 --cool 0.90 --ts-max 1.0
```

Script: `scripts/short_vol_us500.py` (`--strat putspread --real-smile`).
Dati: `data/research/vix_daily.csv` (CBOE) + `us500_daily.csv`.

---

## 1. La tesi e le regole

**Tesi (skew premium):** sugli indici azionari le **put OTM** prezzano una IV molto
più alta dell'ATM (put skew — documentato da decenni, strutturale). Chi **vende**
put OTM incassa questo premio. È la parte dello short-vol che **regge su IG**,
perché lì le put sono care (a differenza delle call, a sconto → il condor moriva
sul lato call).

**Struttura: bull put spread mensile a rischio definito.**
- Ogni ~mese, con sottostante `S` e implied vol `iv` (dal VIX):
  - **vendi** put a `Kp1 = S·(1 − a·iv·√T)` (short, es. a=1.5 ≈ −7%);
  - **compra** put a `Kp2 = S·(1 − b·iv·√T)` (ala di protezione, es. b=3).
- **Incassi** il credito netto; **max perdita** = ampiezza − credito (definita).
- **Exit: a SCADENZA** (cash-settled a intrinseco, europea → niente assegnazione).
- Solo lato put (niente call: su IG rendono meno dello spread).

**Perché non l'iron condor:** il lato call di IG è a sconto (IV ~0.6×VIX) → venderlo
perde dopo lo spread. Togliendolo, resta il lato put (positivo). Vedi §2.

---

## 2. Perché questo regge e il condor no (la lezione)

Il **primo backtest del condor** prezzava tutte le gambe a un **VIX piatto** →
sovrastimava il credito **~2.3×** → falso +6.3% CAGR. Rifatto col **pricing reale**:
- **call OTM** su IG: IV ~0.6×VIX (a sconto) → venderle **perde**;
- **put OTM** su IG: IV ~1.1-1.4×VIX (care, skew) → venderle **rende**.
Quindi il condor (che vende entrambe) va negativo; il **solo put-spread** resta
positivo. Confermato da **misura diretta** dei prezzi reali IG, non solo dal modello.

**Regola d'oro di validazione (nuova):** un backtest di opzioni si fa SOLO con lo
**smile reale** del broker + gli **spread reali per gamba**; mai con un VIX piatto.

---

## 3. Il pricing reale IG (smile) — come è modellato

Misurato sui prezzi reali IG (14 lug 2026, VIX 17.78, scad. 21-ago, forward 7541):

| Strike | Distanza | IV reale | IV/VIX |
|---|---|---|---|
| 2σ put | −11% | 24.4% | 1.37 |
| 1σ put | −6% | 19.2% | 1.08 |
| ATM | 0% | 13.7% | 0.77 |
| 1σ call | +6% | 10.9% | 0.61 |

Modello a **pendenza** (`--real-smile`, calibrato su questi punti):
`IV_put(nσ) = VIX·(0.77 + 0.30·n)`, `IV_call(nσ) = VIX·(0.77 − 0.16·n)`.
Spread bid/ask reali: ~1.5pt near-money, ~0.5-1.0pt far-OTM. Settlement cash a
intrinseco (hold-to-expiry sicuro).

⚠️ Questi rapporti vengono da UNA istantanea. Lo **shape** (put care/call scont.) è
strutturale; i **livelli esatti** (specie l'ATM 0.77) variano → §7.

---

## 4. Risultati (pricing reale, netto spread, banda VIX, 2007-2026)

Put-spread, mosse reali dell'S&P a scadenza, ~8 trade/anno:

| Config (short/ala) | ≈ short | WR | ret/trade | t | CAGR@10% | maxDD | peggior trade |
|---|---|---|---|---|---|---|---|
| **1.5σ / 3σ** ⭐ | −7% | 97% | +1.8% | +9.1 | **+1.5%** | 2% | −23% |
| **1.5σ / 2.5σ** ⭐ CAPITALE PICCOLO | −7% | 97% | +2.0% | +6.6 | +1.7% | 4% | −36% |
| 1.5σ / 4σ | −7% | 97% | +1.4% | +11.7 | +1.2% | 1% | −14% |
| 1.5σ / 2σ | −7% | 97% | +1.5% | +2.5 | +1.2% | 7% | −74% |
| 1.0σ / 3σ | −5% | 92% | +2.0% | +3.9 | +1.7% | 4% | −42% |
| 2.0σ / 3σ | −11% | 100% | +1.1% | +30 | +0.9% | 0% | (mai) |

- **Edge reale e stabile:** WR 92-100%, positivo quasi ogni anno; perdite cappate
  e concentrate nei crash (2010, 2018, 2025).
- **Modesto** al sizing prudente (~+1.5% CAGR): l'ala cara spreme il premio ricco.
- Il **tail-hedge esplicito NON aiuta** (costa premio; l'ala È già la copertura).

### ⭐ Config CAPITALE PICCOLO (€1.000-3.000) — short 1.5σ / ala 2.5σ (14 lug 2026)
Con capitale piccolo la max-loss ASSOLUTA del contratto decide il sizing, non la
frazione di rischio: **ala più vicina (2.5σ) = width ~1σ ≈ $330-400 di max loss
per contratto** (vs ~$550-600 dell'ala 3σ). Backtest (pricing reale): WR 97%,
**+2.0%/trade del capitale a rischio**, t=+6.6, peggior trade −36% del rischio.
Al sizing FORZATO di 1 contratto:
- **€1.000** (rischio ~35%/trade): **CAGR +5.9%/yr ≈ €60/anno, maxDD 13%**,
  peggior trade −€120 (−12% del conto), cigno nero cappato a ~−€340.
- **€2.000** (~18%): CAGR +3.0%, maxDD 6% — oppure 2 contratti = profilo €1000 ×2.
- Comando: `--strat putspread --a 1.5 --b 2.5 --spread-leg 1.0 --vix-min 14
  --vix-max 30 --real-smile --risk-frac 0.35`
- Il compounding scatta **a gradini**: +1 contratto ogni ~€1.000 di equity.
- Ali ancora più strette (2σ) NON conviene: t crolla a 2.5, peggior trade −74%.

### Compounding / sizing
È così sicuro (maxDD 2% a 10%) che **scala col sizing**: a size moderata
(perdita-singola-trade tollerabile) → **~+6% CAGR, maxDD ~9-13%**, coda cappata.
⚠️ Il limite è il **cigno nero** (oltre l'ala = perdita piena su quel trade):
NON sovra-dimensionare. La frequenza settimanale NON aiuta (lo spread mangia il
premio minuscolo delle weekly).

### ⭐ 4c. TIMING D'INGRESSO — vendere SOLO post-panico (C5+C2, 14 lug 2026)

**Scoperta di onestà sul calendario:** il backtest calendario è **fragile alla
fase** (spostando la data di partenza, la griglia dei 21 giorni cambia e il
trade killer di feb 2020 entra o esce: worst da −36% a **−100%**, maxDD@35% da
13% a 35%). Il tail vero del programma calendario INCLUDE il −100% del rischio:
un crash che parte dalla calma non è filtrabile da nessun segnale d'ingresso.

**La soluzione (testata, finestra 2009-2026 a parità di condizioni):** entrare
SOLO dopo il panico, quando il premio è ricco e la tempesta sta passando:
`VIX ≥ 20` **E** `VIX < 0.90 × max(VIX 10gg)` (spike in raffreddamento, C5)
**E** `VIX/VIX3M ≤ 1.0` (term structure rientrata, C2). Scansione giornaliera.

| Modalità (2009-2026, 1.5σ/2.5σ, rischio 35%) | Trade/anno | ret/trade | t | peggior | maxDD | CAGR |
|---|---|---|---|---|---|---|
| Calendario VIX[14,30] | ~9 | +1.4% | 1.9 | **−100%** | 35% | +3.8% |
| Calendario + TS≤1 (C2 da solo) | ~8 | +1.4% | 1.7 | −100% | 35% | +3.4% |
| Postspike (C5 da solo) | ~4 | +2.3% | 6.4 | −21% | 7% | +3.3% |
| **Postspike + TS (C5+C2)** ⭐ | ~4 | **+2.7%** | **+31.6** | **−1%** | **0%** | +3.4% |

- **C2 da solo NON salva il calendario** (feb 2020 era in contango: entrata di
  calma → nessun filtro d'ingresso la evita). Bocciato come filtro standalone.
- **C5+C2 = quasi mai una perdita in 17 anni** (59 trade, 1 perdita da −1%):
  eviti per costruzione le entrate di calma pre-crash, e il TS blocca le entrate
  premature durante la tempesta (senza TS il 2020 costa −21%).
- **⚠️ Caveat onesti:** (1) **2008 non coperto dal TS** (VIX3M parte set-2009):
  il postspike DA SOLO nel 2008 prende **−79%** (secondo tonfo di novembre); il
  TS in backwardation persistente l'avrebbe *probabilmente* bloccato, ma non è
  verificabile → **il tail resta possibile: dimensiona come se il −100% potesse
  accadere**. (2) Sensibilità al parametro `cool`: 0.95 perfetto / 0.90 buono /
  0.85 degrada — non è un plateau pulito, si usa lo 0.90 pre-registrato senza
  tuning. (3) ~4 trade/anno: meno ricorrente del calendario.
- Comando: `--entry-mode postspike --spike-min 20 --cool 0.90 --ts-max 1.0`
  (VIX3M: `data/research/vix3m_daily.csv`, scaricato dal CBOE).

**Su €1.000 REALI (contratti interi, 1 per €1.000 di equity — sim nel report
grafico):** post-panico finale **€1.329** (+€329 in 16,6 anni ≈ **~€20/anno**),
mai un mese sotto −2%; calendario €1.402 ma col mese in cui perde l'INTERO
rischio (feb 2020 — e lì per fortuna il rischio era piccolo, VIX basso).
Il rendimento a rischio-fisso 35% (+3.4%/anno) NON si raggiunge coi contratti
interi perché il rischio reale mediano/contratto è ~€200, non €350.
**Raccomandato: C5+C2 come modalità d'ingresso del pilot.**
**→ Report grafico completo (14 figure, esempi, capitali reali):
[report/report-edges.html](report/report-edges.html)**

---

## 5. Rischi e limiti onesti

- **Rendimento modesto** (+1.5% prudente / ~6% moderato). Non è un compounder
  aggressivo — su IG il premio (dopo protezione) è sottile.
- **Cigno nero:** un crash oltre l'ala (>3σ in un mese) = perdita piena su quel
  trade. Cappata dal rischio definito, ma pesante se sovra-dimensionato.
- **Direzionale-rialzista** (short put): correla col dip-buy nei crash (entrambi
  soffrono). Non è vera diversificazione dal dip-buy.
- **Smile calibrato su 1 istantanea** (§7): lo shape è strutturale, i livelli no.
- **Modello ≠ realtà** finché non c'è paper trading (§7).

---

## 6. Infrastruttura d'esecuzione — GIÀ PRONTA (riusata dal condor)

Tutto costruito e collaudato in dry-run (`src/options/`): il put-spread è **2 gambe**
delle 4 del condor → l'esecutore va bene così com'è (apre longs-first: prima l'ala
comprata, poi la short → mai short nudo). Componenti:
- **Sessione persistente** (`session.py`): login una volta, token riusati → niente
  lockout `invalid-client-security-token`.
- **Executor sicuro** (`executor.py`): apertura con ritento + hold, mai gamba parziale.
- **Catena a costruzione diretta** (`chain_resolver.py`): epic dagli strike
  (`OP.D.<code>.<strike>P.IP`), niente search (che tronca).
- **Scadenze REGOLARI** (3° venerdì): `monitor.upcoming_standard_expiries` +
  `_discover_code` — mai le fine-mese (EMO).
- **Throttle** (anti rate-limit), **store** (SQLite), **monitor** (P&L/DTE/reconcile),
  **orchestrator** (`run_condor.py`, plan-only di default).
- Conto reale opzioni: `TVYYM` (`.env` `IG_LIVE_*`). Vedi STORIA-iron-condor.md §6/§9.

Adattamento minimo: una variante orchestratore che apre **solo il put-spread**
(2 gambe) invece del condor.

---

## 7. Next steps (in ordine)

1. **⭐ Confermare lo skew nel tempo (gate di validazione) — SAMPLER ATTIVO
   (14 lug 2026).** Script: `python scripts/sample_skew_us500.py --live`
   (1×/giorno, read-only, ~14 chiamate throttlate) → appende a
   `data/research/skew_samples.csv`; `--report` = riepilogo vs modello. Servono
   **~10-20 campioni** su diversi livelli di VIX. **Primo campione (14 lug,
   VIX 16.8):** atm_ratio **0.80** (modello 0.77), put_slope **0.301** (modello
   0.30 — esatto, e LINEARE fino a 3σ: ratio 1.22@1.5σ, 1.73@3σ → anche
   l'estrapolazione far-OTM regge), call_slope 0.07 (devia, ma al put-spread non
   serve). **Se l'ATM medio va verso 0.9, l'edge si assottiglia** → rifare i
   conti coi rapporti medi veri. NON andare live prima di questo gate.
2. ✅ **Adapter put-spread FATTO (14 lug 2026):** `scripts/run_spread.py --strat
   putspread --live` (plan-only di default; `--arm --i-understand-live-risk` per
   aprire). Modulo `src/options/spread_orchestrator.py`: 2 gambe (ala comprata
   PRIMA, poi la short → mai nudi), segnale post-panico+TS calcolato in
   automatico (VIX/VIX3M dal CBOE, max 10gg), sizing 1 contratto/€1000, store
   con colonna `strategy`. Verificato plan-only sul reale (salta correttamente
   con VIX 16.4 < 20).
3. **Gate di rischio + sizing:** size moderata (perdita-singola-trade tollerabile,
   NON aggressiva); banda VIX[14,30]; max 1 posizione/scadenza.
4. **Paper/pilot sul reale** (piccolo): loggare fill/spread/settlement veri vs
   modello. Solo se combacia → size normale.
5. **Poi (fase 2 del progetto):** cercare i "grandi numeri" altrove (multi-mercato,
   prezzo) — su IG le opzioni danno reddito sicuro ma modesto, non compounding
   aggressivo. Il put-spread resta come **componente di reddito** in un book
   diversificato (con dip-buy).

**Criterio di promozione:** skew confermato nel tempo (1) + paper trading coerente
(4). Niente live prima di questi due.

---

## 8. File e dati

| Cosa | File |
|---|---|
| Backtest put-spread (pricing reale) | `scripts/short_vol_us500.py --strat putspread --real-smile` |
| Infrastruttura live | `src/options/` (session, executor, chain_resolver, store, monitor, orchestrator, throttle) |
| CLI operativa (plan-only) | `scripts/run_condor.py` (da adattare al put-spread) |
| Condor falsificato (storia + lezione) | `docs/STORIA-iron-condor.md` |
| Dati | `data/research/vix_daily.csv`, `us500_daily.csv` |
