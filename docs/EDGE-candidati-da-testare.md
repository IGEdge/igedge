# PIPELINE EDGE — candidati DA BACKTESTARE (14 lug 2026)

> **⬜ TUTTO questo documento è DA FARE: nessun candidato è stato ancora
> backtestato — qui non ci sono risultati, solo prior e specifiche.**
> Quando un candidato viene testato: se regge → doc dedicato `EDGE_<NOME>.md`
> tra i validati; se fallisce → riga in
> [EDGE-falsificati.md](EDGE-falsificati.md). In entrambi i casi si aggiorna
> lo STATO qui e l'indice [INDICE-EDGE.md](INDICE-EDGE.md).

Candidati **nuovi** selezionati per massimizzare `prior di letteratura × fit coi
costi IG × dati disponibili × frequenza (compounding)`. Ogni candidato ha qui la
spec completa: tesi/meccanismo, perché il prior è alto, regole ESATTE, dati,
apparato di validazione e **criterio di kill** (pre-registrato: se fallisce, si
archivia, niente varianti di salvataggio → INDICE-EDGE.md "come testare").

**Filtri di selezione applicati** (dalle lezioni, `igedge-validation-apparatus`):
1. niente intraday US500 (segnale/costo sfavorevole — 8 falsificazioni);
2. niente stop stretti su MR, niente hold lunghi con financing CFD;
3. opzioni SOLO con smile reale (lezione #3);
4. sopravvive: pochi trade + hold corti, segnale grande, o costi strutturalmente
   assenti (opzioni hold-to-expiry, forward senza financing).
5. **⚠️ VINCOLO CAPITALE (14 lug 2026, PRIORITARIO): dev'essere tradabile con
   €1.000-3.000 a rischio sano per trade.** Il contratto minimo CFD US500 =
   ~€7.5k di nozionale → **C3, C4 e (probabilmente) C6 sono CAPITAL-GATED:
   spec valide ma NON si lavorano finché il capitale non sale** (~€2.5k+ per un
   contratto CFD ≈ 3x). Anche C1 (validato) è capital-gated. **Il focus operativo
   attuale è il programma OPZIONI: put-spread (EDGE #2, ali strette per capitale
   piccolo) + C5 (timing) + C2 (regime).**

---

## Classifica (ordine di test raccomandato)

| # | Edge | Prior | Dati | Effort | Perché qui |
|---|---|---|---|---|---|
| C1 | MR Ensemble daily US500 (+lato short) | ⭐⭐⭐ | ✅ in casa | basso | estende l'edge #1 GIÀ validato → più trade/anno subito |
| C2 | Term structure VIX (VIX3M) come regime | ⭐⭐⭐ | download 5 min | basso | migliora 2 edge esistenti a costo zero |
| C3 | Dip-buy trasferito su US100/DAX/FTSE/JP225 | ⭐⭐⭐ | download daily | basso | famiglia validata, diversificazione, +frequenza |
| C4 | Pre-FOMC drift | ⭐⭐ | date FOMC | minimo | segnale storico enorme, hold 24h, test in 1 ora |
| C5 | Timing put-spread post-panico | ⭐⭐ | ✅ in casa | minimo | variante dello script esistente |
| C6 | TSMOM multi-asset su forward IG | ⭐⭐⭐⭐ | pipeline nuova | ALTO | il fenomeno più documentato in assoluto; la vera diversificazione |
| C7 | FX carry — gate di misura | ⭐ | log 2 settimane | quasi zero | misurare prima di backtestare |

Quick-win prima (C1-C5, giorni), progetto grande dopo (C6, settimane).

---

## C1 — MR Ensemble daily US500 (più trigger della famiglia validata + lato short)

**STATO: ✅ BACKTEST SUPERATO (14 lug 2026) — ADOTTATO come estensione dell'edge #1.**
Tutti i trigger battono il 100% del nulla sui giorni esclusivi; unione t1-t5 =
342 trade (~20/anno), CAGR +8.8%@1x (da +6.2%) a parità di maxDD (10%), regge
IS/OOS e plateau; t6 short = +0.96%/trade, paga nei bear (2020 +10%, 2022 +9%).
**Risultati completi: [EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md) §5b.**
La spec sotto resta come riferimento di cosa è stato testato.

**Tesi.** L'edge #1 (RSI2<10 & >SMA200) è validato ma raro (~10-15 trade/anno).
L'anomalia sottostante — mean-reversion di breve sugli indici azionari, regime
post-~1998 — è più larga del singolo trigger: la letteratura (Connors et al.)
documenta più segnali della STESSA famiglia. Più trigger indipendenti = più
occorrenze = **compounding**, senza cambiare natura del rischio (già noto).

**Perché il prior è alto.** Non è un edge nuovo: è lo STESSO fenomeno già
validato su questo stesso mercato con questi stessi costi. Il rischio è solo che
i trigger extra si sovrappongano a RSI2 (nessun trade nuovo) o peschino giorni
più deboli.

**Trigger da testare** (soglie standard di letteratura, NON ottimizzate):
- T1 (baseline validato): `RSI(2) < 10 AND close > SMA200`
- T2: **3+ chiusure consecutive in ribasso** AND `close > SMA200`
- T3: **%b Bollinger(20,2) < 0.05** AND `close > SMA200`
- T4: **VIX stretch**: `VIX > 1.05 × MA10(VIX)` AND `SPX > SMA200` (panico di
  vol senza aspettare il prezzo)
- T5: **RSI(2) cumulato**: `RSI2(oggi)+RSI2(ieri) < 35` AND `close > SMA200`
- T6 (**SHORT**, diversificazione bear): `RSI(2) > 95 AND close < SMA200` →
  short; exit `RSI2 < 30` o `close < SMA5` o 7gg. Unico candidato che PAGA nel
  2018/2022 — il book attuale è tutto long-biased.

**Exit (famiglia validata, identiche per T1-T5):** `close > SMA10` o `RSI2 > 70`
o time-stop 10gg; **scale-in** sul dip più profondo; **NIENTE stop stretti**.

**Dati:** già in casa (`us500_daily.csv` 2007-2026 + `vix_daily.csv`).
**Script:** estendere `mean_reversion_us500.py` con `--trigger t2|t3|t4|t5|t6`.

**Validazione (pre-registrata):**
1. Ogni trigger da solo: nulla + netto costi + IS(2007-2016)/OOS(2017-2026) + stabilità annuale.
2. **Contributo marginale**: giorni ESCLUSIVI del trigger (non già coperti da T1)
   — hanno edge netto da soli? Quanti trade/anno NUOVI aggiungono?
3. Unione finale: CAGR/DD del portafoglio trigger vs T1 solo.

**Kill:** trigger che non batte il nulla sui suoi giorni esclusivi, o aggiunge
<3 trade/anno nuovi → scartato. Se l'unione non migliora CAGR a parità di DD →
resta T1 solo, capitolo chiuso.

**Trappole:** non fare sweep sulle soglie per farle passare (una sola verifica
plateau attorno ai valori standard); non contare due volte i giorni sovrapposti;
T6 va giudicato SOLO sugli anni bear (il suo scopo è il 2018/2022, non il CAGR).

---

## C2 — Term structure VIX (VIX/VIX3M) come regime e timing

**STATO: 🟨 TESTATO (14 lug 2026) — bocciato da solo, ADOTTATO in combo con C5.**
Da solo sul calendario NON migliora nulla (il killer feb-2020 era un'entrata di
calma in contango: nessun filtro d'ingresso la evita) → kill del filtro
standalone. In combo col postspike (C5) è ESSENZIALE: toglie le entrate
premature in tempesta (2020: da −21% a zero perdite). Dati: `vix3m_daily.csv`
(CBOE, dal set-2009). **Risultati: [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md) §4c.**

**Tesi.** Il rapporto VIX/VIX3M distingue **contango** (calma, carry positivo per
chi vende vol) da **backwardation** (stress acuto). È IL condizionatore standard
del rischio equity/vol in letteratura: la backwardation segnala panico in corso
(non vendere vol, dip più profondi in arrivo), il **rientro in contango** segnala
tempesta passata (miglior momento per vendere premio).

**Tre usi (in ordine di valore):**
- (a) **timing put-spread** (per EDGE-2-vendi-put-lontane.md): vendi solo con `VIX/VIX3M < 1.0`
  (o al primo rientro sotto 1.0 dopo un episodio ≥1.0) — confronto vs calendario.
- (b) **dip-buy**: `ratio > 1.05` al trigger = panico conclamato → dimensiona lo
  scale-in più aggressivo (la MR rende di più in alta vol).
- (c) **kill-switch di book**: `ratio > 1.05` persistente = riduci lo short-vol.

**Dati:** VIX3M dal CBOE, stesso pattern di `download_vix.py`
(`https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv`,
storia dal ~2009; prima l'indice si chiamava VXV). Estendere lo script.

**Validazione:** il filtro deve migliorare **t e maxDD sia IS che OOS** dell'edge
a cui si applica; il nulla qui = confronto con filtro su soglia random/shufflata.
**Kill:** nessun miglioramento stabile → si archivia (l'edge base resta com'è).

**Trappole:** non ottimizzare la soglia (0.95/1.0/1.05 da letteratura, verifica
plateau); attenzione al 2008-09 mancante nel VIX3M (partire dal 2009 o accettare
il buco documentandolo).

---

## C3 — Dip-buy trasferito su altri indici (US100, DAX, FTSE, JP225)

**STATO: ⬜ DA BACKTESTARE** (spec pre-registrata, nessun test eseguito)

**Tesi.** La MR di breve è documentata su tutti gli indici sviluppati (più forte
sugli USA). Trasferire l'edge #1 **IDENTICO — stessi parametri, zero re-fit** è
un test di robustezza (se è un fenomeno reale deve trasferire) e insieme
diversificazione + frequenza aggregata (~30-50 trade/anno di famiglia).

**Regole:** ESATTAMENTE l'edge #1: `RSI2<10 & close>SMA200`, scale-in, exit
`SMA10/RSI2>70/10gg`, niente stop. Nessun parametro cambiato per mercato — **il
re-tuning per mercato è la definizione di overfit** e invalida il transfer test.

**Dati:** daily 15-20 anni per indice. Fonte ricerca: Stooq/Yahoo (gratis) o IG
API `/prices` DAY (⚠️ allowance storica 10k/settimana — Stooq preferito). Costi
IG per mercato da listino reale: spread US100 ~1pt, DAX ~1.2pt, FTSE ~1pt,
JP225 ~7pt (verificare sul frontend), financing come US500.

**Validazione per mercato:** nulla + netto costi + IS/OOS + stabilità. Un mercato
passa o muore da solo; il risultato aggregato è il portafoglio dei sopravvissuti.
**Kill per mercato:** non batte il nulla o netto ≤0 → fuori, senza appello.
**Attese oneste:** US100 prior alto (più vol = segnale più grande vs costi
simili), DAX/FTSE medio, JP225 medio-basso (sessione e regime diversi).

---

## C4 — Pre-FOMC announcement drift (event edge)

**STATO: ⬜ DA BACKTESTARE** (spec pre-registrata, nessun test eseguito)

**Tesi.** Drift azionario positivo nelle **24h prima** dell'annuncio FOMC
(Lucca-Moench, Fed NY: ~+49bp/evento medio 1994-2011, uno dei fatti event-driven
più grandi mai documentati). ~8 eventi/anno, hold 24h → **segnale enorme vs costo
minuscolo** (1 spread + 1 notte financing ≈ 0.03% vs segnale storico ~0.3-0.5%).
Perfetto per il criterio "pochi trade, hold corto, segnale grande".

**Rischio noto (da testare, non da assumere):** pubblicato nel 2013-15 →
possibile decadimento post-pubblicazione. Il test costa un'ora: EV alto comunque.

**Regole esatte:**
- Versione daily (2007-2026): buy close del giorno **T−1** (giorno prima
  dell'annuncio), sell close del giorno **T** (giorno FOMC, annuncio 14:00 ET).
- Versione intraday (2022-2026, `us500_1m.pkl`): buy 14:00 ET di T−1, sell
  **13:55 ET di T** (esci PRIMA dell'annuncio — il drift documentato è pre-annuncio;
  la variante che tiene fino al close cattura anche il rumore post-annuncio → testare
  entrambe ma la spec primaria è l'uscita pre-annuncio).

**Dati:** date FOMC 2007-2026 dal sito Fed (~160 date, hardcode in lista) + dati
già in casa.

**Validazione:** confronto vs TUTTI i giorni non-FOMC e vs finestre random della
stessa durata (nulla); split temporale **pre/post-2015** (pubblicazione) come
IS/OOS obbligatorio; stabilità per anno.
**Kill:** media post-2015 ≤ 0 o t<1.5 sul periodo recente → decaduto, morto.
**Trappole:** NON estendere a CPI/NFP per salvarlo (prior separato non robusto);
non spostare la finestra a posteriori per farla funzionare.

---

## C5 — Timing del put-spread: vendere DOPO il panico

**STATO: ✅ SUPERATO (14 lug 2026) — ADOTTATO (in combo col TS di C2) come
modalità d'ingresso del put-spread.** Postspike+TS (2009-2026): ~4 trade/anno,
+2.7%/trade, t=+31.6, 1 sola perdita (−1%) in 59 trade, maxDD≈0 — contro il
calendario che è **fragile alla fase** (worst −100%, maxDD 35% a seconda della
data di partenza). Caveat: 2008 non coperto dal TS (postspike da solo lì −79%),
sensibilità al parametro `cool` — sizing resta come se il −100% fosse possibile.
**Risultati: [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md) §4c.**

**Tesi.** VRP e skew sono più ricchi subito **dopo** gli spike di vol: IV resta
alta mentre la realized rientra (clustering: il crash è già avvenuto). Vendere il
put-spread (EDGE-2-vendi-put-lontane.md) solo in quelle finestre invece che a calendario →
ret/trade più alto e meno rotture.

**Regole esatte:** entra solo se `VIX > 20` **E** `VIX < max(VIX ultimi 10gg) × 0.90`
(spike in raffreddamento) **E** (se C2 è pronto) `VIX/VIX3M < 1.0` (tempesta
passata). Il resto identico al baseline (short 1.5σ / ala 3σ, hold-to-expiry).

**Dati/script:** in casa; aggiungere `--entry-mode postspike` a
`short_vol_us500.py`. Confronto contro baseline calendario (+1.5% CAGR@10%).

**Validazione:** ret/trade × frequenza vs baseline; coda (peggior trade, maxDD);
IS/OOS. **Kill:** se il totale annuo non batte il calendario o la coda peggiora →
resta il calendario. ⚠️ Trade-off dichiarato: meno trade/anno va CONTRO
l'obiettivo frequenza — vince solo se il ret/trade compensa.

---

## C6 — TSMOM multi-asset su forward IG (il progetto grande)

**STATO: ⬜ DA BACKTESTARE** (spec pre-registrata; partire dal gate costi)

**Tesi.** Time-series momentum (Moskowitz-Ooi-Pedersen 2012; AQR *A Century of
Evidence on Trend-Following*): `sign(ritorno 3-12 mesi)` predice il ritorno
successivo su **ogni asset class, da un secolo**, Sharpe lordo diversificato
~0.7-1.0. È il fenomeno più documentato della finanza quantitativa. Long/short,
multi-asset → **scorrelato dal book attuale** (tutto equity-long-biased): è la
diversificazione vera che il progetto cerca da 8 falsificazioni.

**Perché ORA è fattibile coi costi IG** (il macro-core CFD era morto di
financing): i contratti **FORWARD** IG (indici, commodity, FX) **non pagano
financing overnight** — il costo è nello spread più largo + roll trimestrale.
Il killer dei hold lunghi non si applica. ⚠️ Da **verificare per-mercato** sul
listino reale: è il gate #1.

**Universo IG (~16 mercati):** indici US500, US100, DAX, FTSE, JP225 · FX
EURUSD, USDJPY, GBPUSD, AUDUSD · commodity oro, argento, WTI, rame, gas naturale ·
bond Bund, T-Note 10Y.

**Regole esatte (parametri GLOBALI, mai per-mercato):**
- Segnale: ensemble `sign(ret 3m) + sign(ret 6m) + sign(ret 12m)` → posizione
  long/flat/short proporzionale (o maggioranza).
- Rebalance **mensile** (poche operazioni = pochi spread).
- **Vol-target per mercato**: size ∝ 1/vol60gg, contributo di rischio uguale;
  cap di leva totale di book.
- Esecuzione su forward, roll trimestrale (4 attraversamenti spread/anno).

**Gate in ordine (ognuno può uccidere prima di costruire il successivo):**
1. **Gate costi** (1 giorno): tabella reale IG per i 16 mercati — spread forward,
   meccanica roll, esiste il forward? Se il costo annuo stimato (spread×roll +
   eventuale basis) > 3%/anno su metà universo → ridimensionare o morto.
2. **Backtest lordo** (dati Stooq daily 2000-2026): il segnale ensemble sui 16
   mercati dà t>3 diversificato? (deve — se no i dati sono sbagliati).
3. **Netto costi IG** + nulla (stessi mercati, segnale random long/short a pari
   turnover) + IS 2000-2015 / OOS 2016-2026 + stabilità.
**Kill:** netto diversificato t<2 → morto (NON salvare i singoli mercati buoni:
è la selezione a posteriori).

**Effort:** ALTO — pipeline dati multi-mercato + motore di portafoglio
(vol-target, rebalance). Da iniziare DOPO i quick-win C1-C5.

---

## C7 — FX carry: gate di MISURA (non backtest)

**STATO: ⬜ DA MISURARE** (gate pre-registrato, nessun log avviato)

**Tesi.** Il carry FX è documentato, MA su IG retail il tom-next incorpora il
mark-up del broker **in entrambi i sensi** → il carry netto retail è spesso ~0.
**Misurare prima di backtestare** (lezione: mai fidarsi del pricing assunto).

**Gate (2 settimane, effort quasi zero):** loggare i tassi overnight/tom-next IG
(long E short) su EURUSD, USDJPY, GBPUSD, AUDUSD, AUDJPY, USDCHF — sono nel
market detail dell'API (`get_market`: campi swap/funding). Calcolo: carry netto
annualizzato della coppia migliore, al netto del mark-up.
**Kill immediato:** migliore coppia < 2%/anno netto → MORTO senza backtest.
**Solo se passa:** spec completa (basket 3v3 vol-target, filtro momentum
anti-crash, sizing coda) — da scrivere allora, non prima.

---

## Parcheggiati / morti — NON ritestare

- **GEX/gamma (I):** serve dato opzioni SPX esterno affidabile e gratuito — parcheggiato.
- **Weekly options ladder:** spread IG mangia il premio weekly — falsificato.
- **Tutti gli intraday US500** (A-E, G, H, midswing): falsificati — verdetti e
  lezione segnale/costo in [EDGE-falsificati.md](EDGE-falsificati.md).
- **Calendario US500** (ToM, overnight, late-day): falsificati.
- **Cross-market lead-lag (F: Bond/VIX→SPX intraday):** parcheggiato — richiede
  dati intraday di un secondo strumento IG e il prior è indebolito dalla lezione
  segnale/costo intraday.
- **Iron condor:** falsificato al pricing reale — [STORIA-iron-condor.md](STORIA-iron-condor.md);
  il figlio vivo è [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md).

## Ordine operativo

1. **C1** subito (dati in casa, estende l'edge validato, più frequenza = compounding).
2. **C2** (download 5 min, migliora put-spread E dip-buy).
3. **C4** (test da un'ora, verdetto secco vive/morto).
4. **C3** (download daily indici, transfer test).
5. **C5** (variante script esistente).
6. **C6** progetto grande (partire dal gate costi, che è veloce e può ucciderlo subito).
7. **C7** in parallelo quando capita (è solo un log).

In parallelo resta il **sampler dello skew IG** (next step #1 di
[EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md)) — gira da solo una volta al giorno.
