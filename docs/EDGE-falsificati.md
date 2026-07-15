# EDGE FALSIFICATI — backtestati, NESSUN edge (non ritestare)

Tutto qui dentro è stato **testato con l'apparato completo** (nulla, netto costi,
IS/OOS, sweep, stabilità) e ha **fallito**. Non si ritesta senza un angolo
genuinamente NUOVO (dato nuovo, mercato nuovo, struttura costi diversa). Le
proposte originali pre-test, coi razionali, sono in [archive/](archive/).

---

## CFD / prezzo US500 (13 idee)

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
| **Midswing-Fade** (short al 50% ritracc.) | `midswing_fade_us500.py` | **Ucciso al Test 1 (placebo/falsificazione)**, la sua stessa metodologia pre-registrata. Il livello di ritracciamento (0.382/0.5/0.618) è **statisticamente indistinguibile** da livelli casuali U(0.30,0.70) sulla stessa gamba: MFE/MAE reali ≈ placebo (KS p=0.9+, bootstrap p=0.3+), in diverse combo il reale è pure peggio del placebo. Robusto su k_swing∈{2,3,4}×a_min∈{3,5}×r_entry×window. Nessuna proprietà speciale del livello → rumore. Per la spec ci si ferma qui (niente filtri di salvataggio). Era l'unica idea SHORT (aggirava l'headwind) → morta comunque. US500 5m RTH 2022-2026. Spec metodologica riutilizzabile: [archive/midswing-fade-spec.md](archive/midswing-fade-spec.md). |
| **Volatility Squeeze** (Strat. G, Tier 3) | `tier3_intraday_us500.py --strat squeeze` | Breakout post-squeeze Bollinger(20,2): netto +0.05% (t=1.2) ma **batte 0% del nulla, z=−5** → il timing del breakout è ATTIVAMENTE peggio di entry random (null +0.18% vs reale +0.07%). Nessuna struttura, il positivo è solo la selezione dei giorni uptrend. N=87. 2022-2026. |
| **Accum/Distribution** (Strat. H, Tier 3) | `tier3_intraday_us500.py --strat accdist` | Stessa firma di B/C: **struttura reale** (accumulo sotto VWAP batte il nulla z=+2.9, WR gross 76%) ma **netto ≈0** (+0.004%, t=0.26), IS e OOS ≈0 → headwind intraday. Non tradeable. 2022-2026. |

---

## Opzioni US500 (2 idee + varianti)

### ❌ Iron condor VRP (14 lug 2026) — storia completa: [STORIA-iron-condor.md](STORIA-iron-condor.md)
Il VRP **esiste** (misurato: VIX−realized +3.6 pt vol, t=32.7) ma il primo
backtest prezzava tutte le gambe a **VIX piatto**, sovrastimando il credito
**~2.3×** (falso +6.3% CAGR). Col lo **smile reale IG** (ATM 0.77×VIX, **call OTM
~0.6×VIX quasi regalate**, put OTM 1.1-1.4×VIX) il lato call è netto negativo
(−1.4pt, non copre lo spread) e il condor muore: WR 84% ma ret/trade −0.5%,
CAGR −0.5%. Confermato con **misura diretta** dei prezzi reali IG (credito reale
= 43% del modello-a-VIX). Script: `short_vol_us500.py --strat condor --real-smile`.
**Il figlio sopravvissuto (solo lato put) è [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md)** (🟡 validato con gate).

### ❌ COPERTURA REATTIVA in-trade sul put-spread (14 lug 2026)
`scripts/hedge_reactive_us500.py`. L'idea (dell'utente, sensata a priori): lo
spread resta aperto; se il mercato rompe una soglia durante il trade → compri
una put ATM; la rivendi al picco del panico (o a scadenza), eventualmente
chiudendo anche lo spread in modo coordinato. **Falsificata su TUTTE le
varianti** (trigger 1.0/1.25/1.5σ × exit raffreddamento/scadenza × ±chiusura
coordinata, su 2009-2026 E 2007-2026 col 2008): il programma adottato passa da
**+2.7%/trade (t=+31.6) a −0.2…+0.3% (t≈0)**; nel 2008 il trade killer va da
−79% a −105% (variante cool) o −68% (expiry) ma i falsi allarmi affondano il
totale. **Perché fallisce (strutturale):** (1) l'85-90% delle rotture di soglia
RECUPERA entro scadenza (è il motivo per cui la strategia ha WR 97-98%) → quasi
ogni copertura è un falso allarme; (2) comprare la put DOPO la rottura = pagare
la volatilità al prezzo del panico — **esattamente il pedaggio che la strategia
incassa dagli altri**: reattivi si è sempre dalla parte sbagliata dello skew.
**La protezione vera è già nella struttura:** l'ala comprata ALL'INGRESSO (prima
della tempesta, a prezzo giusto) + sizing 1 contratto/€1000 (perdita massima
~−€340) + la guardia soft che allarga gli strike nei regimi fragili. Possibile
angolo futuro NON testato: trigger INTRADAY (reagire prima che l'IV esploda) —
richiede dati intraday di opzioni che non abbiamo; da valutare solo col pilot.

### ❌ Uscite gestite sul PUT-spread (C8-put, 15 lug 2026)
`managed_exit_us500.py`. Chiudere il vincitore in anticipo (residuo ≤50/25/10%
del credito) PEGGIORA sempre la baseline hold-to-expiry (+2.7%→+0.6/+1.2%; ≈0
nella finestra col 2008): il credito è sottile (~10pt) e lo spread d'uscita ne
mangia il 15%+; il riciclo aggiunge trade peggiori. **Terza conferma della
lezione round-trip: sul lato VENDITA, hold-to-expiry è legge.** (Sul lato
COMPRA invece la regola 60%-ampiezza MIGLIORA — adottata in EDGE-3.)

### ❌ Pre-FOMC drift (C4 + C9, 15 lug 2026)
`fomc_timing_us500.py`, 154 annunci programmati 2007-2026. Effetto reale
pre-2015 (+0.55%/evento, t=2.9, Lucca-Moench confermato) ma **morto dopo la
pubblicazione**: post-2015 +0.10% (t=0.85) ≈ giorni normali (+0.05%). Come
overlay di timing della call mensile: −0.1%/trade e frequenza ridotta. Caso da
manuale di edge accademico arbitraggiato via. Non ritestare.

### ❌ Varianti e hedge bocciati (13-14 lug 2026)
- **Bull-put sui dip come copertura del condor** (`bull_put_dip_us500.py`,
  [STORIA-copertura-put-sui-dip.md](STORIA-copertura-put-sui-dip.md)): short-put = stesso
  rischio del condor → correlato, perde nei crash INSIEME (2020 −62%, 2011 −70%).
  Non diversifica, concentra.
- **Tail-hedge long-vol** (`short_vol_us500.py --tail-hedge`): comprare put
  lontane peggiora ogni metrica e ogni anno-crash (2020 incluso) — restituisce il
  premio. La coda si gestisce con rischio definito + filtro VIX + sizing, NON
  comprando vol. Riconfermato anche sul put-spread (14 lug 2026).
- **Weekly options ladder**: lo spread IG mangia il premio minuscolo delle weekly
  → la frequenza settimanale non è percorribile.

---

## ⚪ MARGINALI — backtestati positivi ma NON adottati

- **Dip-call** (comprare call scontate sui segnali dip-buy, `dip_call_us500.py`,
  14 lug 2026): +7.9% CAGR **se** le call restano a IV ~0.77×VIX, ma il risultato
  è **contingente al pricing** (0.88×VIX → +2.5%; 1.0×VIX → negativo) e non batte
  il CFD dip-buy (che non ha questa dipendenza). Il dip AGGIUNGE vs il nulla, il
  veicolo è il problema. Riconsiderare SOLO se il sampler dello skew (gate di
  EDGE-2-vendi-put-lontane.md) conferma le call stabilmente ≤0.8×VIX.

---

## Le 3 lezioni permanenti (pagate coi test)

**Lezione #1 — costi CFD IG US500:** i costi uccidono tutto ciò che ha **stop
stretti** (lo spread domina) o **hold lunghi** (financing). Sopravvive solo:
pochi trade + hold corti (dip-buy) o intraday flat overnight. Su mean-reversion
NIENTE stop stretti (dimezzano il rendimento e raddoppiano il DD).

**Lezione #2 — il problema dell'intraday è il RAPPORTO SEGNALE/COSTO, non un
"headwind direzionale".** Misura pulita sessione cash RTH (Dukascopy 09:30→16:00
ET, 2022-2026): intraday +5.5%/yr (t=0.8), overnight +7.0%/yr (t=1.3) — entrambi
positivi ma deboli. B/C/D/H falliscono perché il segnale cattura ~0.02-0.05% vs
spread ~0.02% + rumore 1.2%/gg, e le exit tagliano i vincitori. La struttura è
reale (z fino a +6) ma il margine netto ≈0. L'edge #1 rende perché la reversione
si sviluppa su GIORNI (segnale grande vs costo). [Nelle righe sopra "headwind
intraday" va letto così.]

**Lezione #3 — un backtest di OPZIONI a VIX piatto è INAFFIDABILE.** La VIX è una
misura variance-swap che sovrastima il premio ATM/call incassabile. Servono:
(a) lo **smile reale** misurato dai prezzi del broker; (b) gli **spread bid/ask
reali per gamba**; (c) verifica con **misura diretta** del credito reale su un
esempio live. È la lezione che ha falsificato il condor dopo che sembrava +6.3%.

---

## Archivio (proposte originali pre-test, solo storia)
- [archive/proposte-intraday-2026-07.md](archive/proposte-intraday-2026-07.md) — le proposte Tier 1-3 (A-I) coi razionali originali
- [archive/midswing-fade-spec.md](archive/midswing-fade-spec.md) — spec metodologica midswing (template di rigore riutilizzabile)
