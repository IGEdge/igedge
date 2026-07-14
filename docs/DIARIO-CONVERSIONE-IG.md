# Conversione CryptoQuantix → IG (CFD US500)

Log di lavoro della conversione del bot da **quant crypto (Deribit + Binance)** a
**quant CFD su IG (US500)**. Avviata l'11 luglio 2026.

Principio guida: **validare PRIMA, costruire l'infrastruttura live DOPO.**
Nessun codice di esecuzione IG finché i backtest non dimostrano che un edge
sopravvive su US500. È lo stesso rigore ("test del nulla") che il progetto
predica in [../microevolutive/CONVERSIONE-IG-API.md](../microevolutive/CONVERSIONE-IG-API.md).

---

## 1. Setup ambiente

### Credenziali IG (`.env`)
```
IG_API_KEY=…          # API key del conto DEMO (diversa dalla live!)
IG_IDENTIFIER=…       # username di login (non l'email)
IG_PASSWORD=…         # password del conto
IG_ACC_TYPE=DEMO      # DEMO -> demo-api.ig.com | LIVE -> api.ig.com
IG_ACCOUNT_ID=Z4YQIV  # conto CFD demo
IG_EPIC=IX.D.SPTRD.IFE.IP   # "US 500 Cash (1€)"
```

### Problema TLS su Windows (risolto)
Questa macchina intercetta l'HTTPS con una CA di proxy/antivirus che il bundle
`certifi` non contiene → `requests` fallisce la verifica. **Soluzione:**
`truststore.inject_into_ssl()` usa lo store certificati di Windows (dove quella
CA è già fidata). Iniettato all'import in `src/core/ig_client.py`; per Node
(Dukascopy) non funziona, quindi il downloader tick è in Python.

---

## 2. Cosa è stato costruito

| Componente | File | Stato |
|---|---|---|
| Client IG (login/session, account, mercati, prezzi) | `src/core/ig_client.py` | ✅ verificato su demo |
| Smoke test connessione IG | `scripts/test_ig_connection.py` | ✅ |
| Download US500 daily da IG | `scripts/download_us500_ig.py` | ✅ 5000 barre 2007-2026 |
| Download US500 tick/orario da Dukascopy | `scripts/download_us500_dukascopy.py` | ✅ Python+truststore |
| Lettore cache tick → barre 1m/1h | `src/data/dukascopy_cache.py` | ✅ |
| Backtest Macro Core su US500 (daily) | `scripts/backtest_macro_core_us500.py` | ✅ |
| Backtest Trend Breakdown su US500 (orario) | `scripts/backtest_trend_breakdown_us500.py` | ✅ in attesa dati |
| Ricerca sessioni + **test del nulla** | `scripts/session_research_us500.py` | ✅ |
| Lib harness neutra (provider storico + candele) | `scripts/_us500_lib.py` | ✅ |

### Strumento US500 su IG (parametri sizing confermati)
- Epic `IX.D.SPTRD.IFE.IP` = "US 500 Cash (1€)", INDICES, valuta **EUR**.
- **€1 per punto indice** per 1.0 lotto (`valueOfOnePip=1.00`). Size minima 1.0.
- Margine 5% (leva 20:1 ESMA). Stop minimo 1 pt (normale), 4 pt (garantito).
- Market order `AVAILABLE_DEFAULT_OFF` (va richiesto esplicitamente).
- **Formula sizing CFD** (per il futuro risk manager):
  `size_lotti = (equity × rischio%) / (distanza_stop_punti × 1€)`.

### Fonti dati
- **Daily**: IG `/prices` v2 (`/prices/{epic}/DAY/{N}`) — il v3 cappa a 20 barre.
  Quota 10k punti/settimana; 5000 daily consumati una tantum, in cache CSV.
- **Intraday**: Dukascopy tick `USA500IDXUSD` (prezzo /1000), aggregati a 1m/1h.
  ~6 slot/s (host lento) → download in background, cache-ato e ripartibile.

**Dove sono salvati i dati (nel progetto, NON si riscaricano):**
- `data/research/us500_daily.csv` — daily IG (~350 KB)
- `data/research/duka_cache/USA500IDXUSD/` — cache tick Dukascopy (~164 MB → ~500 MB)
- `data/research/us500_h1.csv` — orario aggregato (a fine download)
- Dettagli e idempotenza dei downloader: **`data/research/README.md`**.

---

## 3. Risultati di validazione (finora)

### Macro Core (port crypto) — ❌ BOCCIATA su US500
Backtest daily 2007-2026 (19,3 anni), codice reale della strategia:

| Scenario | Rendimento | CAGR | maxDD |
|---|---|---|---|
| Gross (zero costi) | +201% | +5,9%/yr | 26,9% |
| + financing 1,5 bps/g | +41% | +1,8%/yr | 35,5% |
| **Buy & hold indice** | **+437%** | **~9,2%/yr** | — |

**Perché fallisce (strutturale):** su BTC batteva il buy&hold schivando i crash
dell'80%; l'US500 ha trend secolare forte e drawdown miti, quindi un overlay
trend-following regala più upside di quanto salvi. E il **financing overnight**
sui hold di 205 giorni è un costo che nella validazione crypto non esisteva.
→ Archetipo "core long trend-following" sbagliato per un indice azionario.

### Fade dei livelli di sessione (tesi killzone) — NESSUN EDGE (definitivo sul fade nudo)
Test del nulla su **tutto il 2022-2026** (1,5M barre 1m, 2655 eventi completati):

| Sottoinsieme | N | E[R] reale | E[R] nullo | batte random | z |
|---|---|---|---|---|---|
| Incondizionato | 2655 | +0.404 | +0.434 | 7% | −1.32 |
| reg=RANGE | 1556 | +0.406 | +0.439 | 15% | −1.04 |
| reg=TREND | 1099 | +0.399 | +0.429 | 19% | −0.82 |
| LONDON←ASIA | 1239 | +0.417 | +0.395 | 75% | +0.63 |
| NY←LONDON | 1416 | +0.392 | +0.465 | 1% | −2.36 |

Su dati rappresentativi, il fade dei livelli di sessione **non batte livelli
casuali alla stessa distanza in nessun regime né coppia**. L'edge apparente
(+0.40 E[R] gross) è mean-reversion generico, non struttura di sessione.

**Continuation (l'ipotesi opposta) — testata, morta:** N=333 (rara: il 93%
degli sweep rientra entro 30 min → i breakout che tengono sono pochi), WR 37%,
E[R] −0.081, batte 16% del nulla. Gli sweep US500 non proseguono.

**Netto costi — il killer definitivo:** lo stop del fade è strettissimo (risk
medio **3.2 punti**, perché gli sweep superano il livello di poco). Con 2pt di
spread+slippage round-trip il costo è **0.62 R/trade** → il +0.40 gross diventa
**−0.64 netto, negativo in OGNI anno** (2022-2026, somma da −106 a −483 R/anno).
Anche a 1pt resta negativo. Più "veloce"/stretto il trade, più lo spread vince.

**VERDETTO: tesi "livello di sessione predice la direzione" FALSIFICATA su
US500** — in entrambe le direzioni (fade e continuation) e su entrambi i criteri
(struttura via test del nulla E tradeabilità netto costi). Non è un problema di
tuning: è microstruttura (sweep piccoli → stop stretti → i costi dominano).
Questo è il **criterio di STOP**: non si cercano altre varianti (= overfitting).
Framework riutilizzabile: `scripts/session_research_us500.py` (`--mode`, `--cost-pts`).

Altri "no" (per completezza): **Opening Range Breakout** sulle aperture US/Londra
= coin flip (E[R] gross ≈ 0, non batte un'ora morta); **overnight drift** = reale
lordo (+6.9%/yr) ma ucciso da financing + spread (−3.7%/yr netto).

**Trend Breakdown** (backtest orario 2022-2026, `scripts/backtest_trend_breakdown_us500.py`):
netto ~**piatta** (+0.7%). LONG side edge marginale (netto PF 1.17, +6.2%/4.5y ≈
1.4%/yr); SHORT side NESSUN edge (PF 0.93 — shortare un indice long-biased non
paga, come atteso). Non è un secondo edge forte; è long-biased quindi correla col
buy-the-dip invece di diversificarlo. Vera diversificazione = multi-mercato
(trend su FX/commodity/bond, non long-biased).

### ✅ Buy-the-Dip daily — PRIMO EDGE VALIDATO
Mean-reversion di breve (RSI2<10 in uptrend, exit su forza): **WR 79-80%**,
net/trade +0.38-0.46% (**sopravvive ai costi**: pochi trade + hold corti),
**regge out-of-sample** (WR 79% su 2018-2026 mai visto), **robusto** (9/9 combo
parametri positive). Raw ~3-4%/yr a 1x con maxDD ~11-14%; scalabile a 2-3x
(~6-11%/yr, DD 21-39%). Il financing è piccolo e leva-neutro; il limite è il
peggior trade / gap-risk. Documentazione completa: **[EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md)**.
Script: `scripts/mean_reversion_us500.py`. Prossimo: catastrophe stop + test
variante intraday + combinare edge.

---

## 4. Pulizia: rimosso il residuo crypto/Deribit

Rimossi dall'albero di lavoro (recuperabili da git history):
- **Esecuzione Deribit**: `deribit_client`, `order_manager`, `order_registry`,
  `position_monitor`, `risk_manager`, `failure_handler`, `flags`, `state_manager`.
- **Data layer Binance**: `binance_ingestion`, `orderbook_engine`, `data_quality`,
  `kline_provider`, `positioning_collector`.
- **Engine microstruttura crypto**: `orderflow`, `regime`, `scoring`.
- **Strategie crypto bocciate/non-portabili**: `funding_squeeze` (funding =
  concetto perp), `volume_breakout`, `mean_reversion`, `liq_squeeze`,
  `imbalance_scalp`, `smart_money`, `wm_formation`, `brings_strategy`,
  `iron_condor`, `pvsra_analyzer`.
- **Bot live crypto**: `async_trading_bot`, `trading_bot`, `main.py`, dashboard
  crypto, script crypto (download/backtest/research/sweep/test).

**Tenuto** (sotto validazione US500 o infrastruttura nuova): `ig_client`,
`base_strategy`, `macro_core`, `trend_breakdown`, `dukascopy_cache`, i backtest
US500, `config.py` (riscritto IG-oriented), i dati in `data/research/`.

---

## 5. Stato e tre strade per continuare

**Stato al 11 lug 2026 — EDGE TROVATO, DECISIONE = A (esecuzione live demo).**
Trovato il primo edge reale: **buy-the-dip intraday + scale-in** (vedi §3 e
**[EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md)**). Deciso di costruirci sopra il bot e
portarlo su IG demo. **Piano concreto: EDGE-1-compra-il-dip.md §7** (esecuzione IG +
sizing con leva + runtime strategia + paper trading demo). Le "tre strade" qui
sotto restano come contesto storico; B (multi-mercato) è il seguito naturale per
la diversificazione, dopo aver portato al vivo l'edge attuale.

**Bocciato dai dati (§3):** Macro Core (perde vs buy&hold), tesi livelli di
sessione (fade + continuation), ORB, overnight drift, Trend Breakdown (netto
piatto). L'apparato di validazione è riutilizzabile per ogni idea futura.

### Strada A — Trend Breakdown (la più veloce, già pronta)
Ultima strategia del piano originale non ancora testata, **meccanismo diverso**
(breakout di canale, non fade): short al breakdown del minimo 48h in macro-bear,
long al breakout del massimo 7g in macro-bull; hold corti → poco financing.
Dati e codice pronti:
```
python scripts/backtest_trend_breakdown_us500.py            # netto costi
python scripts/backtest_trend_breakdown_us500.py --gross    # lordo
```
Guardare **long vs short separati** e per anno. Nota: il gate `flow_confirm`
(taker flow) è disattivato — US500 non ce l'ha. Se regge il netto costi → è la
prima candidata al port live (Strada finale, sotto).

### Strada B — Riflessione strategica / cambia arena
Dopo due falsificazioni, l'ipotesi da valutare è che **l'intraday US500 retail
sia un'arena troppo efficiente/costosa** (spread su stop stretti = morte). Da
considerare PRIMA di altri test, per non cadere nell'overfitting:
- **timeframe più lento** (swing/daily): meno trade, spread meno rilevante,
  ma serve un edge daily reale (Macro Core no — servono altri meccanismi:
  mean-reversion sull'indice, stagionalità, breadth, momentum cross-sezionale);
- **tipo di edge diverso**: drift overnight (i rendimenti overnight degli indici
  battono storicamente quelli intraday), carry, volatilità/opzioni;
- **altro strumento** con microstruttura diversa (spread più stretti, o dove i
  livelli hanno più significato).
- Domanda onesta di fondo: vale la pena insistere su IG/US500, o l'edge sta
  altrove? Meglio deciderlo qui che dopo altri 10 backtest.

### Strada C — Opening Range Breakout (ORB) sull'apertura RTH
Pattern **diverso** dal fade delle sessioni, con edge documentato in letteratura
(anche se molto arbitraggiato): definire il range dei primi X minuti dopo
l'apertura cash RTH (~13:30 UTC), tradare il breakout di quel range. Da testare
con lo **stesso apparato** (`session_research_us500.py` è estendibile) e gli
stessi criteri: test del nulla + **netto costi** (qui è cruciale) + stabilità
annuale, deflazionato per multiple testing.

### Se una strada dà un edge reale → Adapter IG di esecuzione
Solo allora si scrive l'esecuzione live (finora c'è solo lettura in `ig_client`):
1. `open_position(epic, direction, size, stop_distance, limit_distance)` via
   `POST /positions/otc` (**SL/TP nativi attaccati** → niente ordini orfani),
   `GET /confirms/{dealRef}`, `GET /positions`, chiusura via `DELETE`.
2. **Sizing CFD lineare**: `size_lotti = (equity × rischio%) / (dist_stop_pt × 1€)`, min 1.0.
3. Paper trading su **demo** + guardrail (kill switch giornaliero, max posizioni).

### Criterio di STOP (già applicato alle sessioni)
Un setup si costruisce live SOLO se batte il nulla **E** resta positivo netto
costi **E** è stabile ogni anno, in-sample e out-of-sample. Altrimenti si
documenta il "no" e si cambia strada — non si cercano varianti all'infinito.
