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

## 🔬 PROMETTENTE — passato i gate a modello, manca il gate COSTI IG

### Volatility Risk Premium (short-vol a rischio definito) — vendere opzioni US500
**→ Documento completo e vivo: [EDGE_SHORTVOL.md](EDGE_SHORTVOL.md).** Sintesi qui sotto.

Primo candidato che **avanza** dopo 8 falsificazioni sul prezzo. È **non-direzionale**
(aggira l'headwind/segnale-piccolo che uccide le idee intraday) e sfrutta un premio
noto e robusto. Script: `vrp_probe_us500.py`, `short_vol_us500.py`, `download_vix.py`.

- **Il premio ESISTE (misurato):** VIX vs realized 21g dell'S&P 2007-2026 →
  VRP medio **+3.6 punti vol** (mediana +4.7), **t=+32.7**, positivo **82%** del
  tempo, positivo ogni anno tranne 2008. VIX/RV 1.37x.
- **Coda brutale:** feb 2020 VRP −60 (VIX 14 → RV 74), 2008 −50. Vendere vol nudo
  esplode → **obbligatorio rischio definito** (iron condor / put spread).
- **Modello a rischio definito (BS a vol=VIX, lordo spread IG):** iron condor 1M,
  short a a·σ√T / wing a b·σ√T. Robusto su TUTTI gli strike (a=0.75→1.5):
  WR 81-96%, **t=5.5→7.4**, CAGR +5→+18%/yr @10% rischio/trade, maxDD 10-21%.
  Plateau, non picco. Il put-spread singolo lato è mediocre (CAGR +3.4%): serve
  il condor (premio su entrambi i lati).
- ✅ **GATE COSTI IG SUPERATO (13 lug 2026, catena reale).** Spread opzioni IG
  US500 misurato dalla chain live (scad. mensile, sottostante 7580): **~1.8 punti
  per gamba**, costante su tutta la catena. Iron condor = 4 gambe → **~3.6 pt di
  costo d'ingresso** se **tenuto a scadenza** (settlement a intrinseco, niente
  spread in uscita). Rifatti i conti NETTI (`short_vol_us500.py --spread-leg 1.8`):
  strike 0.75-1.0σ → **WR 79-88%, t=+4.6/+4.8, CAGR +7.6/+11.4%/yr, maxDD 19-23%**.
  L'edge **sopravvive** allo spread reale. ⚠️ Ma serve **hold-to-expiry**: se si
  chiude sempre in anticipo (round-trip, ~7.2pt) scende a t=1.9 / CAGR 2.9%.
  Strike stretti = più credito vs lo spread fisso = più robusti ai costi.
- **Prossimi passi:** (1) confermare che le opzioni mensili IG su US500 si
  **liquidano a scadenza a intrinseco** (per l'assunzione hold-to-expiry); (2)
  **paper trading sul demo** IG (conto opzioni `Z4YQIW`) per fill/settlement reali —
  richiede login IG a posto (api-key demo ora `api-key-missing`); (3) **gestione
  coda** (sizing sul max-loss, eventuale regime filter — da TESTARE, non assumere:
  peggior trade −100% del rischio in crash 2008/2020, DD clusterizzati lì).
  **Criterio residuo:** confermare settlement + paper trading coerente col modello.
  Nota a favore non ancora sfruttata: lo skew reale degli index put alza il credito
  lato put (BS-flat lo ignora → margine extra reale probabile).

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
| **Late-Day Drift** (power hour, Strat. A) | `late_day_drift_us500.py` | Nessun drift dell'ultima ora (E[ret]≈0 **incondizionato**, t≈−0.25). MR sui giorni in calo NON esiste: condizionare "day down" peggiora (semmai lieve continuation). Continuation sui giorni forti (>+1%) marginale (t≈1.7 a 14:00 ET) ma **evapora** a 15:00 (t≈0.5) → fragile/overfit. Non batte il nulla in nessuna combo (entry 12-15 ET × dip 0/−0.5 × trend on/off, 2022-2026). Netto costi negativo, instabile per anno (2022 −0.34%/trade). |
| **Turn-of-Month** (Strat. E) | `turn_of_month_us500.py` | I 5 gg ToM (ultimi 2 + primi 3) NON battono i giorni normali: intraday ToM +0.055% ma non-ToM +0.048% e TUTTI +0.050% con t **più alto** (2.9) → nessun premio ToM, è solo il drift intraday generico. Test del nulla: batte solo 58% dei subset random (z=+0.18). Netto costi ≈0 (+0.007%, t=0.19). Instabile (retto solo da 2020 COVID + 2023), IS negativo. Anche close-to-close ToM (+0.043%) = non-ToM (+0.042%). Effetto arbitraggiato via (noto dagli anni '80). 2008-2026. |
| **Intraday MR 15m** (Strat. B) | `intraday_mr_us500.py` | ⚠️ Caso speciale: **struttura REALE** (RSI2<5/<10 su 15m batte il nulla fino a z=+5, 100% random → la famiglia MR dell'edge #1 è genuina) ma **NON tradeable**: E[ret] negativa **anche lorda** (−0.01…−0.02%) in ogni combo (entry/exit/VWAP), netto peggiore, OOS negativo, instabile. Motivo: su US500 l'**intraday long è headwind** (premio azionario overnight; long random intraday perde −0.02…−0.09%); il micro-rimbalzo di ~70min è troppo piccolo per battere headwind + spread. Negativo a costo zero → nessuna leva lo salva. **Lezione:** la reversione paga su GIORNI (edge #1, cattura l'overnight), non compressa intraday. 2022-2026. |
| **VWAP MR 15m** (Strat. C) | `vwap_mr_us500.py` | Stessa firma di B. Struttura fortissima (long sotto VWAP−1.5σ/−2.5σ batte il nulla a **z=+6**, 100% random) ma gross ≈0 (+0.004…+0.007%, t≈0.4) → netto **negativo** (−0.01…−0.02%), OOS negativo, instabile (solo 2026 positivo). Deviazioni più profonde non lo raddrizzano. Headwind intraday + spread. 2022-2026. |
| **First-Hour Filter** (Strat. D) | `first_hour_us500.py` | Non-ORB (filtro direzionale prima ora 09:30-10:30 ET + entry su pullback 50%, target=high, stop=low, filtro AT>med). Struttura reale (batte il nulla z=+2.5…+4 → la prima ora è informativa, come Gao et al.) ma **netto negativo** (−0.04…−0.06%, t≈−2.2), gross ≤0, OOS negativo, TUTTI gli anni negativi. Payoff avverso (99 stop vs 78 target) + headwind intraday. Robusto al variare di soglia/pullback/regime: sempre negativo. 2022-2026. |
| **Midswing-Fade** (short al 50% ritracc.) | `midswing_fade_us500.py` | **Ucciso al Test 1 (placebo/falsificazione)**, la sua stessa metodologia pre-registrata. Il livello di ritracciamento (0.382/0.5/0.618) è **statisticamente indistinguibile** da livelli casuali U(0.30,0.70) sulla stessa gamba: MFE/MAE reali ≈ placebo (KS p=0.9+, bootstrap p=0.3+), in diverse combo il reale è pure peggio del placebo. Robusto su k_swing∈{2,3,4}×a_min∈{3,5}×r_entry×window. Nessuna proprietà speciale del livello → rumore. Per la spec ci si ferma qui (niente filtri di salvataggio). Era l'unica idea SHORT (aggirava l'headwind) → morta comunque. US500 5m RTH 2022-2026. |
| **Volatility Squeeze** (Strat. G, Tier 3) | `tier3_intraday_us500.py --strat squeeze` | Breakout post-squeeze Bollinger(20,2): netto +0.05% (t=1.2) ma **batte 0% del nulla, z=−5** → il timing del breakout è ATTIVAMENTE peggio di entry random (null +0.18% vs reale +0.07%). Nessuna struttura, il positivo è solo la selezione dei giorni uptrend. N=87. 2022-2026. |
| **Accum/Distribution** (Strat. H, Tier 3) | `tier3_intraday_us500.py --strat accdist` | Stessa firma di B/C: **struttura reale** (accumulo sotto VWAP batte il nulla z=+2.9, WR gross 76%) ma **netto ≈0** (+0.004%, t=0.26), IS e OOS ≈0 → headwind intraday. Non tradeable. 2022-2026. |

**Lezione trasversale:** su CFD IG US500 i costi uccidono tutto ciò che ha stop
stretti (spread) o hold lunghi (financing). Sopravvive solo: pochi trade + hold
corti (dip-buy) o intraday (flat overnight).

**Lezione #2 (dai test 13 lug 2026, CORRETTA): il problema dell'intraday non è un
"headwind direzionale" ma il RAPPORTO SEGNALE/COSTO.** Misura pulita sulla vera
sessione cash RTH (Dukascopy 09:30→16:00 ET, 2022-2026): intraday open→close
**+5.5%/yr (t=0.8)**, overnight 16:00→09:30 **+7.0%/yr (t=1.3)**. Entrambi POSITIVI
ma deboli/non significativi; l'overnight è solo un po' più grande (anomalia
classica presente ma NON robusta su questo campione — e sul daily IG 2008-2026,
con la sua convenzione di barra, l'intraday risulta +13%/yr: dipende da come si
tagliano le ore). Quindi B/C/D/H NON falliscono per un headwind: falliscono perché
il segnale cattura un movimento troppo piccolo (~0.02–0.05%) rispetto a spread
(~0.02%) e al rumore (vol/gg 1.2%), e le exit logic hanno skew avverso (tagliano i
vincitori). La struttura è reale (z fino a +6) ma il margine NETTO è ≈0. Corollario
invariato: l'edge #1 rende perché la reversione si sviluppa su GIORNI (segnale
grande vs costo), non compressa intraday. La direzione a più alto EV resta il
**multi-mercato** (segnali più grandi, scorrelati), non un'altra idea intraday US500.
[nota: nelle righe FALSIFICATI sopra "headwind intraday" va letto come questo
problema segnale/costo, non come un drift direzionale negativo robusto.]

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




# MIDSWING-FADE — Project Prompt — ❌ FALSIFICATO al Test 1 (13 lug 2026)

> **Esito:** il gate placebo (§4, il primo test obbligatorio) ha **ucciso**
> l'ipotesi. Il livello di ritracciamento (0.382/0.5/0.618) è statisticamente
> indistinguibile da livelli casuali sulla stessa gamba (MFE/MAE reali ≈ placebo,
> KS p=0.9+, bootstrap p=0.3+), robusto su tutti i parametri richiesti. Per il
> criterio di kill della spec ci si ferma qui, senza filtri di salvataggio.
> Implementato in `scripts/midswing_fade_us500.py` (ZigZag ATR causale + eventi
> reali/placebo + KS/bootstrap). Se un giorno si vuole rivalidare con dati proper
> (ES/MES Databento + SPY Alpaca) e la pipeline completa (Test 2/3, DSR/CPCV/
> walk-forward), la spec sotto resta il riferimento — ma il Test 1 su US500 dice
> rumore. La spec integrale resta come metodo di riferimento riutilizzabile.

## 0. Scopo

Verificare se il **fade del ritracciamento intermedio** costituisce un edge statistico
sull'S&P 500 intraday, o se è una regolarità apparente indistinguibile dal rumore.

Ipotesi da testare (formulata dal pattern osservato):

> Dopo un impulso ribassista definito, il prezzo rimbalza. Quando il rimbalzo
> raggiunge il ~50% dell'impulso, uno short a quel livello ha aspettativa positiva,
> con target al ~50% del rimbalzo stesso (≈25% dell'impulso originale).

Il progetto **non deve confermare l'ipotesi**. Deve tentare di ucciderla e riportare
onestamente se sopravvive.

---

## 1. Principio metodologico vincolante

L'errore da evitare è la **tautologia ex-post**: "i rimbalzi che si fermano al 50%
poi scendono" è vero per costruzione. La domanda corretta è **condizionale**:

> Dato che il prezzo ha *toccato* il livello 50% del rimbalzo, quale è la
> distribuzione del movimento successivo?

Al momento del tocco, un rimbalzo che sta per esaurirsi e uno che tirerà fino al 78%
o al 100% sono **indistinguibili**. Il campione deve includere entrambi.
Qualsiasi definizione dell'evento che richieda informazione futura (es. "il rimbalzo
il cui massimo è al 50%") è look-ahead e invalida il test.

---

## 2. Dati

- **Strumento primario**: ES / MES futures continui (Databento), 1-minuto, back-adjusted.
- **Cross-check**: SPY 1-minuto (Alpaca) per confermare che il risultato non dipenda
  dalla costruzione del contratto continuo.
- **Periodo**: minimo 2015–oggi (deve includere 2018 vol shock, 2020 COVID, 2022 bear,
  2024–25 regime a bassa vol).
- **Sessione**: solo RTH (14:30–21:00 UTC) per il test base. L'estensione a sessioni
  Asia/Londra è una **fase successiva**, non parte del test primario.
- **Costi**: spread + commissioni + 1 tick di slippage per lato, applicati sempre.
  Nessun risultato viene riportato lordo.

---

## 3. Definizione algoritmica dell'evento

Nessuna identificazione visiva. Tutto deve essere riproducibile da codice.

### 3.1 Impulso (gamba A)
Swing detection via **ZigZag normalizzato ad ATR**:
- `ATR(14)` su barre a 5 minuti.
- Un pivot è confermato quando il prezzo inverte di `k_swing × ATR` dal punto estremo.
- `k_swing ∈ {2.0, 3.0, 4.0}` — parametro da testare, non ottimizzare a mano.
- Gamba A = movimento da pivot-high `H0` a pivot-low `L0`, con ampiezza
  `A = H0 − L0`, valida solo se `A ≥ a_min × ATR` (`a_min ∈ {3, 5}`).

**Vincolo critico**: il pivot `L0` è confermato solo *dopo* la risalita di `k_swing × ATR`.
Il timestamp di conferma, non quello del minimo, è il primo istante in cui la
strategia "sa" della gamba A. Ogni calcolo successivo parte da lì.

### 3.2 Rimbalzo (gamba B) e trigger
- Retracement corrente: `R_t = (P_t − L0) / A`.
- **Evento E**: primo tocco di `R_t ≥ 0.50` (parametrizzato: `r_entry ∈ {0.382, 0.50, 0.618}`).
- Entry: short al primo tocco (limit al livello) e, in variante, alla chiusura
  della barra 5m che tocca il livello. Confrontare le due fill assumptions.
- L'evento è **unico per gamba A**: un solo trade per impulso, niente ri-entrate.

### 3.3 Stop e target
- **Stop**: `H0` (100% dell'impulso) — variante conservativa;
  oppure `r_entry + s × ATR` — variante stretta. Testare entrambe.
- **Target**: 50% della gamba B **misurata al momento dell'entry**, cioè
  `P_target = P_entry − 0.5 × (P_entry − L0)`.
  Nota: questo è ≈ il 25% di A solo se `r_entry = 0.50`. Non hard-codare 25%.
- **Time stop**: chiusura a fine sessione RTH. Nessun overnight.

---

## 4. Test 1 — Il livello ha proprietà speciali? (test di falsificazione)

Questo è il test che deve venire **per primo**, prima di qualunque backtest di equity.

Costruire un **controllo placebo**:
- Per ogni evento E al 50%, generare N=20 eventi sintetici a livelli casuali
  `r_random ~ U(0.30, 0.70)` sulla stessa gamba A, con identiche regole di uscita.
- Misurare per entrambi i gruppi la distribuzione di **MFE e MAE** nelle 60 barre
  successive, normalizzata ad ATR.

**Criterio di kill**: se la distribuzione MFE/MAE al 50% non è statisticamente
distinguibile dal placebo (test di Kolmogorov–Smirnov + differenza di medie con
bootstrap, α = 0.01), **il pattern è rumore**. Il progetto si ferma qui e lo si
riporta come tale. Non si procede a "sistemare" con filtri.

---

## 5. Test 2 — Distribuzione condizionale

Se il Test 1 sopravvive:

Stimare `P(MFE ≥ target | evento E)` e la distribuzione completa del path, **non solo
il win rate**. Riportare:
- win rate, R medio, distribuzione dei R multipli;
- aspettativa netta costi;
- distribuzione condizionata al **regime**:
  - VIX quintili;
  - trend giornaliero (posizione rispetto alla VWAP di sessione e alla EMA200 daily);
  - ora del giorno (prima ora / mid-day / ultima ora);
  - `A / ATR` (dimensione dell'impulso).

**Ipotesi da testare esplicitamente**: l'edge, se esiste, non sta nel livello ma nel
**modo in cui il prezzo raggiunge il livello**. Aggiungere come feature:
- velocità della gamba B (barre impiegate per coprire il retracement);
- contrazione del range nelle ultime k barre prima del tocco;
- rapporto volume gamba B / volume gamba A;
- se il tocco è per estensione (spike) o per drift.

---

## 6. Test 3 — Validazione statistica

Obbligatorio, non opzionale:
- **Conteggio esplicito di tutte le combinazioni testate**
  (`k_swing × a_min × r_entry × stop × fill` = numero di trial).
- **Deflated Sharpe Ratio** (López de Prado) sul best performer, con il numero di trial
  effettivo.
- **Combinatorial Purged Cross-Validation** (CPCV) con embargo, non train/test semplice.
- Soglia di t-statistic secondo Harvey/Liu: `|t| > 3.0` come minimo, non 2.0.
- **Walk-forward** su finestre da 2 anni, step 6 mesi. Riportare la degradazione
  out-of-sample, non solo il risultato aggregato.

**Criterio di kill**: DSR < 0 oppure edge che scompare out-of-sample → chiuso.

---

## 7. Deliverable

1. `data_loader.py` — ingestione e allineamento ES/SPY, gestione contratti.
2. `swing_detector.py` — ZigZag ATR con conferma pivot causale (test unitari
   che dimostrino assenza di look-ahead).
3. `event_builder.py` — costruzione eventi E + placebo.
4. `experiment_1_placebo.py` — Test 1, con report KS + bootstrap.
5. `experiment_2_conditional.py` — distribuzioni condizionali per regime.
6. `experiment_3_validation.py` — DSR, CPCV, walk-forward.
7. `REPORT.md` — conclusione binaria: **edge / non-edge**, con i numeri.
   Se non-edge, dirlo chiaramente. Nessun salvataggio del pattern con overfitting.

---

## 8. Vincoli espliciti al modello che esegue

- Non aggiungere filtri *dopo* aver visto i risultati per far apparire un edge.
  Ogni filtro va dichiarato prima e conteggiato come trial.
- Non riportare mai equity curve senza costi.
- Non usare il massimo/minimo del rimbalzo nella definizione dell'entry.
- Se il risultato è negativo, il deliverable corretto è un report negativo.