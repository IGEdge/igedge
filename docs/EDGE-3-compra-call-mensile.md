# EDGE #3 (candidato forte) — Compra call mensile in uptrend (opzioni US500 IG)

**IN UNA FRASE:** ogni mese, se l'S&P è sopra la sua media a 200 giorni, COMPRI
una call (o call spread) sulla scadenza mensile IG e la tieni a scadenza —
rischi solo il premio (~$45-65 a contratto), catturi il rialzo con leva.

> **STATO: 🟨 BACKTEST FORTE — NON ancora provato sul reale.**
> Due gate prima dei soldi veri: **(1)** il sampler skew deve confermare che IG
> prezza davvero le opzioni a ~0.77-0.82×VIX (l'edge dipende da questo);
> **(2)** pilot reale con 1 contratto (regola del progetto: nessun edge è
> provato finché i fill veri non confermano il backtest — lezione iron condor).

---

## 1. Perché dovrebbe funzionare (3 motivi, tutti misurabili)

1. **Le call IG costano poco** (misurato sui prezzi veri, 14 lug 2026: ATM a
   0.77-0.80×VIX, +1σ a 0.61×VIX). Compri l'esposizione al rialzo a sconto.
2. **Il drift dell'S&P è la fonte di rendimento più documentata che esista** —
   e il filtro SMA200 (lo stesso dell'edge #1) ti tiene fuori dai bear.
3. **Su IG questo è il modo GIUSTO di stare long con poco capitale:** il CFD
   minimo forza leva 7.5x su €1.000 e paga financing ~5.5%/anno; l'opzione ha
   rischio definito (= premio), zero financing, size perfetta per €1.000-10.000.

**Cosa NON è:** non è alpha market-neutral — è esposizione al rialzo azionario
con rischio cappato e vol comprata a sconto. Perde (il premio) nei mesi piatti
o in calo. Vince perché i mesi buoni pagano 2-5× il premio.

## 2. Le regole esatte

- Ogni ~mese (scadenza regolare 3° venerdì, 21-28 giorni):
  - **se** `close > SMA200` (uptrend): compra **call spread ATM / +1σ**
    (o call secca ATM — stessi numeri) sulla mensile US500;
  - **se** sotto SMA200: **fermo** (niente trade quel mese).
- **USCITA (regola C8, adottata 15 lug 2026): chiudi in anticipo quando lo
  spread vale ≥60% dell'ampiezza (≈2× il debito pagato)** e rientra al ciclo
  successivo se l'uptrend regge; altrimenti tieni a scadenza (cash-settled).
  Migliora CAGR (+21→+25% full, +32→+37/43% OOS a parità di sizing), taglia il
  maxDD (71→50%) e alza il WR (51→57%). ⚠️ Regola da CONFERMARE sui prezzi veri
  durante il pilot (i valori mid-life del backtest sono da modello).
- Rischio massimo = premio pagato.
- 1 contratto ogni ~€1.000 di equity.
- Script: `scripts/postpanic_call_us500.py --spike-min 0 --cool 99 --no-ts
  --uptrend --from 2007-01-01`

## 3. I numeri (pricing reale smile IG, spread 1.5pt/gamba, 2007-2026)

| | trade/anno | WR | ret/trade | t | su €1.000 | su €10.000 | maxDD |
|---|---|---|---|---|---|---|---|
| **ATM 0.77×VIX (misurato)** | ~11 | 54% | **+25%** del premio | **+3.0** | **~€110/anno** | **~€1.100/anno** | 16% |
| ATM 0.90 (prudente) | ~11 | 52% | +13% | +1.7 | ~€61/anno | ~€600/anno | 23% |

- **IS/OOS:** 2007-2016 +16%/trade (t=1.4) · 2017-2026 +28% (t=2.4) — nessun
  decadimento, entrambe le metà positive.
- **Plateau:** call secca ≈ spread; ala venduta a 1σ/1.5σ/2σ ≈ uguali; orizzonte
  21-28gg ottimo (14gg peggiora: lo spread pesa di più). Nessun parametro magico.
- **Anni cattivi:** 2018 −16% (11 trade), 2022 −100% sui 3 trade fatti (il filtro
  SMA200 tiene fuori quasi tutto l'anno). Il costo del filtro trend È il suo
  valore: senza, il 2008 fa −60% l'anno.
- **Timing "furbo" NON serve:** l'ingresso post-panico non batte il calendario
  (test del nulla: 42%) — qui l'edge è il prezzo + il drift, non il momento.

## 4. Il book opzioni completo (con l'EDGE #2)

I due edge opzioni si completano sui regimi e vivono sullo stesso conto opzioni:

| Regime | Cosa fa il book |
|---|---|
| Uptrend tranquillo | **EDGE #3**: compra call mensile (motore) |
| Post-panico (VIX≥20 che rientra, TS≤1) | **EDGE #2**: vendi put-spread (reddito ricco) |
| Bear conclamato (sotto SMA200) | fermo (o satellite short CFD quando c'è capitale) |

**Insieme su €1.000: ~€130/anno (~13%). Su €10.000: ~€1.300/anno.** ⚠️ Code
correlate: un crash improvviso in uptrend colpisce entrambi (le call perdono il
premio, il put-spread può rompersi) → mai sovradimensionare i due insieme.

## 5. Cosa manca prima dei soldi veri (i 2 gate)

1. **Sampler skew (GIÀ ATTIVO, `sample_skew_us500.py --live` 1×/giorno):** se il
   rapporto ATM/VIX medio su 2-4 settimane resta ≤0.82 → l'edge vale ~€110/€1.100;
   se sale verso 0.90 → vale la metà (ancora positivo); se ≥0.95 → riconsiderare.
   **È LO STESSO gate dell'EDGE #2** — un solo sampler valida entrambi.
2. **Pilot reale, 1 contratto:** comprare UNA call spread mensile vera, verificare
   fill/spread/settlement vs modello. Costo del test ≈ il premio (~€50).

## 6. File

| Cosa | Dove |
|---|---|
| Backtest | `scripts/postpanic_call_us500.py` (`--uptrend`, `--atm`, `--to`) |
| Sampler skew (gate) | `scripts/sample_skew_us500.py` → `data/research/skew_samples.csv` |
| Edge gemello (vendita put) | [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md) |
| **Esecuzione (FATTA, 14 lug 2026)** | `scripts/run_spread.py --strat callspread --live` (plan-only di default; `--arm --i-understand-live-risk` per il pilot). Segnale SMA200 automatico, compra la call PRIMA di vendere quella sopra (mai nudi). Verificato plan-only sul reale: call 7550/7950 AUG-26, rischio ~€125/contratto. |
