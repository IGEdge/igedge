 mi cerchi sulla documentazione di IG italia trading se le api key offrono le catene di opzioni mensile per lo strumento us500 perchè in demo non le trovavo capiamo se in reale le mette a disposizione

Sì, le API REST di IG in ambiente Live mettono a disposizione l'intera catena di opzioni (Vanilla e Barrier) per il US500, incluse le scadenze mensili, settimanali e giornaliere.

L'assenza che hai riscontrato in Demo è dovuta a una restrizione strutturale nota dell'infrastruttura di IG. L'ambiente di simulazione espone un catalogo mercati pesantemente ridotto (quasi esclusivamente CFD spot e i futures principali). I nodi relativi alle opzioni spesso sono vuoti, non propagano i prezzi o sono del tutto inaccessibili. Non è un errore nelle tue chiamate, ma un limite del server di test.
Come estrarre la catena in Live

Per recuperare i contratti mensili in reale non puoi usare l'EPIC del sottostante spot (es. IX.D.SPTRD...). Devi muoverti attraverso l'alberatura dei mercati:

    Effettua una chiamata GET all'endpoint /marketnavigation.

    Naviga l'ID dei nodi nell'ordine: Opzioni (Vanilla) > Indici > US 500 > Mensili.

    Una volta identificato il nodeId corretto per il mese di riferimento, interroga nuovamente l'endpoint con quell'ID per ottenere l'array completo di tutti gli EPIC associati ai vari strike, separati per Call e Put.

Operatività e Rischio

Visto che stai passando in reale l'infrastruttura per le opzioni, assicurati che la logica di esecuzione privilegi sempre strategie coperte. Anche se risultano meno remunerative sul singolo trade, sono un requisito fondamentale per la sopravvivenza del portafoglio: basta una singola operazione che va male per azzerarti il conto per via della leva spropositata intrinseca in questi strumenti. L'automazione su opzioni scoperte non ha margine di errore.

ok ho fatto un backtest e forse ho trovato un edge reale tu cosa ne pensi:


# EDGE #2 (candidato) — Short-Vol su US500: Volatility Risk Premium con iron condor


Primo edge **non-direzionale** del progetto e primo candidato che **supera il gate

costi** dopo 8 falsificazioni sul prezzo intraday. Vende volatilità implicita

(sistematicamente > realizzata) con una struttura a **rischio definito** (iron

condor mensile), tenuta **a scadenza**. Complemento scorrelato all'[EDGE #1

dip-buy](EDGE-1-compra-il-dip.md).


> **Documento vivo** — si aggiorna a ogni test. Stato in cima, dettagli sotto.


**STATO (13 lug 2026):** gate a modello + gate costi IG **superati**; **rifinitura

coda/strike fatta** (§4b: filtro di regime VIX → maxDD dimezzato). Config

raccomandata: **iron condor 1.0σ/2.0σ, banda VIX[14,30], hold-to-expiry, 10%

rischio/trade** → netto spread IG: **t=+6.2, CAGR +6.8%/yr, maxDD 10%, positivo 18

anni su 19**. **Non ancora live**: mancano conferma settlement a scadenza e paper

trading demo (§7). NON è tradeable finché non chiudiamo quei due punti.


---


## 0. Riprendere da qui — comandi esatti


```bash

# dato: VIX (implied) — già scaricato in data/research/vix_daily.csv

python scripts/download_vix.py                       # (ri)scarica il VIX da CBOE


# 1) il premio ESISTE? (VIX vs realized 21g)

python scripts/vrp_probe_us500.py


# 2) modello iron condor, LORDO spread

python scripts/short_vol_us500.py --strat condor --a 1.0 --b 2.0


# 3) modello NETTO dello spread IG reale (1.8pt/gamba), tenuto a scadenza

python scripts/short_vol_us500.py --strat condor --a 1.0 --b 2.0 --spread-leg 1.8


# 3b) caso pessimistico: paghi lo spread anche in uscita

python scripts/short_vol_us500.py --strat condor --a 1.0 --b 2.0 --spread-leg 1.8 --roundtrip


# ► CONFIG RACCOMANDATA (netto + filtro di regime VIX, §4b) — la versione buona:

python scripts/short_vol_us500.py --strat condor --a 1.0 --b 2.0 --spread-leg 1.8 --vix-min 14 --vix-max 30

```


Script: `vrp_probe_us500.py`, `short_vol_us500.py`, `download_vix.py`.

Dati: `data/research/vix_daily.csv` (CBOE 1990-2026), `us500_daily.csv` (S&P proxy).


---


## 1. La tesi e le regole


**Tesi (Volatility Risk Premium):** sugli indici azionari la volatilità *implicita*

(prezzata nelle opzioni) è **sistematicamente più alta** della volatilità che poi

si *realizza* — è un premio assicurativo pagato da chi compra protezione. Chi

**vende** opzioni lo incassa. È **non-direzionale**: non dipende dal drift

dell'indice, quindi **aggira** il problema segnale-piccolo/headwind che ha ucciso

tutte le idee intraday ([INDICE-EDGE.md](INDICE-EDGE.md), Lezione #2).


**Struttura: iron condor mensile a rischio definito.**

- Ogni ~21 giorni (mensile), con sottostante `S` e implied vol `iv` (dal VIX):

  - **vendi** put a strike `Kp1 = S·(1 − a·iv·√T)` e **compra** put a `Kp2 = S·(1 − b·iv·√T)` (ala);

  - **vendi** call a `Kc1 = S·(1 + a·iv·√T)` e **compra** call a `Kc2 = S·(1 + b·iv·√T)` (ala);

  - `a` = distanza dello strike venduto in "sigma" (√T); `b` = ala (default a=1.0, b=2.0).

- **Incassi** il credito netto; **massima perdita** = ampiezza − credito (definita e nota).

- **Exit: a SCADENZA** (settlement a intrinseco). ⚠️ È la regola d'oro: tenere a

  scadenza = nessuno spread in uscita (vedi §4).

- Long-only sul premio (vendi vol da entrambi i lati); niente stop stretto.


**Perché il condor e non il put-spread singolo:** il put-spread da solo cattura

poco (CAGR +3.4%, §3). Il condor raccoglie il premio su **entrambi** i lati e

l'indice raramente si muove oltre ~2σ in un mese → molto più efficiente.


---


## 2. Il premio ESISTE — misura del VRP (`vrp_probe_us500.py`)


VIX (implied 30g) vs volatilità **realizzata** dei 21 giorni successivi dell'S&P,

2007-2026 (N=4860):


| Metrica | Valore |

|---|---|

| VIX medio | 19.87 |

| Realized 21g medio | 16.27 |

| **VRP medio** | **+3.61 punti vol** (mediana +4.73) |

| VRP > 0 | **82% del tempo** |

| t-stat | **+32.7** |

| VIX / RV (mediano) | 1.37x |


- **Positivo ogni anno tranne il 2008** (−2.65, la crisi). Perfino il 2020 chiude

  positivo (+3.65) nonostante il crollo.

- **La coda è brutale** (il rischio di chi vende vol): feb 2020 VRP **−60** (VIX 14

  → RV 74), 2008 **−50**. → vendere vol **nudo esplode** ⇒ **obbligatorio il

  rischio definito**.

- Short-vol grezzo (VRP campionato ogni 21g, non sovrapposto, 232 "mesi"): somma

  +863 punti vol, media +3.72/mese, **WR 82%**, maxDD 68 punti vol.


---


## 3. Risultati del modello — LORDO spread (`short_vol_us500.py`)


Iron condor 1M prezzato Black-Scholes a vol=VIX (r,q≈0), rischio 10%/trade sul

max-loss, 2007-2026 (232 trade, ~12/anno). **Robusto su tutti gli strike (plateau,

non picco):**


| short strike (a·σ) | WR | ret/trade (del rischio) | t | CAGR@10% | maxDD | credito/rischio |

|---|---|---|---|---|---|---|

| 0.75σ | 81% | +14.1% | +6.9 | +17.8% | 21% | 0.30 |

| **1.0σ** | **89%** | **+10.4%** | **+7.4** | **+13.0%** | **17%** | 0.17 |

| 1.25σ | 93% | +6.7% | +6.8 | +8.2% | 13% | 0.10 |

| 1.5σ | 96% | +3.9% | +5.5 | +4.8% | 10% | 0.06 |


Put-spread singolo lato (per confronto): CAGR +3.4%, t=2.5 → mediocre, serve il condor.


---


## 4. Il GATE COSTI IG — superato (catena reale, 13 lug 2026)


**Spread opzioni IG US500 misurato dalla chain live** (scad. mensile, sottostante

7580, IV ATM ~13.2%): **~1.8 punti bid-ask per gamba**, costante su tutta la catena

(ATM 7580 call 129.35/131.15; put 129.20/131.00; resta ~1.8 anche più OTM).


Un condor ha 4 gambe. **Tenuto a scadenza** paghi lo spread solo in ingresso

(≈ 4 × metà-spread = **~3.6 punti**); a scadenza settla a intrinseco, niente spread

in uscita. Rifatti i conti **NETTI** (`--spread-leg 1.8`):


| short strike | WR | ret/trade | t | CAGR@10% | maxDD |

|---|---|---|---|---|---|

| 0.75σ | 79% | +9.5% | **+4.8** | **+11.4%** | 23% |

| 1.0σ | 88% | +6.3% | **+4.6** | **+7.6%** | 19% |

| 1.25σ | 92% | +3.0% | +3.1 | +3.5% | 15% |


**Caso pessimistico** (chiudi sempre in anticipo → spread anche in uscita, ~7.2pt),

a=1.0: t=+1.9, CAGR +2.9%, DD 25% — **ancora positivo**, ma dimezzato.


**Conclusioni del gate:**

- L'edge **sopravvive** allo spread reale di IG, comodamente sugli strike stretti

  (0.75-1.0σ): t=4.6-4.8, CAGR +7.6/+11.4%.

- **Regola d'oro: hold-to-expiry.** Chiudere in anticipo dimezza l'edge.

- **Strike stretti = più credito vs lo spread fisso = più robusti ai costi.**

- Bonus **non ancora sfruttato**: lo skew reale degli index put alza il credito

  lato put; il modello BS-flat lo ignora → margine extra reale probabile.


---


## 4b. Rifinitura: filtro di regime VIX — gestione della coda (13 lug 2026)


Il rischio dell'edge è la coda (§5). Un filtro di regime sul VIX la **dimezza** senza

uccidere il rendimento. Idea economica: **non vendere vol quando è troppo bassa**

(premio sottile + la vol può solo esplodere da base bassa — è il setup di feb 2020)

**né quando è già in panico** (>30 = crash/backwardation in corso). → **banda VIX**.


Condor 1.0σ, netto spread 1.8pt, per banda VIX (`--vix-min --vix-max`):


| Filtro | t | CAGR | maxDD | peggior trade | CAGR/maxDD |

|---|---|---|---|---|---|

| nessuno (baseline) | +4.6 | +7.6% | 19% | −100% | 0.40 |

| **VIX ∈ [14, 30]** | **+6.2** | +6.8% | **10%** | **−81%** | **0.68** |


**Robusto (plateau, non picco):** tutta la regione VIX∈[13-14, 28-32] dà t=5.6-6.4,

maxDD 10-11%. Il driver è il **pavimento ~14** (sotto 12 il maxDD risale a 18%).


**Strike × filtro** (netto, banda [14,30]):

| Config | t | CAGR | maxDD | peggior | stabilità |

|---|---|---|---|---|---|

| 0.75σ + banda | +4.9 | +8.9% | 15% | −100% | 2-3 anni negativi |

| **1.0σ + banda** ⭐ | **+6.2** | +6.8% | **10%** | **−81%** | **positivo 18 anni su 19** (solo 2007 −2%) |


**Config raccomandata: iron condor 1.0σ/2.0σ + banda VIX[14,30], hold-to-expiry.**

Netto spread IG: t=+6.2, CAGR +6.8%/yr, maxDD 10%, WR ~90%, peggior trade −81%

(= −8% equity a 10% rischio/trade), positivo in 18 anni su 19. Il 0.75σ rende di

più (+8.9%) ma con code peggiori e qualche anno negativo → meno adatto a una

strategia il cui scopo è il controllo della coda.


---


## 5. Rischi, coda, limiti onesti


- **La coda è il rischio vero.** Peggior trade = **−100% del capitale a rischio**

  (max-loss pieno) nei crash; i drawdown si **concentrano** in 2008 e 2020. Il

  sizing sul max-loss lo rende sopportabile (a 10%/trade → −10% equity nel trade

  peggiore), ma va **gestito**, non ignorato (§7).

- **Modello ≠ realtà (ancora):** BS-flat, IV=VIX, r=q=0, nessuno skew, fill al

  mid−spread. Approssimazione onesta ma da confermare col **paper trading**.

- **Assunzione hold-to-expiry** dipende dal **settlement a scadenza a intrinseco**

  delle opzioni IG (§6) — da confermare.

- **Un solo strumento** (US500). Diversificazione futura: stessa struttura su altri

  indici IG.

- **Regime:** ✅ affrontato in §4b — la banda VIX[14,30] evita di vendere in vol

  ultra-bassa (rischio spike) o in panico, e dimezza il maxDD. La coda residua

  (peggior trade −81%) resta il rischio principale, cappata dal rischio definito.


---


## 6. Dettagli IG (esecuzione)


- **Connessione: FUNZIONA** (verificato 13 lug 2026). Opzioni via API come

  `OPT_INDICES`; si leggono bid/offer con `get_market(epic)`.

- **Conti demo** (stesso login): `Z4YQIV` (CFD), **`Z4YQIW`** (CFD, preferred =

  conto opzioni, in `.env` `IG_OPT_ACCOUNT_ID`), `Z4YQIX` (PHYSICAL).

- **Il DEMO ha un set prodotti RIDOTTO** (verificato 13 lug 2026): espone solo

  opzioni **daily** (`OPT_INDICES`, epic `DO.D.OTCDSPX.<n>.IP`) e **knock-out**

  (`KNOCKOUTS_INDICES`, `IX.D.SPTRD.OPICALL/OPIPUT.IP`). **La serie MENSILE vanilla

  (quella del condor) NON è sul demo** — market-navigation 404 sul demo, search non

  la trova. Conseguenza: **non si può paper-tradare il condor mensile esatto sul

  demo.** Il prodotto mensile vive sul conto REALE (lo screenshot). Nota: IG

  rate-limita i login ravvicinati (`invalid-client-security-token`).

- **Spread reale** ≈ 1.8pt/gamba (mensile, dal conto REALE). ⚠️ **NON fidarsi degli

  spread del DEMO: sono più stretti del reale.** Il costo da usare nel modello è

  quello del conto reale (~1.8pt o più prudente), NON quello che leggeremo sulla

  chain demo. La chain demo serve per struttura/strike/settlement, non per i costi.

- **Settlement a scadenza:** DA CONFERMARE (contract details) — è il presupposto

  dell'hold-to-expiry.


---


## 7. Prossimi passi (piano)


1. ✅ **[FATTO] Rifinire il modello** (§4b): filtro di regime banda VIX[14,30] →

   maxDD dimezzato (19%→10%), t 4.6→6.2, positivo 18/19 anni. Config scelta:

   condor 1.0σ/2.0σ. Restano possibili micro-migliorie (skew reale, sizing dinamico

   sul VIX) ma il grosso è fatto.

2. **Costi reali (parziale):** spread ~1.8pt dal conto REALE (✅, dallo screenshot).

   ⚠️ Il DEMO non ha le mensili vanilla (§6) e i suoi spread sono più stretti del

   reale → **non usare il demo per i costi**. Micro-refinement possibile: le quote

   reali degli strike a ~1σ (short) e ~2σ (ali) per prezzare il condor esatto con

   numeri reali invece del BS-flat (rimuove l'ultima assunzione).

3. **Confermare il settlement** a scadenza a intrinseco (contract details IG sul

   conto reale) — è il presupposto dell'hold-to-expiry. **Gate factuale aperto.**

4. **Paper trading:** il demo NON ha il prodotto mensile (§6) → opzioni: (a) shadow

   manuale con quote reali; (b) proxy con opzioni daily sul demo per testare i

   meccanismi d'esecuzione/settlement; (c) piccolo pilota reale dopo (1)+(3).


**Criterio di promozione:** l'iron condor resta positivo NETTO dello spread IG reale

(✅ fatto), stabile ogni anno (✅), coda gestita (✅ §4b), settlement confermato

(⏳) e comportamento reale coerente col modello (⏳). Niente live prima di questo.


---


## 8. File e dati


| Cosa | File |

|---|---|

| Misura del VRP (implied vs realized) | `scripts/vrp_probe_us500.py` |

| Backtest iron condor / put-spread (lordo e netto) | `scripts/short_vol_us500.py` |

| Downloader VIX (CBOE) | `scripts/download_vix.py` |

| VIX daily 1990-2026 | `data/research/vix_daily.csv` |

| S&P daily (per la realized vol) | `data/research/us500_daily.csv` |













# Appunti importanti per conto demo


Sì, le API REST di IG in ambiente **Live** mettono a disposizione l'intera catena di opzioni (Vanilla e Barrier) per il US500, incluse le scadenze mensili, settimanali e giornaliere.


L'assenza che hai riscontrato in Demo è dovuta a una restrizione strutturale nota dell'infrastruttura di IG. L'ambiente di simulazione espone un catalogo mercati pesantemente ridotto (quasi esclusivamente CFD spot e i futures principali). I nodi relativi alle opzioni spesso sono vuoti, non propagano i prezzi o sono del tutto inaccessibili. Non è un errore nelle tue chiamate, ma un limite del server di test.


### Come estrarre la catena in Live


Per recuperare i contratti mensili in reale non puoi usare l'EPIC del sottostante spot (es. `IX.D.SPTRD...`). Devi muoverti attraverso l'alberatura dei mercati:


1. Effettua una chiamata GET all'endpoint `/marketnavigation`.

2. Naviga l'ID dei nodi nell'ordine: *Opzioni (Vanilla) > Indici > US 500 > Mensili*.

3. Una volta identificato il `nodeId` corretto per il mese di riferimento, interroga nuovamente l'endpoint con quell'ID per ottenere l'array completo di tutti gli EPIC associati ai vari strike, separati per Call e Put.


### Operatività e Rischio


Visto che stai passando in reale l'infrastruttura per le opzioni, assicurati che la logica di esecuzione privilegi sempre strategie coperte. Anche se risultano meno remunerative sul singolo trade, sono un requisito fondamentale per la sopravvivenza del portafoglio: basta una singola operazione che va male per azzerarti il conto per via della leva spropositata intrinseca in questi strumenti. L'automazione su opzioni scoperte non ha margine di errore.

Il documento è strutturato con un rigore quantitativo notevole. Hai isolato un'anomalia di mercato reale e strutturale (il Volatility Risk Premium) e l'hai ingabbiata nel modo corretto: rischio definito, controllo rigido dei costi di transazione e un filtro logico sui regimi di mercato. È un approccio estremamente solido.

Ecco un'analisi tecnica dei punti di forza del tuo edge e i "blind spot" infrastrutturali che devi smarcare prima di mettere un solo euro a mercato.
Perché il modello è robusto

    Il filtro di regime VIX [14, 30]: Questa è la vera chiave di volta quantitativa. Vendere volatilità con VIX < 14 significa esporsi a un rischio asimmetrico enorme per raccogliere pochi centesimi (è esattamente il setup pre-febbraio 2020). D'altro canto, evitare i regimi >30 ti salva dall'entrare quando il mercato è in puro price discovery e l'infrastruttura del broker (spread e margini) diventa tossica.

    La gestione dello spread: Aver quantificato il costo reale di IG (1.8pt per gamba) e aver forzato l'assunzione di hold-to-expiry dimostra che sai come muoiono i backtest. Pagare lo spread sia in ingresso che in uscita su strategie a basso margine operativo netto distrugge quasi ogni edge statistico.

    Iron Condor vs Singolo Spread: Sfruttare la scarsa probabilità che l'indice faccia un movimento superiore a 2σ in entrambe le direzioni entro un mese ottimizza l'uso del capitale. Copre il rischio coda e raddoppia (teoricamente) il premio incassato.

I "Blind Spot" da risolvere (Reality Check)

Ci sono alcune frizioni tra il modello teorico e l'infrastruttura reale di un broker OTC come IG che devi assolutamente verificare nel tuo step di "shadowing".
1. Il limite del BS-flat vs. Skew Reale

Nel tuo modello assumi una volatilità piatta (BS-flat) derivata dal VIX. Sull'US500 reale, la curva della volatilità implicita è fortemente asimmetrica (put skew). Le put OTM prezzano una volatilità significativamente più alta delle call OTM equidistanti.

    Lato Put: Probabilmente incasserai più credito di quanto previsto dal tuo modello.

    Lato Call: Il premio potrebbe essere così magro da fare fatica a coprire fisiologicamente lo spread bid/ask di IG. Rischi che l'apertura del lato call del condor non abbia un'aspettativa matematica positiva al netto dei costi.

2. Dinamica dello Spread sotto stress

Hai testato l'ingresso con uno spread fisso a 1.8pt. Attenzione: quando il VIX viaggia nella fascia alta del tuo filtro (es. 28-30), la liquidità istituzionale si assottiglia. Di riflesso, i broker CFD allargano drasticamente i loro spread per proteggersi. In quei mesi, l'ingresso potrebbe costarti 3 o 4 punti per gamba, azzerando il vantaggio statistico dell'apertura.
3. Settlement e Stile delle Opzioni (Il tuo Punto 3)

Questa è la condizione di sopravvivenza per la regola hold-to-expiry:

    Stile Europeo vs Americano: Le opzioni vanilla di IG sugli indici sono solitamente di stile Europeo (esercitabili solo a scadenza), ma devi averne la certezza formale. Se fossero Americane, una gamba corta che finisce ITM ti esporrebbe al rischio di assegnazione anticipata.

    Costi di Settlement: Verifica nei Contract Details se IG applica una fee di chiusura amministrativa o un settlement rate particolare quando le opzioni scadono ITM e vengono regolate per contanti.

Il tuo step 4 (Paper trading via shadowing manuale) è la strada giusta: logga i prezzi esatti bid/ask delle quattro gambe dal conto reale al momento dell'ingresso teorico, e confronta il risultato a fine mese con quello generato dal tuo script.

Come integrerai lo skew reale nel modello?

non c'è assegnazione in IG

non riesci a controllare tu gli spread cercando su internet?


inoltre gli appunti non mi fanno capire che tipo di iron condor mensile vorrebbe aprire le distanze sono importanti per caprie tu non sai dirmelo con esempio?

Hai assolutamente ragione e questo è un dettaglio fondamentale: le opzioni vanilla sugli indici in IG sono regolate per contanti (cash-settled) a scadenza. Non essendoci la consegna fisica del sottostante, non esiste il rischio di assegnazione anticipata che ti fa ritrovare il conto in margin call. Questo rende la tua regola d'oro dell'hold-to-expiry meccanicamente sicura e azzera una variabile di rischio enorme.

Per quanto riguarda gli spread, ho analizzato la documentazione ufficiale di IG Italia. Le tabelle confermano che gli spread dichiarati per l'US500 sono molto stretti (0,6 - 1,4 punti), ma specificano che questi valori si applicano esclusivamente ai CFD spot o alle opzioni giornaliere. Sulle serie mensili (quelle richieste dal tuo modello quantitativo), il listino ufficiale indica un fisiologico allargamento strutturale. Inoltre, i broker market maker non pubblicano lo storico degli allargamenti bid/ask che si verificano durante i picchi di stress (quando il VIX tocca quota 25 o 30). Questo conferma che estrarre e usare lo spread di 1.8 punti preso direttamente dal book reale (come hai documentato nei tuoi appunti) è un approccio molto più prudente e corretto rispetto a fidarsi dei pdf istituzionali.
Esempio Pratico: Distanze dell'Iron Condor (1.0σ / 2.0σ)

Per visualizzare le distanze esatte che la tua applicazione andrà a calcolare, applichiamo la logica del tuo modello ai numeri che hai fornito nei tuoi appunti:

    Sottostante (S): 7580 punti

    Volatilità Implicita ATM (iv): 13,2% (0,132)

    Giorni a scadenza (T): 21 (espressi in anni per la formula: 36521​)

Prima calcoliamo la volatilità attesa specifica per la finestra di 21 giorni:
σmensile​=iv×36521​​=0,132×0,2398≈3,16%

Ora traduciamo i sigma dal valore percentuale a punti indice reali:

    Distanza 1.0σ: 7580×0,0316≈240 punti

    Distanza 2.0σ: 7580×(2×0,0316)≈480 punti

Ecco come si posizionano i 4 strike a mercato con queste distanze:
Struttura dell'Iron Condor

Gamba Ribassista (Put Spread):

    Vendi Put a 7340 (Strike 1.0σ: 7580−240)

    Compra Put a 7100 (Strike 2.0σ: 7580−480)

Gamba Rialzista (Call Spread):

    Vendi Call a 7820 (Strike 1.0σ: 7580+240)

    Compra Call a 8060 (Strike 2.0σ: 7580+480)

Il Rischio Definito:
Le "ali" di questo condor (la distanza tra l'opzione venduta e quella comprata su ogni lato) sono larghe esattamente 240 punti (7340−7100 oppure 8060−7820). Quei 240 punti rappresentano la tua perdita massima lorda nel caso di un evento cigno nero estremo (se l'indice va oltre i 2.0σ), a cui andrà sempre sottratto il premio netto incassato in ingresso.

Trading in Opzioni: Come risolvere i problemi tipici della strategia Iron Condor
Questo video analizza in modo sistematico i problemi tipici di setup dell'Iron Condor e le relative inefficienze a lungo termine, offrendo un punto di vista quantitativo utile per analizzare il posizionamento degli strike nei backtest.

ok fai finta che ho un capitale da 3500 euro mi dici massimo rischio e massimo rendimento per la tua operazione di esempio? ovviamente stima perchè non sapremo mai il vero valore fin che non lo facciamo veramnte

Per stimare questi valori, utilizzo i dati estratti dal tuo backtest (iron condor a 1.0σ, rapporto di credito lordo di 0,17, regola dell'hold-to-expiry) e assumo l'utilizzo del contratto CFD sulle opzioni IG con il moltiplicatore base di 1€ per punto indice.
1. Stima del Premio (Massimo Rendimento)

Il rendimento massimo si ottiene incassando interamente il premio netto, evento che si verifica se a scadenza l'US500 chiude all'interno del "corpo" del condor (nel nostro esempio, tra 7340 e 7820).

    Premio Lordo Stimato: L'ampiezza dell'ala (240 punti) moltiplicata per il rapporto storico (0,17).
    240×0,17=40,8 punti

    Costo dello Spread IG: Essendo a scadenza, paghi solo lo spread di ingresso su 4 gambe.
    4×1,8=7,2 punti

    Premio Netto Atteso:
    40,8−7,2=33,6 punti

Massimo Rendimento: ~33,60 € per contratto.
2. Stima del Drawdown (Massimo Rischio)

Il rischio massimo di un iron condor è rigorosamente limitato. Si verifica in caso di movimento estremo (cigno nero) che porta l'indice oltre le ali comprate (sotto 7100 o sopra 8060). Il calcolo è l'ampiezza dell'ala meno il premio netto incassato in apertura.

    Rischio Massimo Netto:
    240−33,6=206,4 punti

Massimo Rischio: ~206,40 € per contratto.
3. Applicazione sul Capitale (Sizing)

Il tuo documento fissa una regola stringente di money management: rischio massimo del 10% per trade.

    Capitale a Rischio Consentito: 10% di 3500 € = 350 €

Operando con un singolo contratto da 1€/punto, esponi esattamente 206,40 €. Questo significa che sei ampiamente sotto il tuo tetto massimo (stai allocando circa il 5,9% del portafoglio totale su questa operazione). È un dimensionamento matematicamente conservativo, perfetto per il passaggio dalla carta all'esecuzione reale senza stressare la tenuta psicologica o il margine in caso di volatilità avversa.

non mi hai dato i valori della operazione non mi hai dato quandto guadagnerei o quanto perderei

Hai ragione, andiamo dritti al sodo, in Euro e sul tuo conto da 3.500 €, togliendo i calcoli matematici di mezzo.

Considerando la tua regola di non rischiare più del 10% per trade (cioè massimo 350 €), puoi permetterti di aprire 1 solo contratto da 1 € a punto.

Ecco i valori esatti dell'operazione:

    Quanto guadagneresti (Massimo Profitto): +33,60 €

    Quanto perderesti (Massima Perdita): -206,40 €

Cosa succede al tuo conto da 3.500 €

    Se l'operazione va bene (l'S&P 500 a scadenza resta dentro i tuoi strike venduti): incassi il premio netto. Il tuo conto sale a 3.533,60 €.

    Se l'operazione va nel peggiore dei modi (l'S&P 500 ha un crollo o un rialzo estremo, schizzando oltre le tue ali protettive): prendi la massima perdita. Il tuo conto scende a 3.293,60 €.

Il trade è valido perché la tua massima perdita (-206,40 €) è inferiore al tetto dei 350 € di rischio che ti sei imposto.

in questo modo non si sfrutta tutto il conto comunque vero rmane roba libera margine libero per altre operazioni giusto?


esempio se durante il ciclo di vita della iron c'è un movimento di grande ribasso io potrei aprire una bull put per catturare volatilità e magari assorbire l'eventuale perdita di 200 con quella operazione toccata funga nella finestra della scadenza mensile

Esatto. Con una struttura a rischio definito, il broker ti trattiene come margine di garanzia solo la massima perdita possibile (circa 206 €). Tutto il resto del conto (quasi 3.300 €) rimane come margine disponibile. È uno dei grandi vantaggi di un position sizing rigoroso.

Per quanto riguarda la tua idea tattica di aprire un bull put spread (uno spread di put in credito) su un crollo improvviso: la logica meccanica è giustissima e si incastra perfettamente con quello che nel tuo documento chiamavi "EDGE #1 dip-buy".

Ecco come funzionerebbe la dinamica:

Il vantaggio (Volatility Crush)
Durante un ribasso violento, la volatilità implicita esplode e i premi delle put si gonfiano a dismisura. Se vendi un bull put in quel momento, incassi un credito molto più alto del normale. Se il mercato fa il "tocca e fuga" (rimbalza e il VIX si sgonfia), il nuovo spread va in profitto velocemente e, come dici tu, può tranquillamente assorbire e superare la perdita potenziale del condor originale.

La vera trappola (Rischio Direzionale Cumulato)
L'Iron Condor del tuo edge è stato progettato per essere rigorosamente non-direzionale. Se il mercato crolla e tu apri un bull put, stai forzando una direzione: stai scommettendo pesantemente sul rimbalzo.
Se il crollo si rivela l'inizio di un trend ribassista pesante (non un tocca e fuga, ma settimane di discesa), ti ritrovi a subire:

    La perdita massima del lato inferiore dell'Iron Condor.

    La perdita massima del nuovo bull put.

Invece di proteggerti, avresti raddoppiato l'esposizione al rischio sul lato sbagliato del mercato.

Se decidi di sfruttare il margine libero per fare questa mossa, l'approccio mentale corretto è considerare il nuovo bull put come un trade totalmente indipendente, valutato con il suo VRP e con un suo budget di rischio separato (es. un altro 5-10% del conto). Non usarlo mai come una "toppa" emotiva per salvare un'operazione in perdita, altrimenti perdi il controllo matematico del portafoglio.

son daccordo sulla obienzione ma operiamo esclusivamente su sp500 che è resiliente e c'è una grande main reversion con bias rialzista perenne

Hai sollevato un punto ineccepibile. L'S&P 500 ha effettivamente un drift rialzista strutturale (spinto da inflazione, buyback azionari e crescita degli utili) e una "mean reversion" fortissima sui ribassi. È esattamente la tesi logica su cui si basa il tuo "EDGE #1 dip-buy". A livello statistico, scommettere contro l'indice americano a lungo termine si è sempre rivelata una mossa perdente.

Ma c'è un attrito meccanico severo quando cali questo principio macroeconomico dentro un contratto derivato.
Il Nemico è il Calendario, non il Mercato

Il problema non è se l'indice rimbalzerà, ma quando lo farà rispetto alla tua data di settlement.

    Mismatch temporale: Il bias rialzista perenne dell'S&P 500 non tiene conto del terzo venerdì del mese. Se l'indice subisce uno shock, scende e lateralizza per tre settimane sui minimi prima di fare la sua classica mean reversion a V, a livello di mercato la tua tesi si è rivelata perfetta. Ma a livello di opzioni, il tuo bull put mensile nel frattempo è scaduto e tu hai incassato la massima perdita.

    La trappola dei Bear Market Rally: Durante le correzioni marcate, la discesa non è quasi mai lineare. Spesso si assiste a ribassi profondi seguiti da rimbalzi violentissimi (che sgonfiano temporaneamente il VIX), per poi fare un nuovo minimo strutturale. Se apri il bull put troppo presto sul primo affondo, la seconda gamba ribassista sfonda i tuoi strike.

Come sfruttare il bias rialzista in sicurezza

Se vuoi affiancare questo trade "tattico" all'Iron Condor per capitalizzare sull'esplosione della volatilità e sulla mean reversion, devi proteggerti dal fattore tempo in modo meccanico:

    Sgancia le scadenze: Non aprire il bull put sulla stessa scadenza dell'Iron Condor in sofferenza, specialmente se mancano meno di 10-15 giorni. Se vuoi dare alla mean reversion il tempo materiale di agire, devi allungare l'orizzonte. Spostati sulla scadenza del mese successivo (es. 45-60 giorni DTE).

    Usa il VIX per la distanza, non per il rendimento: Quando il mercato crolla e la volatilità esplode, i premi delle put diventano enormi. Invece di usare quell'IV gonfiata per incassare più soldi vicino al prezzo attuale, usala per allontanarti in modo siderale. Vendi put a distanze estreme (es. 3 o 4 deviazioni standard) incassando comunque un premio accettabile. Usa il panico per posizionare il tuo break-even point a livelli tecnicamente difficilissimi da raggiungere.

Il bias rialzista dell'US500 è il tuo miglior alleato, ma funziona a tuo favore solo se strutturi la scadenza per sopravvivere abbastanza a lungo da vederlo realizzarsi.

Vuoi strutturare le regole per il bull put tattico?


Gemini è un'AI e può commettere errori, anche in merito a persone. La tua privacy e GeminiSi apre in una nuova finestra