# Registro degli EDGE — US500 / IG

Stato di tutte le idee testate e da testare. Ogni edge nuovo passa lo **stesso
apparato**: test del nulla (se applicabile) + **netto costi** + out-of-sample +
robustezza parametri. Dati: `data/research/` (vedi il suo README).

---

## ✅ VALIDATI (tradeable)

### EDGE #1 — Buy-the-Dip intraday + scale-in
Mean-reversion di breve. Doc completa: **[EDGE_BUYTHEDIP.md](EDGE_BUYTHEDIP.md)**.
- Regole: long se `close>SMA200 AND RSI(2)<10`; scale-in su dip più profondi;
  exit su `close>SMA10 / RSI2>70 / 10gg`; **intraday** (flat overnight).
- Numeri (2008-2026): WR **86%**, net **+0.73%/trade**, CAGR +6.2%@1x /
  +18.9%@3x, maxDD ~10%. Regge OOS (WR 79%) e robusto (9/9 combo).
- Costi OK (pochi trade + hold corti). Intraday = stesso edge, leverabile.
- Script: `scripts/mean_reversion_us500.py` (`--scale-in 2 --add-thr 5 --intraday`).
- ⚠️ NIENTE stop stretto (peggiora la MR — testato: −5% dimezza rendimento,
  raddoppia DD). Controllo rischio = leva moderata + bassa esposizione.

---

## ❌ FALSIFICATI (non ritestare senza un angolo NUOVO)

| Idea | Script | Verdetto |
|---|---|---|
| **Macro Core** (trend core daily) | `backtest_macro_core_us500.py` | Perde vs buy&hold anche gross (+201% vs +437%); financing su hold lunghi lo affonda. Archetipo sbagliato per indice azionario. |
| **Fade sessioni** (killzone H/L) | `session_research_us500.py --mode reversal` | Batte solo 6-7% dei livelli casuali (test del nulla): no struttura. Netto costi negativo OGNI anno (stop 3.2pt → costo 0.62R). |
| **Continuation sessioni** | `session_research_us500.py --mode continuation` | Rara (93% degli sweep rientra) e negativa (E[R] −0.08). |
| **Opening Range Breakout** | `opening_breakout_us500.py` | Coin flip (E[R] gross ≈ 0), non batte un'ora morta. Netto negativo. |
| **Overnight drift** | `overnight_drift_us500.py` | Reale lordo (+6.9%/yr) ma financing + spread giornaliero lo uccidono (−3.7%/yr netto). Peggio del buy&hold. |
| **Trend Breakdown** | `backtest_trend_breakdown_us500.py` | Netto ~piatto (+0.7%). Long marginale (PF 1.17), short nessun edge (shortare indice long-biased non paga). |

**Lezione trasversale:** su CFD IG US500 i costi uccidono tutto ciò che ha stop
stretti (spread) o hold lunghi (financing). Sopravvive solo: pochi trade + hold
corti (dip-buy) o intraday (flat overnight).

---

## 🔍 DA INDAGARE (nuovi edge, in ordine di promessa)

### 1. Trend-following multi-mercato (la vera diversificazione)
Paniere di mercati IG (FX, materie prime, bond, altri indici) con momentum
time-series (3-12 mesi), long/short, vol-target. NON long-biased come gli indici
→ **scorrelato dal dip-buy** = il complemento che serve al bot. Edge retail più
robusto (managed futures). **Serve scaricare più epic IG.** Priorità alta.

### 2. Complemento short/difensivo per il dip-buy
Il dip-buy soffre nei bear ripidi (2018, 2022). Cercare qualcosa che guadagni o
protegga lì: filtro di regime che riduce size in bear confermato, o un edge su
volatilità (long vol nei crash). Aumenta l'esposizione utile oltre il 13%.

### 3. Varianti mean-reversion (stessa famiglia, dati già pronti)
- Altri indici IG (Nasdaq/US100, DAX, FTSE) — la MR di breve è cross-market:
  testare RSI2<10 su altri epic → **diversificazione a basso costo**, stesso codice.
- Filtri aggiuntivi (VIX/vol regime: la MR rende di più in alta vol).
- Uscite alternative (target su banda, non solo RSI/MA).

### 4. Stagionalità / effetti calendario sugli indici
Turn-of-month, day-of-week, pre-festivi: effetti documentati, pochi trade →
costi ok su CFD. Facili da testare coi dati daily.

### 5. Mean-reversion intraday pura (sub-giornaliera)
Con la cache 1m (`us500_1m.pkl`): oversold intraday → rientro entro poche ore.
Da capire se esiste un edge intraday veloce (finora l'MR era multi-day).

**Come testare un nuovo edge:** riusa l'apparato — backtest codice reale + netto
costi + split in/out-of-sample + sweep parametri + (se sui livelli) test del nulla.
Promosso solo se batte il nulla E resta positivo netto costi E stabile ogni anno.



# nuove idee edges

# Strategie Intraday S&P 500 — Proposte da Backtestare

Tutte le proposte sono progettate intorno ai **vincoli IG CFD** che hai già identificato:
- ❌ Stop stretti → lo spread ti mangia
- ❌ Hold lunghi → il financing ti mangia
- ✅ Pochi trade + hold corti / flat overnight

> [!IMPORTANT]
> Ogni strategia va passata dal tuo apparato: backtest netto costi + split IS/OOS + sweep parametri + test del nulla (dove applicabile). Promuovi solo se batte il nulla, resta positiva netta, e stabile anno per anno.

---

## 🏆 TIER 1 — Alta probabilità di edge (struttura documentata in letteratura)

### Strategia A: Late-Day Drift (Power Hour Mean Reversion + Momentum)

**Razionale:** L'ultima ora di trading (15:00–16:00 ET, cioè 21:00–22:00 CET) è dominata da flussi istituzionali (MOC orders, rebalancing fondi). Ci sono due effetti documentati:
1. **Drift rialzista verso la chiusura** — effetto robusto su S&P 500, specialmente in giornate negative (reversion)
2. **Accelerazione della direzione dominante** — in giornate fortemente direzionali, l'ultima ora amplifica

**Regole proposte (versione mean-reversion):**
```
SETUP:
- Ore 20:00 CET (1h prima della chiusura US)
- Il mercato è in calo dalla open: close_corrente < open_giornata
- Filtro trend: close > SMA(200) daily (stesso del tuo dip-buy)

ENTRY:
- Long a mercato alle 20:00 CET
- Variante aggressiva: long se rendimento intraday < -0.5%

EXIT:
- Chiudi alla chiusura della sessione US (22:00 CET) → flat overnight
- Oppure: trailing stop ultimo 30 minuti (solo se ampio, tipo 0.3%)

SIZING:
- Fisso, niente scale-in (hold troppo corto)
```

**Perché potrebbe funzionare per te:**
- Hold di 1-2 ore → costi minimi (no financing, spread pagato 1 volta)
- Flat overnight → nessun gap risk
- Non richiede stop stretto (exit a tempo)
- Complementare al dip-buy (questo è giornaliero, il dip-buy aspetta RSI2<10)
- Dati 1m già disponibili nella tua cache `us500_1m.pkl`

**Test del nulla:** confronta con entry random nella stessa finestra oraria. Se l'entry "giornata in calo" non batte entry casuali, non c'è edge.

---

### Strategia B: Intraday Oversold Bounce (MR sub-giornaliera)

**Razionale:** Estensione naturale del tuo Edge #1. Invece di aspettare RSI(2) daily < 10 (raro), cerca oversold su timeframe inferiori (15m/30m) per trade intraday. La mean-reversion è più forte sugli indici liquidi perché i market maker riportano il prezzo verso il fair value.

**Regole proposte:**
```
SETUP:
- Timeframe: 15 minuti
- RSI(2) su 15m < 5 (oversold estremo su TF veloce)
- Filtro: close > VWAP del giorno (non comprare in trend ribassista puro)
- Filtro macro: close daily > SMA(50) o SMA(200)

ENTRY:
- Long al close della candela 15m che genera il segnale

EXIT (in ordine di priorità):
1. Close > VWAP + 0.1% → target raggiunto
2. RSI(2) 15m > 70 → momentum esaurito
3. Fine sessione US → flat overnight (exit forzata)
4. Max hold: 3 ore → exit a tempo

NO STOP LOSS stretto (stessa lezione del dip-buy).
Controllo rischio = leva moderata.
```

**Perché potrebbe funzionare per te:**
- Stessa famiglia del tuo edge validato (MR), stessa logica, TF diverso
- Molto più frequente di RSI2 daily < 10 → più trade, più diversificazione temporale
- Hold di minuti/ore → costi trascurabili
- Usa i dati 1m che hai già
- Cross-validabile: se RSI2<10 daily funziona, RSI2<5 su 15m *dovrebbe* avere lo stesso bias

**Rischio:** il rumore su TF bassi può diluire l'edge. Lo spread IG pesa di più su target piccoli. Testa il P&L netto spread con attenzione.

---

### Strategia C: VWAP Mean Reversion

**Razionale:** Il VWAP (Volume-Weighted Average Price) è il livello di "fair value" intraday per eccellenza. Le deviazioni significative dal VWAP tendono a rientrare, specialmente su strumenti liquidi come S&P 500. Usato attivamente da desk istituzionali.

**Regole proposte:**
```
SETUP:
- Calcola VWAP rolling dalla open della sessione US
- Calcola deviazione standard delle distanze dal VWAP

ENTRY (long):
- Prezzo < VWAP - 1.5σ (deviazione significativa sotto il fair value)
- Filtro: almeno 1h dall'apertura (il VWAP si stabilizza)
- Filtro trend: SMA(200) daily rialzista

ENTRY (short) — opzionale, solo se i dati lo supportano:
- Prezzo > VWAP + 2σ (soglia più alta per short su indice long-biased)

EXIT:
- Ritorno al VWAP (target naturale)
- Max hold: fine sessione US
- Stop: VWAP - 2.5σ (ampio, solo protezione catastrofe)
```

**Perché potrebbe funzionare per te:**
- Il VWAP ha un'ancora economica reale (prezzo medio ponderato per volume)
- Complementare al dip-buy: questo cattura micro-dislocazioni intraday
- Hold corto (tipicamente 30min-2h per il rientro al VWAP)
- Facilmente testabile con i dati 1m

**Nota:** servono dati di volume. Se IG non fornisce volume tick affidabile, puoi usare un proxy (tick count o volume da un'altra fonte come Yahoo Finance per SPY).

---

## 🥈 TIER 2 — Edge plausibile (richiede più validazione)

### Strategia D: First-Hour Momentum Filter (NON è un ORB!)

**Razionale:** Hai falsificato l'Opening Range Breakout classico (coin flip). Ma c'è un edge diverso: usare la **direzione** della prima ora come **filtro**, non come segnale di breakout. La letteratura accademica (Gao, Han, Li, Zhou 2018) documenta che la prima mezzora ha potere predittivo sul resto della giornata, specialmente in regime di alta volatilità.

**La differenza col tuo ORB falsificato:** non entri al breakout del range. Usi la prima ora solo per decidere la direzione, poi entri su un pullback nel resto della giornata.

**Regole proposte:**
```
SETUP:
- Alle 16:30 CET (1h dopo open US), classifica la giornata:
  - "Bullish first hour" se rendimento prima ora > +0.15%
  - "Bearish first hour" se rendimento prima ora < -0.15%
  - "Neutro" altrimenti → no trade

ENTRY (solo long, indice long-biased):
- Se "Bullish first hour": attendi un pullback del 50% del range della prima ora,
  poi long
- Se "Bearish first hour": NO TRADE (non shortare indice, lezione già appresa)

EXIT:
- Target: high della prima ora
- Max hold: fine sessione US
- Stop: low della prima ora (stop strutturale, non stretto)

FILTRO REGIME:
- ATR(14) daily > mediana storica → trade solo in volatilità sopra media
  (la prima ora è più predittiva in alta vol)
```

**Perché è diverso dal tuo ORB falsificato:**
- Non è un breakout meccanico → è un filtro direzionale + entry su pullback
- Ha un filtro di regime (volatilità) che il tuo test non aveva
- Solo long → allineato col bias dell'indice
- Stop strutturale (non stretto), coerente con la tua lezione

---

### Strategia E: Effetti Calendario Intraday (già nella tua lista)

**Razionale:** Effetti ben documentati accademicamente su S&P 500:
- **Turn-of-Month (ToM):** ultimi 2 giorni del mese + primi 3 del mese successivo concentrano ~80% dei rendimenti mensili (Ariel 1987, Lakonishok & Smidt 1988). Effetto persistente da decenni.
- **Pre-festivi:** il giorno prima di festività USA (Thanksgiving, Independence Day, ecc.) ha rendimento medio significativamente positivo.
- **Lunedì negativo / Venerdì positivo:** effetto day-of-week, più debole ma testabile.

**Regole proposte (ToM):**
```
SETUP:
- Identifica i giorni ToM: ultimi 2 trading days del mese + primi 3 del mese

ENTRY:
- Long all'apertura della sessione US nei giorni ToM
- Filtro opzionale: close > SMA(200)

EXIT:
- Chiusura della sessione US dello stesso giorno (intraday puro)
- Oppure: hold fino alla fine della finestra ToM (5 giorni), ma attenzione
  al financing se hold multi-day

SIZING:
- Pieno nei giorni ToM
- Flat (o ridotto) nei giorni non-ToM
```

**Perché potrebbe funzionare per te:**
- Pochissimi trade (5 giorni/mese) → costi ok
- Edge documentato da 40+ anni, ancora presente
- Intraday = no financing
- Semplicissimo da implementare e testare
- **Complementare al dip-buy:** il ToM non dipende da RSI → cattura giorni diversi

**Test del nulla:** confronta il rendimento medio dei 5 giorni ToM vs 5 giorni random del mese. Ripeti 10.000 volte.

---

### Strategia F: Cross-Market Leading Signal (Bond/VIX → SPX)

**Razionale:** I Treasury (US T-Note) e il VIX spesso *anticipano* i movimenti dell'S&P 500 di minuti/ore. Se i bond salgono (risk-off diminuisce) mentre l'S&P è ancora in calo, è un segnale di mean-reversion imminente.

**Regole proposte:**
```
SETUP:
- Monitor correlazione rolling 30m tra US T-Note (o US 10Y future) e US500
- Calcola z-score della divergenza

ENTRY (long):
- US T-Note in rialzo (rendimento 1h > +0.05%) 
  AND US500 in calo (rendimento 1h < -0.1%)
  AND z-score divergenza > 1.5
- → Long US500 (aspettandosi convergenza)

EXIT:
- Convergenza raggiunta (divergenza torna sotto 0.5σ)
- Max hold: 4 ore o fine sessione
- Stop: divergenza si allarga oltre 2.5σ (genuino risk-off)
```

**Perché potrebbe funzionare per te:**
- Edge strutturale (relazione economica bond/equity)
- Intraday → no financing
- Stop ampio (basato sulla divergenza, non in punti)
- Scorrelato dal dip-buy e dal ToM

**Complessità:** richiede dati intraday di un secondo strumento IG (T-Note o VIX). Verifica disponibilità nei tuoi epic IG.

---

## 🥉 TIER 3 — Idee speculative (testa solo se i Tier 1-2 sono esauriti)

### Strategia G: Volatility Squeeze Intraday
- Bollinger Bands (20,2) su 15m si comprimono (bandwidth < percentile 10 degli ultimi 50 periodi)
- Entry: alla prima candela che chiude fuori dalle bande
- Direction: solo long se sopra VWAP
- Exit: 2x l'ampiezza delle bande prima dello squeeze, o fine sessione
- **Rischio:** simile all'ORB, potrebbe essere coin flip. Ma il filtro di compressione aggiunge informazione.

### Strategia H: Accumulation/Distribution Intraday
- Monitora il flusso: se il prezzo scende ma il volume sulle candele rialziste è > volume candele ribassiste → accumulation
- Entry long su conferma di accumulation + price sotto VWAP
- Exit: ritorno al VWAP o fine sessione
- **Rischio:** volume su CFD potrebbe non riflettere il mercato reale. Usa volume SPY come proxy.

### Strategia I: Gamma Exposure Levels
- Usa i livelli di gamma exposure (GEX) da opzioni SPX come supporti/resistenze intraday
- Long a livelli di alto gamma positivo (dealer hedging crea supporto)
- Short a livelli di gamma negativo estremo (solo in bear confermati)
- **Rischio:** richiede dati di opzioni esterni (non su IG). Più complesso.

---

## 📊 Matrice di Priorità

| Strategia | Frequenza trade | Hold medio | Costi IG | Correlazione col Dip-Buy | Complessità | **Priorità** |
|---|---|---|---|---|---|---|
| **A: Late-Day Drift** | Alta (quasi daily) | 1-2h | ✅ Minimi | Bassa | Bassa | ⭐⭐⭐⭐⭐ |
| **B: MR sub-giornaliera** | Media-Alta | 30m-3h | ✅ Minimi | Media (stessa famiglia) | Media | ⭐⭐⭐⭐ |
| **E: Turn-of-Month** | Bassa (5gg/mese) | 1 giorno | ✅ Ok | Bassa | Molto bassa | ⭐⭐⭐⭐ |
| **C: VWAP MR** | Media | 30m-2h | ✅ Minimi | Media | Media | ⭐⭐⭐ |
| **D: 1st Hour Filter** | Bassa-Media | 2-4h | ✅ Ok | Bassa | Media | ⭐⭐⭐ |
| **F: Cross-Market** | Bassa | 1-4h | ✅ Ok | Bassa | Alta | ⭐⭐ |
| **G-I: Speculative** | Variabile | Variabile | ❓ | Variabile | Alta | ⭐ |

---

## 🔧 Suggerimento di Implementazione

### Ordine di test raccomandato:

```
1. Late-Day Drift (A)        → più facile, dati pronti, alta frequenza
2. Turn-of-Month (E)         → semplicissimo, pochi parametri da ottimizzare
3. MR sub-giornaliera (B)    → estensione naturale del tuo edge #1
4. VWAP MR (C)               → se hai volume o proxy
5. First-Hour Filter (D)     → se vuoi diversificare da MR
6. Cross-Market (F)          → se hai dati multi-strumento
```

### Template di test (per mantenere coerenza col tuo apparato):

```python
# Struttura suggerita per ogni nuovo backtest
def test_strategy(data, params, costs):
    """
    1. Genera segnali su in-sample (60% dei dati)
    2. Calcola metriche LORDE: WR, avg_trade, PF, maxDD
    3. Applica costi IG: spread + commissioni + financing (se hold > intraday)
    4. Ricalcola metriche NETTE
    5. Test del nulla: randomizza entry N volte, confronta distribuzione
    6. Out-of-sample (40%): ricalcola tutto
    7. Sweep parametri: variazioni ±20% dei parametri chiave
    8. Output: passa/non passa
    """
    pass
```

---

## 🎯 Il Portafoglio Ideale (se più edge sopravvivono)

La combinazione perfetta per il tuo setup sarebbe:

```
CORE:     Edge #1 Dip-Buy (già validato)        → cattura i drawdown di 2-5gg
INTRADAY: Late-Day Drift + MR sub-giornaliera    → P&L giornaliero, flat overnight
CALENDAR: Turn-of-Month                          → edge passivo, pochi trade
HEDGE:    Cross-Market o filtro di regime         → protezione nei bear ripidi
```

Questo portafoglio avrebbe:
- **Diversificazione temporale** (dal multi-day al sub-orario)
- **Diversificazione logica** (MR + calendario + cross-market)
- **Costi sotto controllo** (tutto intraday o hold corto)
- **Protezione nelle code** (regime filter + hedge)

> [!TIP]
> La strategia singola più promettente da testare **subito** è il **Late-Day Drift (A)**:
> - Hai già i dati 1m
> - È complementare al dip-buy
> - Pochi parametri → basso rischio di overfitting
> - Frequenza alta → statistica robusta velocemente
> - Costi trascurabili su IG
