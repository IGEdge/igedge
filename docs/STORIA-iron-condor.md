# EDGE #2 (candidato) — Short-Vol su US500: Volatility Risk Premium con iron condor

Primo edge **non-direzionale** del progetto e primo candidato che **supera il gate
costi** dopo 8 falsificazioni sul prezzo intraday. Vende volatilità implicita
(sistematicamente > realizzata) con una struttura a **rischio definito** (iron
condor mensile), tenuta **a scadenza**. Complemento scorrelato all'[EDGE #1
dip-buy](EDGE-1-compra-il-dip.md).

> **Documento vivo** — si aggiorna a ogni test. Stato in cima, dettagli sotto.

> **➡️ L'EDGE SOPRAVVISSUTO È IL PUT-SPREAD FAR-OTM — vedi [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md).**
> Togliendo il lato call (a sconto, la causa di morte del condor) resta il solo lato
> put (skew ricco) = edge reale ma modesto. Questo documento resta come **storia +
> lezione** del condor. L'infrastruttura live (§6/§9) è riusata dal put-spread.

**❌ STATO (14 lug 2026) — EDGE FALSIFICATO su IG (pricing reale).** Il primo
backtest prezzava tutte le gambe a un **VIX piatto** (17.7), sovrastimando il
credito **~2.3×**. Rifatto il backtest con lo **SMILE REALE** misurato sui prezzi
IG (put OTM care ~VIX+, **call OTM quasi regalate ~11% IV**, ATM 0.77×VIX),
spread reali, mosse reali (`short_vol_us500.py --real-smile`): **credito medio
8.7pt** (non 20), **lato call NETTO NEGATIVO** (−1.4pt, non copre lo spread),
**WR 84% ma ret/trade −0.5%, t −0.4, CAGR −0.5%/yr → NESSUN EDGE.** I +6.3% erano
un **artefatto del pricing a VIX piatto**. Come l'intraday CFD: fenomeno (VRP)
reale, ma il pricing IG non lascia margine (la struttura si rompe abbastanza da
mangiare un premio troppo magro). **NON tradeable.** L'INFRASTRUTTURA live
(sessione, esecuzione, catena, scadenze regolari) resta valida e riusabile per
altri edge.

**STATO precedente (13 lug 2026, ora superato dal punto sopra):** gate a modello + gate costi IG **superati**; **rifinitura
coda/strike fatta** (§4b: filtro di regime VIX → maxDD dimezzato). Config
raccomandata: **iron condor 1.0σ/2.0σ, banda VIX[14,30], hold-to-expiry, 10%
rischio/trade** → netto spread IG: **t=+6.2, CAGR +6.8%/yr, maxDD 10%, positivo 18
anni su 19**. ✅ **Settlement confermato** (cash a intrinseco) e ✅ **spread reale
≤ assunto** (ali ~0.5pt → il modello a 1.8-flat è conservativo). **Manca solo:**
prezzare il condor esatto con le quote reali AUG (allowance permettendo) e definire
l'operatività (fetcher economico / streaming). Vicini al tradeable; ancora niente
live prima del test operativo.

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

## 4c. Skew reale + convenzione temporale (13 lug 2026)

Due raffinamenti per avvicinare il modello alla realtà (`short_vol_us500.py`):
- **Tempo a scadenza in giorni di CALENDARIO** (`T = giorni_reali/365`). Verifica:
  **non cambia i risultati** (t 6.1 vs 6.2) → il modello a `21/252` era già corretto
  (21 gg di trading ≈ 30 di calendario). I "240pt" di stime a `21/365` erano un
  understatement. Gli strike 1σ/2σ del modello sono giusti (~289/577pt a S=7580).
- **Put skew** (`--skew`, vol pt per σ): sull'SPX le put OTM prezzano IV più alta,
  le call OTM più bassa. Effetto (skew realistico 2pt/σ, netto spread + banda VIX):

| | credito PUT netto | credito CALL netto | t | CAGR | maxDD |
|---|---|---|---|---|---|
| flat (skew 0) | +7.9pt | +9.2pt | +6.1 | +6.7% | 9% |
| **skew 2pt/σ** | **+9.9pt** | **+6.6pt** | +5.7 | +6.3% | 9% |
| skew 3pt/σ | +10.5pt | +5.1pt | +5.2 | +5.6% | 10% |

Lo skew sposta credito dal lato call al lato put (Gemini aveva ragione nella
direzione), **ma il lato call copre ancora lo spread e resta positivo**; l'edge
totale tiene (**t~5.7, CAGR ~6.3% netto spread E skew**). Il **put side è il
motore**, il **call side è il punto debole** → spunto futuro: **condor asimmetrico**
(call più lontane / ala più larga sul call). Da confermare con lo skew reale in
shadowing.

---

## 4d. Copertura bull-put sui dip — TESTATA, NON è una copertura (13 lug 2026)

Idea (docs/STORIA-copertura-put-sui-dip.md): durante un ribasso, vendere un **bull put
spread** sul segnale dip-buy validato (RSI2<10, close>SMA200) per sfruttare l'IV
gonfiata + la mean-reversion, e "assorbire" la perdita del put side del condor.
Backtestata in `scripts/bull_put_dip_us500.py` (BS+VIX+skew, hold-to-expiry).

**Verdetto: NON funziona come copertura — è STRUTTURALMENTE correlata al condor.**
Un bull put è esposizione short-put = lo stesso rischio del lato put del condor.

| Config | edge standalone | 2020 / 2011 (crash) |
|---|---|---|
| 1.0σ, 10gg (vicino) | +2.4% CAGR, WR 95%, batte il nulla | **−62% / −70%** (perde col condor) |
| 2.0σ, 10gg (lontano) | −1.4% CAGR (spread mangia premio) | −89% / −111% |
| 2.0σ, 21gg (lontano+lungo) | ~0% (non batte il nulla) | coda ok ma nessun edge |

Dilemma insanabile: put **vicine** = edge reale ma **perde nei crash col condor**
(raddoppia, non copre); put **lontane** = coda ok ma premio troppo sottile → lo
spread azzera l'edge. La tesi "l'S&P rimbalza" è vera al 95%, ma quel 5% coincide
con la coda del condor → **concentra il rischio, non lo diversifica**.

**La copertura VERA del condor sembrava l'opposto** (long-vol/long-put) → testata
in §4e: **anche quella è controproducente.**

---

## 4e. Tail-hedge long-vol TESTATO — controproducente (13 lug 2026)

Overlay: comprare una put lontana (2.5-3σ, oltre l'ala) su ogni condor
(`--tail-hedge`). Atteso: paga nei crash, attenua la coda. **Risultato: NO.**

| | CAGR | maxDD | peggior trade | 2020 (COVID) |
|---|---|---|---|---|
| condor da solo | +6.3% | 9% | −86% | +15% |
| + hedge 3σ×1 | +5.2% | 10% | −88% | +14% |
| + hedge 2.5σ×2 | +3.3% | 11% | −91% | +13% |

L'hedge **peggiora ogni metrica e ogni anno-crash** (2020 incluso). Non ha aiutato
da nessuna parte, ha solo bruciato premio. Ragioni strutturali:
1. **Il condor è già a rischio definito** → nessuna coda illimitata da coprire.
2. **Comprare put = SHORT sul VRP** (il premio che il condor incassa) → restituisci l'edge.
3. **L'hedge in unità-σ si allontana quando la vol esplode** → quasi mai raggiunto,
   proprio nei crash (VIX sale → σ si allarga → 3σ va lontanissimo in valore assoluto).
4. **Il drawdown viene da perdite MODERATE clusterizzate** (1.5-2σ), non da crash
   profondi → non raggiungono un hedge lontano.

**Conclusione: NON si hedgia una strategia VRP comprando vol.** La coda si gestisce
con ciò che c'è già: **rischio definito + filtro VIX[14,30] + sizing** (10%/trade →
mese peggiore −8% equity; ridurre la size per più margine). Capitolo coda CHIUSO.

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
- **Il DEMO ha un set prodotti RIDOTTO** (verificato 13 lug 2026): solo opzioni
  **daily** (`OPT_INDICES`, `DO.D.OTCDSPX.*`) e **knock-out**. Le mensili vanilla
  NON ci sono → niente paper trading del condor esatto sul demo.
- **Sul conto REALE (`TVYYM`, host `api.ig.com`) c'è tutto** (verificato 13 lug
  2026, solo lettura). 148 opzioni US500. Schemi epic: settimanali
  `OP.D.OTCSPXMON.<strike><C/P>.IP` (es. 6920C), mensili `OP.D.OTCSPXEMO.*` (es.
  31-AUG), altre scadenze `OP.D.OTCSPX2/3/4/5.*`. Valuta USD, lotSize 1.0,
  valueOfOnePip 1.00.
- ✅ **SETTLEMENT CONFERMATO (cash a intrinseco):** contract details IG →
  *"Settled basis the cash close of SPX ..."*. Cash-settled sul close S&P →
  **l'hold-to-expiry è valido** (nessuno spread in uscita). Chiude il gate §7.3.
- ✅ **SPREAD REALE per moneyness:** **0.5pt (far OTM / ali del condor) → 1.2pt
  (ITM)**, ATM ~1.8pt. Le ali (2σ) costano ~0.5pt, non 1.8 → **il modello a
  1.8pt-flat SOVRASTIMA i costi**; l'edge reale è probabilmente MIGLIORE. (Costo
  condor più realistico ≈ 2 short a ~1.5-1.8 + 2 ali a ~0.5 ⇒ ~2.5-2.6pt d'ingresso
  vs i 3.6 assunti.)
- ⚠️ **Allowance API live strettissima:** ~20 `get_market` la esauriscono
  (`exceeded-api-key-allowance`). Per fetch/esecuzione servono query mirate
  (`--strike-list`) con pause, o lo **streaming Lightstreamer**. Il demo invece
  rate-limita i login (`invalid-client-security-token`).
- **Spread reale** ≈ 1.8pt/gamba (mensile, dal conto REALE). ⚠️ **NON fidarsi degli
  spread del DEMO: sono più stretti del reale.** Il costo da usare nel modello è
  quello del conto reale (~1.8pt o più prudente), NON quello che leggeremo sulla
  chain demo. La chain demo serve per struttura/strike/settlement, non per i costi.
- **Settlement a scadenza:** DA CONFERMARE (contract details) — è il presupposto
  dell'hold-to-expiry.

---

## 7. Prossimi passi (piano)

> ### ✅ RISOLTO — scadenze mensili REGOLARI (3° venerdì) (14 lug 2026)
> Requisito: usare SOLO le mensili **standard (3° venerdì)**, MAI le fine-mese (EMO).
> **Le mensili regolari ESISTONO ogni mese** (17 lug, 21 ago, 18 set…): la SEARCH IG
> le nascondeva (tronca), non è che mancassero. Codici: `OTCSPX1`=AUG-26, `4`=JUL,
> `3`=SEP, `5`=DEC, `2`=MAR; `OTCSPXEMO`="US 500 (End of Month)" = l'EMO da evitare.
> **Soluzione (niente search):** `_pick_expiry` **calcola** il 3° venerdì target più
> vicino a ~30gg (`monitor.upcoming_standard_expiries`); `_discover_code` trova il
> codice interrogando `get_market` (che restituisce la `expiry`); si costruiscono
> gli epic (`OP.D.<code>.<strike><P/C>.IP`). **Verificato live:** prende AUG-26
> (21 ago, 38gg, `OP.D.OTCSPX1.*`), condor reale credito 35pt/maxloss 265pt, 8
> chiamate, sessione riusata. VIX 13.7 → in produzione salta (sotto banda, giusto).

1. ✅ **[FATTO] Rifinire il modello** (§4b): filtro di regime banda VIX[14,30] →
   maxDD dimezzato (19%→10%), t 4.6→6.2, positivo 18/19 anni. Config scelta:
   condor 1.0σ/2.0σ. Restano possibili micro-migliorie (skew reale, sizing dinamico
   sul VIX) ma il grosso è fatto.
2. **Costi reali (parziale):** spread ~1.8pt dal conto REALE (✅, dallo screenshot).
   ⚠️ Il DEMO non ha le mensili vanilla (§6) e i suoi spread sono più stretti del
   reale → **non usare il demo per i costi**. Micro-refinement possibile: le quote
   reali degli strike a ~1σ (short) e ~2σ (ali) per prezzare il condor esatto con
   numeri reali invece del BS-flat (rimuove l'ultima assunzione).
3. ✅ **[FATTO] Settlement confermato:** cash-settled a intrinseco sul close S&P
   ("Settled basis the cash close of SPX") → hold-to-expiry valido (§6).
4. **Paper trading:** il demo NON ha il prodotto mensile (§6) → opzioni: (a) shadow
   manuale con quote reali; (b) proxy con opzioni daily sul demo per testare i
   meccanismi d'esecuzione/settlement; (c) piccolo pilota reale dopo (1)+(3).

**Criterio di promozione:** l'iron condor resta positivo NETTO dello spread IG reale
(✅ fatto), stabile ogni anno (✅), coda gestita (✅ §4b), settlement confermato
(⏳) e comportamento reale coerente col modello (⏳). Niente live prima di questo.

---

## 9. Esecuzione live — infrastruttura (13 lug 2026)

**Decisione:** niente shadow paper trading; si va **live con poco capitale (~€1000)**
per collaudare i meccanismi. ⚠️ **Sizing:** su €1000 un condor (max loss ~€200)
rischia **~20%/trade** = il DOPPIO del sizing testato (10%). Va bene per *testare la
meccanica*, NON è il profilo di rischio validato — per quello servono ~€2000+/contratto.

**Regola d'oro (mai short nudo) SENZA sprecare spread:** `src/options/executor.py`.
Chiave = **ordine longs-first**: aprendo prima le 2 ali di protezione, ogni stato
intermedio è a rischio definito → si può **RITENTARE** la gamba mancante invece di
disfare tutto (che ripagherebbe lo spread inutilmente).
- **Preflight:** le 4 gambe TRADEABLE con quote sane, altrimenti non si apre nulla.
- **Longs-first + RITENTO:** si aprono prima le 2 LONG poi le 2 SHORT; su ogni
  gamba si **insiste** (retry con backoff) invece di arrendersi al primo errore IG.
- **Guardia anti-doppione:** dopo un'apertura fallita/ambigua si controlla
  `get_positions`; se la gamba è in realtà aperta (conferma persa) la si **adotta**,
  niente doppio ordine.
- **Fallimento persistente → HOLD (default):** il parziale è a rischio definito
  (longs-first) → **NON si disfa**; si tiene (`INCOMPLETE_HELD`) + **allarme
  CRITICO** all'operatore (completare/decidere). Regola invalicabile: se manca
  un'ALA, NON si apre il suo short. Policy `unwind` disponibile ma non default.
- **Difesa:** se mai risultasse uno short nudo → unwind forzato immediato.
- **Chiusura:** shorts-first, con retry (flattare è prioritario).
- **Log rotativo minuzioso:** `logs/condor.log` (umano) + `logs/condor_audit.jsonl`.
- **Collaudato in dry-run** (`scripts/test_condor_executor.py`, 6 scenari: happy,
  retry-riesce, hold-persistente, adozione-ambigua, unwind-policy, preflight-KO).

**Stato infrastruttura (tutto dry-run, nessun ordine reale):**
- ✅ **executor sicuro** (`executor.py`) — apertura ritento+hold, mai short nudo.
- ✅ **audit log rotativo** (`audit_log.py`) — umano + JSONL.
- ✅ **store SQLite** (`store.py`) — condor + 4 gambe persistenti (`data/condors.db`).
- ✅ **monitor** (`monitor.py` + `scripts/monitor_condors.py`) — mark-to-market,
  DTE, distanza dagli short, P&L non realizzato, reconcile con IG (allarme gambe
  mancanti/orfani). Collaudi: `scripts/test_condor_executor.py`, `test_condor_monitor.py`.
- ✅ **anti rate-limit** (`throttle.py`) — intervallo minimo tra chiamate IG
  (proattivo, non si arriva mai al limite). Wrappa il client.
- ✅ **risoluzione catena frugale** (`chain_resolver.py`) — 4 epic dagli strike
  (1σ/2σ) con poche search + parsing strike dagli epic; **niente get_market per
  esplorare** (era ciò che bruciava l'allowance). Cache per scadenza.
- ✅ **orchestratore** (`orchestrator.py` + `scripts/run_condor.py`) — gate VIX[14,30]
  → scadenza (DTE 20-45) → strike → catena → quote reali → **credito NETTO e max
  perdita reali** → sizing (gate rischio) → **DEFAULT plan-only** (calcola e mostra
  il condor, NON apre). `--arm --i-understand-live-risk` per aprire davvero.
  Collaudo dry-run: `scripts/test_orchestrator.py` (gate segnale, catena, sizing,
  plan-only, armato, max-posizioni).
- ✅ **volatilità AUTONOMA** — il bot ricava l'**IV ATM dalla catena** ogni ciclo
  (opzione ATM → mid → inversione Black-Scholes), auto-consistente con le opzioni
  che tradia; nessun VIX da passare a mano (override `--vix` solo per test). La
  banda VIX[14,30] usa questa IV (≈ VIX = IV ATM 30gg). Alternativa non usata: epic
  VIX di IG (basato su futures VIX, meno preciso).
- ✅ **sessione PERSISTENTE** (`session.py` `PersistentIGSession`) — login UNA volta,
  token salvati (`data/ig_session_{live,demo}.json`, git-ignorati) e riusati per
  discovery + apertura + monitoraggio e tra riavvii; nuovo login SOLO se scaduti.
  **Risolve il lockout `invalid-client-security-token` da login ravvicinati** — a
  regime non può capitare (test: 5 run = 0 login). `run_condor.py`/`monitor_condors.py`
  NON fanno più logout (tengono viva la sessione). Test: `scripts/test_session.py`.
- ✅ **catena live risolta per COSTRUZIONE DIRETTA** (`chain_resolver.py`
  `resolve_condor_epics_direct`): la `search` IG tronca la mensile e la
  market-navigation dà 404 → si **costruiscono** i 4 epic dagli strike target
  (`OP.D.<code>.<strike><P|C>.IP`, strike ogni 50) e si **verificano** con
  get_market (nudge ±50 se serve). Spot via parità dal weekly (griglia piena);
  IV dall'ATM mensile costruito. Bypassa entrambi i limiti IG.
- ✅ **PIPELINE LIVE FUNZIONANTE END-TO-END (13 lug 2026)** — `run_condor.py --live`
  plan-only sul conto reale (`TVYYM`): sessione **riusata** (0 login), spot 7540,
  VIX≈12.3 → oggi SALTA (sotto banda, corretto); con banda abbassata produce il
  condor reale (31-AGO, short 7200P/7900C, ali 6850/8200, **credito 51.7pt, max
  perdita 298pt**, ~14 chiamate throttlate). Strike/quote/credito TUTTI reali.
- ⏳ **poi:** completamento `INCOMPLETE_HELD`; loop schedulato mensile + monitor
  automatico; (C) condor asimmetrico. La size su €1000 resta aggressiva (~30%/trade).
**Nessun ordine live finché l'utente non autorizza esplicitamente (`--arm`).**
Il `run_condor.py --live` in **plan-only** dà anche il PREZZO REALE del condor AUG.

---

## 10. ⚠️ Il GATE decisivo: IG prezza sotto la VIX (14 lug 2026)

Il backtest (§3-4) prezza le opzioni con BS a **σ=VIX**. Ma **le opzioni US500 di
IG quotano a un'IV più bassa della VIX**:
- Misura live (14 lug, VIX CBOE 17.73): forward ~7550, put ATM 7550 mid ~133.5 →
  **IV ATM = 13.7%** → fattore IV-IG/VIX ≈ **0.77**.
- Perché: la VIX è un indice variance-swap **gonfiato dallo skew/convessità** (sta
  ~1-3 pt sopra l'IV ATM), + possibile **markdown OTC di IG**.

**Rivalidazione col pricing reale** (`--iv-factor` scala placement+pricing; banda
resta su VIX). Config raccomandata, netto spread 1.8pt + skew:

| fattore IV-IG/VIX | ret/trade | t | CAGR | verdetto |
|---|---|---|---|---|
| 1.00 (=VIX, backtest) | +7.4% | +5.7 | +6.3% | artefatto |
| 0.90 (−1.5pt) | +3.6% | +2.1 | — | ok |
| 0.85 (−2.5pt) | +1.1% | +0.6 | — | **break-even** |
| 0.80 (−3.5pt) | −1.8% | −0.9 | — | negativo |
| **0.77 (OGGI)** | **−1.8%** | **−0.9** | **−3.5%** | **NEGATIVO** |

**Conclusione:** l'edge (+6.3%) è un **artefatto del prezzare a VIX**; al livello
reale IG di oggi è **negativo**. Sopravvive solo se IG prezza **entro ~2.5 pt dalla
VIX** (fattore ≥0.85).

**Verdetto (backtest con SMILE REALE, `--real-smile`):** smile calibrato sui prezzi
IG del 14 lug (put 1σ 19.2%, put 2σ 24.4%, ATM 13.7%, **call 1σ 10.9%**, call 2σ
12.9% — cioè rapporti IV/VIX 1.08/1.37/0.77/**0.61**/0.72). Con questo:
**credito medio 8.7pt, lato CALL netto −1.4pt** (le call OTM rendono meno dello
spread), **WR 84%, ret/trade −0.5%, t −0.4, CAGR −0.5%/yr → NESSUN EDGE.**
❌ **EDGE #2 FALSIFICATO su IG.** Il +6.3% del primo backtest era un **artefatto
del VIX piatto** (credito gonfiato ~2.3×). Come l'intraday CFD: il VRP è reale nel
mercato ma sulle opzioni US500 di IG il premio incassabile è troppo magro (specie
il lato call) per battere le rotture. Confermato da misura DIRETTA dei prezzi reali,
non solo dal modello.

**Lezione trasversale:** un backtest di opzioni che prezza a VIX piatto è
inaffidabile — servono lo **smile reale** (put care/call a sconto) e gli **spread
reali per gamba**. La VIX (variance-swap) sovrastima il premio ATM/call incassabile.

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