> **ARCHIVIO STORICO** — proposte originali PRE-test (14 lug 2026). Gli esiti veri sono in `../EDGE-falsificati.md`; questo file resta solo come storia dei razionali.

# Strategie Intraday S&P 500 — Proposte da Backtestare

Tutte le proposte sono progettate intorno ai **vincoli IG CFD** che hai già identificato:
- ❌ Stop stretti → lo spread ti mangia
- ❌ Hold lunghi → il financing ti mangia
- ✅ Pochi trade + hold corti / flat overnight

> [!IMPORTANT]
> Ogni strategia va passata dal tuo apparato: backtest netto costi + split IS/OOS + sweep parametri + test del nulla (dove applicabile). Promuovi solo se batte il nulla, resta positiva netta, e stabile anno per anno.

---

## 🏆 TIER 1 — Alta probabilità di edge (struttura documentata in letteratura)

### Strategia A: Late-Day Drift (Power Hour Mean Reversion + Momentum) — ❌ FALSIFICATA (13 lug 2026)

> **Esito test:** nessun edge. Il drift dell'ultima ora è ≈0 anche incondizionato
> (t≈−0.25); condizionare "giorno in calo" NON aiuta (la MR verso la chiusura non
> esiste su US500); la continuation sui giorni forti è marginale e fragile (t≈1.7
> a 14:00 ET, sparisce a 15:00). Non batte il nulla, netto costi negativo,
> instabile per anno. Dettaglio nella tabella FALSIFICATI sopra.
> Script: `scripts/late_day_drift_us500.py`. Il razionale sotto resta come storia.

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

### Strategia B: Intraday Oversold Bounce (MR sub-giornaliera) — ❌ FALSIFICATA come tradeable (13 lug 2026)

> **Esito test:** struttura REALE ma NON tradeable. RSI2<5/<10 su 15m batte il
> nulla in modo netto (fino a z=+5, 100% dei random) → il bias MR intraday esiste
> e conferma la genuinità dell'edge #1. MA E[ret] è negativa **anche lorda** in
> ogni combo (entry/exit/VWAP), OOS negativa, instabile: l'**intraday long su
> US500 è headwind** (il premio azionario è overnight) e il micro-rimbalzo non
> batte headwind + spread. La reversione paga su GIORNI (edge #1), non compressa
> intraday. Dettaglio nella tabella FALSIFICATI sopra. Script:
> `scripts/intraday_mr_us500.py`. Il razionale sotto resta come storia.

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

### Strategia C: VWAP Mean Reversion — ❌ FALSIFICATA come tradeable (13 lug 2026)

> **Esito:** come B — struttura fortissima (z=+6, batte 100% dei random) ma gross
> ≈0 e netto negativo per l'headwind intraday long. Non tradeable. Tabella
> FALSIFICATI sopra. Script: `scripts/vwap_mr_us500.py`. Razionale sotto = storia.

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

### Strategia D: First-Hour Momentum Filter (NON è un ORB!) — ❌ FALSIFICATA (13 lug 2026)

> **Esito:** la prima ora È informativa (struttura batte il nulla z=+2.5…+4) ma
> la strategia è netto negativa (−0.04…−0.06%, tutti gli anni negativi), payoff
> avverso (99 stop vs 78 target) + headwind intraday. Non tradeable, robusto al
> variare dei parametri. Tabella FALSIFICATI sopra. Script:
> `scripts/first_hour_us500.py`. Razionale sotto = storia.

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

### Strategia E: Effetti Calendario Intraday (già nella tua lista) — ❌ ToM FALSIFICATO (13 lug 2026)

> **Esito test (Turn-of-Month):** nessun edge su US500 2008-2026. I 5 giorni ToM
> non rendono più dei giorni normali (batte solo 58% del nulla, z=+0.18); netto
> costi ≈0; instabile. Dettaglio nella tabella FALSIFICATI sopra. Script:
> `scripts/turn_of_month_us500.py`. Restano non testati (dentro "Effetti
> Calendario"): pre-festivi e day-of-week — ma stessa attesa (effetti noti,
> arbitraggiati). Il razionale sotto resta come storia.

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

> **Esito (13 lug 2026):** G e H testati (`tier3_intraday_us500.py`) → falsificati.
> G (squeeze) non ha struttura (batte 0% del nulla). H (accum/dist) ha struttura
> reale (z=+2.9, WR 76%) ma netto ≈0 per l'headwind intraday. I (gamma/GEX) **non
> testabile**: richiede dati opzioni SPX esterni (non su IG). Dettagli in tabella
> FALSIFICATI sopra.

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


