# EDGE #1 — Buy-the-Dip daily US500 (mean-reversion di breve)

Primo edge **validato** del progetto: sopravvive ai costi CFD, regge
out-of-sample, robusto ai parametri. Documentazione operativa per scalarlo.

Script: `scripts/mean_reversion_us500.py` · Dati: `data/research/us500_daily.csv`
(IG daily, 2008-2026). Costi modellati: spread 1pt round-trip + financing 5,5%/yr.

---

## 0. Riprendere da qui — comandi esatti

```bash
# ► LA VERSIONE BUONA (scale-in) — riproduce l'edge + tabella leva:
python scripts/mean_reversion_us500.py --entry-thr 10 --exit-ma 10 --scale-in 2 --add-thr 5

# validazione out-of-sample (2018-2026, mai visto in fase di scoperta):
python scripts/mean_reversion_us500.py --from 2018-01-01 --to 2026-07-11 --entry-thr 10 --exit-ma 10 --scale-in 2 --add-thr 5

# in-sample (2008-2017):
python scripts/mean_reversion_us500.py --to 2018-01-01 --entry-thr 10 --exit-ma 10 --scale-in 2 --add-thr 5

# prova che lo STOP peggiora (mean-reversion):
python scripts/mean_reversion_us500.py --from 2018-01-01 --to 2026-07-11 --entry-thr 10 --exit-ma 10 --stop-pct 5

# ► VERSIONE INTRADAY (flat overnight, da LEVERARE — stesso edge, no gap/fin):
python scripts/mean_reversion_us500.py --entry-thr 10 --exit-ma 10 --scale-in 2 --add-thr 5 --intraday

# ► ENSEMBLE C1 (validato 14 lug 2026, §5b): unione trigger t1-t5, ~20 trade/anno:
python scripts/mean_reversion_us500.py --trigger union --exit-ma 10 --scale-in 2 --add-thr 5
# satellite SHORT per i bear (t6):
python scripts/mean_reversion_us500.py --trigger t6 --exit-ma 5 --max-hold 7
# contributo marginale di un trigger (solo giorni non-t1) + test del nulla:
python scripts/mean_reversion_us500.py --trigger t3 --exclude-t1 --null 200 --exit-ma 10 --scale-in 2 --add-thr 5
```

**Stato:** edge validato + scale-in + **intraday confermato** (§5) + **ENSEMBLE
C1 validato** (§5b: 5 trigger → ~20 trade/anno, CAGR +8.8% a parità di maxDD, più
satellite short per i bear). **Prossimo passo** (§6):
sizing/combinazione edge → adapter IG + paper demo.
Se i dati US500 vanno estesi/rigenerati vedi `data/research/README.md`.

---

## 1. Le regole (meccaniche, nessun lookahead)

Segnale valutato sulla **barra daily chiusa**, esecuzione all'**apertura successiva**.

- **ENTRY (long)**: `close > SMA200` (compra i ribassi solo in uptrend)
  **AND** `RSI(2) < 10` (ipervenduto estremo di brevissimo).
- **EXIT**: `close > SMA(10)` **OR** `RSI(2) > 70` **OR** tenuto ≥ 10 giorni.
- Long-only, una posizione per volta, no piramidazione.

**Perché funziona:** due forze note negli indici azionari — il *drift* al rialzo
(premio al rischio) + la *mean-reversion di breve* (gli eccessi ribassisti
rientrano). Il filtro SMA200 evita di comprare i dip nei bear veri (dove
continuano a scendere). RSI(2) è il timing dell'eccesso.

---

## 2. Risultati (combo robusta: RSI2<10, exit MA10)

| Periodo | Trade | WR | gross/trade | **net/trade** | maxDD | CAGR (1x) |
|---|---|---|---|---|---|---|
| Full 2008-2026 | 144 (~8/yr) | **80%** | +0.59% | **+0.46%** | 14.2% | +3.8% |
| **OOS 2018-2026** (mai visto) | 72 | **79%** | +0.50% | **+0.38%** | 11.1% | +3.2% |
| IS 2008-2017 (exit MA5) | 73 | 75% | +0.51% | +0.38% | 12.2% | +3.2% |

- **Out-of-sample TIENE**: WR 79% (vs 80% full), net/trade ancora positivo. La
  magnitudine è decaduta ~40% dall'in-sample (mean-reversion parzialmente
  arbitraggiata) ma l'edge **resta**.
- **Esposizione ~13% dei giorni** (hold medio ~5,7 gg, ~8 trade/anno). Sta fuori
  mercato l'87% del tempo → maxDD basso, ma rendimento raw modesto.
- **Anno cattivo: 2018** (crollo Q4 con vol spike: compri il dip, continua a
  scendere). È il profilo di rischio della mean-reversion.

### Robustezza (sweep out-of-sample, tutte positive)
9 combo `entry_thr ∈ {5,10,15} × exit_ma ∈ {3,5,10}`: **tutte** net/trade
positive, WR 69-79%. È un **plateau**, non un parametro su misura. `exit_ma=10`
(tenere il rimbalzo un po' di più) è il migliore.

### ⭐ MIGLIORAMENTO: SCALE-IN (aggiungi sui dip più profondi)
Invece di uno stop (che PEGGIORA la mean-reversion, vedi §6), si **aggiunge**
una unità quando il dip si approfondisce (`RSI2 < 5` e prezzo sotto l'ultima
entrata). RSI più basso = segnale più forte = entrata migliore. Flag:
`--scale-in 2 --add-thr 5`.

| Versione | WR | net/trade | CAGR (1x) | maxDD |
|---|---|---|---|---|
| Baseline | 80% | +0.46% | +3.8% | 14.2% |
| **Scale-in 2** (full) | **86%** | **+0.73%** | **+6.2%** | **10.4%** |
| **Scale-in 2** (OOS 2018-26) | **83%** | **+0.68%** | **+5.9%** | **6.8%** |

Migliora rendimento **E** win rate **E** abbassa il drawdown, su full **e**
out-of-sample. È la versione raccomandata.

---

## 3. Perché sopravvive ai costi (dove le altre idee morivano)

Costo per trade ≈ **0,13%** (spread ~0,03% + financing ~0,09% su ~5,7 gg).
Gross +0,59% → net +0,46%. Il drag è piccolo perché:
- **poche operazioni** (~8/anno) → lo spread non si accumula;
- **hold corti** (giorni) → financing minimo.

Contrasto: il fade intraday aveva stop da 3,2pt → costo 0,62 R/trade → morte.
Qui gli hold sono più lunghi e i trade rari → i costi sono trascurabili.

---

## 4. LEVA — quanto si può scalare (la domanda chiave)

Simulazione: stessi trade, posizione = L × equity (`--` la tabella è in output).

**Full 2008-2026 (versione SCALE-IN, raccomandata):**
| Leva | CAGR | maxDD | peggior singolo trade |
|---|---|---|---|
| 1x | +6.2% | 10% | −10.0% |
| 2x | +12.5% | 21% | −20.0% |
| **3x** | **+18.9%** | **31%** | **−30.0%** |
| 5x | +31.4% | 51% | −50.0% |

**Out-of-sample 2018-2026:**
| Leva | CAGR | maxDD | peggior trade |
|---|---|---|---|
| 1x | +3.2% | 11% | −5.3% |
| 2x | +6.1% | 21% | −10.6% |
| 3x | +8.8% | 31% | −15.8% |
| 5x | +13.2% | 49% | −26.4% |

### Il financing NON è il problema (contro l'intuizione comune)
Il financing overnight è **~0,09%/trade** ed è **proporzionale al nozionale** →
**neutro rispetto alla leva** (scala insieme al rendimento del trade). È già
dentro i numeri "net". A 3x non ti mangia più di quanto ti mangia a 1x, in
proporzione. Quindi tenere overnight questo edge **non** è ammazzato dal
financing.

### Il vero limite della leva: DRAWDOWN e PEGGIOR TRADE (rischio gap)
- Il DD scala ~linearmente: a 3x sei a **~31-39% di maxDD**.
- Il **peggior singolo trade** scala con la leva: a 3x è **−16%/−31%** in UN
  trade (dip multi-day che continua a scendere + eventuale gap notturno). A 5x
  diventa insostenibile (−26%/−52%).
- Questo è il rischio reale di tenere leva overnight: non il financing, ma un
  **gap avverso** notturno amplificato dalla leva.

### Raccomandazione leva
- **2-3x** è la fascia ragionevole: CAGR ~6-11%/yr con maxDD ~21-39% —
  profilo rischio/rendimento simile o migliore del buy&hold (che ha ~56% di DD
  nel 2008), e **poco correlato** (in mercato solo il 13% del tempo).
- **Serve un catastrophe stop** per cappare il peggior trade prima di alzare la
  leva (vedi §6). Senza, a 3x un singolo 2018 fa male.

---

## 5. INTRADAY — TESTATO: l'edge SOPRAVVIVE (leva sicura) ✅

Domanda: si può tenere **flat overnight** (per leverare senza rischio gap)?
**Sì**, quasi senza perdita. Flag: `--intraday` (tiene open→close ogni giorno,
flat la notte, rientra ogni mattina).

| Versione | WR | gross/trade | net/trade | CAGR (1x) | maxDD |
|---|---|---|---|---|---|
| Multi-day (overnight) | 86% | +0.85% | +0.73% | +6.2% | 10.4% |
| **INTRADAY (flat overnight)** | 86% | **+0.85%** | **+0.69%** | +5.9% | 11.1% |

**Perché funziona:** il rimbalzo della mean-reversion avviene **dentro la seduta
(open→close)**, non overnight. Quindi l'edge lordo è **identico** (+0.85%); si
paga solo un po' di spread in più (rientro ogni mattina) → net +0.69% vs +0.73%.

**Implicazione leva (risolve il problema):** la versione intraday ha lo stesso
edge MA **niente rischio gap notturno** e **niente financing** → è quella da
**leverare**. Elimina la coda che rendeva rischiosa la leva overnight. Operativa:
ogni mattina, se il segnale daily (RSI2<10 in uptrend) è attivo, entra long
all'apertura; chiudi alla chiusura; flat la notte; esci quando scatta l'exit.

---

## 5b. ENSEMBLE C1 — più trigger della stessa famiglia + lato short ✅ (14 lug 2026)

Era il candidato **C1** della pipeline: la MR di breve è più larga del solo
RSI2<10 → più trigger standard di letteratura = più occorrenze = compounding,
stessa natura di rischio. **Validato con l'apparato completo** (nulla sui giorni
esclusivi, IS/OOS, plateau, stabilità). Flag: `--trigger t1..t6|union`,
`--exclude-t1` (contributo marginale), `--null N` (test del nulla).

**Contributo marginale dei trigger (SOLO giorni non coperti da t1, exit famiglia
MA10 + scale-in, netto costi, 2008-2026):**

| Trigger | Regola (soglie standard, non ottimizzate) | Trade nuovi | net/trade | vs nulla |
|---|---|---|---|---|
| t2 | 3+ chiusure consecutive giù, uptrend | 70 (~4/yr) | +0.52% | batte 100% ✅ |
| t3 | %b Bollinger(20,2) < 0.05, uptrend | 57 (~3/yr) | **+1.07%** | batte 100% ✅ |
| t4 | VIX > 1.05×MA10(VIX), uptrend | **278 (~16/yr)** | +0.48% | batte 100% ✅ |
| t5 | RSI2 cumulato 2gg < 35, uptrend | 57 (~3/yr) | +0.56% | batte 100% ✅ |

**UNIONE t1-t5 (il portafoglio, config raccomandata `--trigger union --exit-ma 10
--scale-in 2 --add-thr 5`):**

| Versione | Trade | WR | net/trade | CAGR 1x | CAGR 3x | maxDD 1x |
|---|---|---|---|---|---|---|
| t1 solo (baseline) | 144 (~8/yr) | 86% | +0.73% | +6.2% | +18.9% | 10.4% |
| **UNIONE t1-t5** | **342 (~20/yr)** | 79% | +0.43% | **+8.8%** | **+27.4%** | **10.0%** |

- **2.5× la frequenza, +42% di CAGR, STESSO drawdown.** L'esposizione sale a 25%
  dei giorni (da 13%) — più capitale al lavoro, stessa coda.
- **IS/OOS regge:** +0.54%/trade (2008-16) → +0.35% (2017-26), WR 76% — decadimento
  fisiologico della famiglia, edge presente.
- **Stabilità:** 16/18 anni positivi; negativi piccoli (2018 −5%, 2022 −4%).
- **Plateau (non picco):** t4 a soglia 1.10 → +0.63%/trade (regge, anzi meglio
  per-trade); t3 a %b<0.10 → +0.92% su 75 trade; exit MA5 resta positiva (MA10
  meglio). Soglie standard di letteratura, nessun tuning.

**t6 — satellite SHORT per i bear (`--trigger t6 --exit-ma 5 --max-hold 7`):**
`RSI2 > 95 AND close < SMA200` → short; exit RSI2<30 / close<SMA5 / 7gg.
27 trade (~2/yr), WR 78%, **+0.96%/trade netto**, batte il **100%** del nulla
(che sui giorni bear è ≈0: shortare a caso lì non paga — il timing sì). Paga
**esattamente dove serve: 2008 +3%, 2020 +10%, 2022 +9%** — il primo pezzo del
book che guadagna nei bear ripidi. Da usare come satellite piccolo, non come
motore (2 trade/anno).

⚠️ Nota onesta: i trigger si sovrappongono nel tempo (una posizione per volta,
il motore non piramida tra trigger) e t4 domina la frequenza — se il VIX regime
cambia, l'apporto di t4 va monitorato come per t1.

---

## 6. Rischi, limiti, prossimi passi

**Limiti onesti:**
- Rendimento **raw modesto** (~3-4%/yr a 1x); vive di leva e/o combinazione.
- Edge **in decadimento** (OOS ~60% dell'IS) — va monitorato, non è eterno.
- **Nessuno stop** attuale → coda di rischio (peggior trade −10%). Da aggiungere.
- **Un solo strumento/edge** → poca diversificazione; vero valore quando
  combinato con altri edge scorrelati.

**Lo stop di catastrofe PEGGIORA l'edge (testato — non usarlo):**
| OOS 2018-26 | net/trade | CAGR | maxDD |
|---|---|---|---|
| baseline (no stop) | +0.38% | +3.2% | 11% |
| stop −5% | +0.16% | +1.1% | **21%** ⬆️ |
| **scale-in** | **+0.68%** | **+5.9%** | **6.8%** ⬇️ |

Su una strategia di mean-reversion lo stop ti fa uscire sul minimo, proprio
prima del rimbalzo: **dimezza il rendimento e RADDOPPIA il drawdown**. I gap
notturni catastrofici sull'S&P sono rarissimi; e quando il dip si approfondisce
la MR è più forte → la risposta giusta è **aggiungere** (scale-in), non stoppare.

**Prossimi passi per renderlo tradeable con leva:**
1. ✅ **Scale-in** (fatto): la risposta ai dip profondi, migliora tutto.
2. ✅ **Intraday** (fatto, §5): l'edge sopravvive flat overnight → **è la
   versione da leverare** (no gap-risk, no financing).
3. **Sizing basato sul rischio** + leva moderata (2-3x) sulla versione intraday.
4. **Combinare** con altri edge scorrelati per aumentare l'esposizione utile
   (~13% dei giorni lascia spazio) — su US500 i complementi sono limitati
   (long-bias): vera diversificazione = multi-mercato (FX/commodity/bond).
5. Se regge → **adapter IG di esecuzione** + paper trading su demo.

**Criterio:** si va live con scale-in + leva moderata (2-3x) + paper trading
positivo. Niente stop stretti (uccidono la MR); il controllo del rischio è la
leva moderata e la bassa esposizione, non uno stop.

---

## 7. PIANO A (DECISO) — dal backtest al bot live sul demo IG

**Decisione presa:** costruiamo il bot attorno a QUESTO edge (buy-the-dip
intraday + scale-in), lo portiamo su IG in esecuzione reale e paper trading sul
demo. Versione da usare: **intraday** (flat overnight, leverabile).

**Passi concreti (nell'ordine):**

1. **Esecuzione IG** — estendere `src/core/ig_client.py` (ora solo lettura):
   - `open_position(epic, direction, size, stop=None, limit=None)` → `POST /positions/otc`
     (orderType MARKET, currencyCode EUR); niente stop stretto (vedi §6).
   - `get_positions()`, `close_position(dealId, size)`, `confirm(dealRef)` → `GET /confirms/{ref}`.
   - (Live intraday) streaming prezzi via Lightstreamer per timing open/close.

2. **Sizing CFD con leva** — `size_lotti = (equity × L) / prezzo` oppure per-rischio;
   L target **2-3x** (§4). Min size 1.0, valore punto €1 (vedi ig-demo-us500-params).

3. **Runtime della strategia** (nuovo, es. `src/strategies/dip_buy.py` + loop):
   - ogni mattina calcola il segnale daily da IG `/prices` (close>SMA200 AND RSI2<10);
   - se attivo → entra long all'**apertura RTH**; **scale-in** su dip più profondi
     (RSI2<5, prezzo più basso); esci alla **chiusura** ogni giorno (flat overnight);
     ri-entra il mattino finché il segnale d'uscita (close>SMA10 / RSI2>70) non scatta.
   - guardrail: max perdita giornaliera, max size, kill switch.

4. **Paper trading sul demo IG** — girarlo dal vivo, loggare i trade, **confrontare
   col backtest** (fill, spread reale IG, timing). Solo se combacia → considerare live.

**Nota diversificazione (dopo):** su US500 i complementi sono scarsi (long-bias);
per il bot multi-strategia pieno servirà il multi-mercato (FX/commodity/bond,
Strada B in DIARIO-CONVERSIONE-IG.md §5). Ma prima portiamo QUESTO edge al vivo.

**Riferimenti:** parametri strumento in memoria `ig-demo-us500-params`; connessione
IG già verificata (`scripts/test_ig_connection.py`); dati in `data/research/`.
