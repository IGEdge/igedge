# Registro degli EDGE — INDICE

**Questo file è solo l'indice.** Ogni idea sta in UNA sola categoria e ogni
categoria ha il suo documento. Qui: stato, numeri chiave e link — niente dettagli.

| Categoria | Significato | Documento |
|---|---|---|
| ✅ VALIDATO | backtest completo superato → tradabile | un doc per edge: `EDGE_<NOME>.md` |
| 🟡 VALIDATO CON GATE | backtest ok, manca una conferma pre-live | idem |
| ⬜ DA BACKTESTARE | solo specifica, **nessun test fatto** | [EDGE-candidati-da-testare.md](EDGE-candidati-da-testare.md) |
| ❌ FALSIFICATO | backtestato, niente edge — non ritestare | [EDGE-falsificati.md](EDGE-falsificati.md) |
| ⚪ MARGINALE | backtestato positivo ma non adottato | EDGE-falsificati.md §marginali |

**Ciclo di vita di un'idea:** nasce in `EDGE-candidati-da-testare.md` (⬜ spec pre-registrata)
→ backtest con l'apparato → se regge: doc dedicato `EDGE_<NOME>.md` + riga qui
tra i validati; se fallisce: riga in `EDGE-falsificati.md`. Mai a metà.

**L'apparato (obbligatorio, TUTTO):** test del nulla (dove applicabile) + netto
costi reali + IS/OOS + sweep parametri (plateau, non picco) + stabilità per anno.
Per le opzioni: SOLO smile reale + spread per gamba, mai VIX piatto (lezione #3).
Se fallisce un pezzo → falsificato, niente varianti di salvataggio.

---

## ✅ 🟡 VALIDATI — backtest superato (2)

### EDGE #1 — Buy-the-Dip CFD + ENSEMBLE C1 — ✅ pronto
**→ [EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md)**
`RSI(2)<10 AND close>SMA200`, scale-in, exit `SMA10 / RSI2>70 / 10gg`, intraday
flat overnight, niente stop stretti. Baseline 2008-2026: WR 86%, +0.73%/trade,
CAGR +6.2%@1x, maxDD 10.4%. **ENSEMBLE C1 (validato 14 lug 2026, §5b): unione di
5 trigger MR → 342 trade (~20/anno), CAGR +8.8%@1x / +27.4%@3x, STESSO maxDD
(10%)** + satellite short t6 che paga nei bear (2020 +10%, 2022 +9%).
Script: `scripts/mean_reversion_us500.py --trigger union|t6`.

### EDGE #3 — Compra call mensile in uptrend (opzioni) — 🟨 backtest forte, 2 gate
**→ [EDGE-3-compra-call-mensile.md](EDGE-3-compra-call-mensile.md)**
Ogni mese, se S&P>SMA200: compra call spread ATM/+1σ sulla mensile IG, tieni a
scadenza, rischio = premio (~$50/contratto). Sfrutta le **call IG a sconto**
(0.77×VIX misurato) + drift. 2007-2026: ~11 trade/anno, WR 54%, +25%/trade,
t=+3.0, IS/OOS entrambi positivi. **Su €1.000 ≈ €110/anno, su €10.000 ≈
€1.100/anno, maxDD 16%** (a pricing prudente 0.90: la metà, ancora positivo).
**GATE:** (1) sampler skew conferma ATM ≤0.82×VIX; (2) pilot reale 1 contratto.
RICORRENTE mensile — il motore direzionale del book opzioni.

### EDGE #2 — Put-spread far-OTM su opzioni US500 — 🟡 validato, gate pre-live
**→ [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md)**
Vende lo skew ricco delle put IG, **rischio definito, IL programma per il
capitale attuale (€1-3k)**. Config operativa (14 lug 2026, §4b+§4c): **short
1.5σ / ala 2.5σ (max loss ~$370/contratto) + ingresso POSTSPIKE+TS** (VIX≥20 in
raffreddamento E VIX/VIX3M≤1 — mai vendere nella calma piatta né in piena
tempesta): ~4 trade/anno, +2.7%/trade, 1 perdita in 59 trade (2009-2026),
**su €1000 ≈ +3.4%/anno con maxDD osservato ≈0** (tail teorico resta −100% del
rischio → 1 contratto/€1000). Sampler skew ATTIVO (1° campione: modello regge).
**GATE prima del live:** (1) sampler skew 2-4 settimane, (2) paper/pilot
coerente. Infrastruttura pronta (`src/options/`).

---

## ⬜ DA BACKTESTARE — spec pronte (6 rimasti)

**→ [EDGE-candidati-da-testare.md](EDGE-candidati-da-testare.md)** — spec complete pre-registrate (tesi,
regole esatte, dati, criterio di kill). **Nessuno dei rimanenti ha ancora un solo
backtest: lì non esistono risultati, solo prior.**

| # | Candidato | In una riga | Prior | Ordine |
|---|---|---|---|---|
| ~~C1~~ | ~~MR Ensemble US500~~ | ✅ **SUPERATO** (14 lug) → adottato, EDGE #1 §5b — ⚠️ capital-gated (serve ~€2.5k+) | — | fatto |
| ~~C2~~ | ~~Term structure VIX~~ | 🟨 **TESTATO** (14 lug): bocciato da solo, adottato in combo con C5 — EDGE #2 §4c | — | fatto |
| ~~C5~~ | ~~Timing put-spread~~ | ✅ **SUPERATO** (14 lug) → adottato: ingresso postspike+TS — EDGE #2 §4c | — | fatto |
| ~~C4~~ | ~~Pre-FOMC drift~~ | ❌ **FALSIFICATO** (15 lug): effetto morto post-2015 (t=0.85) | — | morto |
| C3 | Dip-buy altri indici | transfer su US100/DAX/FTSE/JP225 — ⚠️ capital-gated (min size CFD) | ⭐⭐⭐ | gated |
| C6 | TSMOM multi-asset | trend following su ~16 forward IG — ⚠️ verificare min size (probabile gated) | ⭐⭐⭐⭐ | gated |
| C7 | Carry FX | SOLO gate di misura tom-next (log 2 settimane) | ⭐ | parallelo |
| ~~C8~~ | ~~Uscite gestite~~ | 🟨 **TESTATO** (15 lug): put ❌ (hold-to-expiry resta legge) · call ✅ regola 60%-ampiezza ADOTTATA (EDGE-3 §2) | — | fatto |
| ~~C9~~ | ~~Timing pre-FOMC~~ | ❌ **FALSIFICATO** (15 lug): −0.1%/trade e meno frequenza | — | morto |
| **C10** | Ladder call | 2 posizioni sfalsate di 2 settimane (~22 ingressi/anno) | ⭐⭐ | 3° (da €2k) |
| **C11** | Multi-indice opzioni | stessi edge su DAX/FTSE IG se lo smile è favorevole | ⭐⭐⭐ | settimana |

---

## ❌ FALSIFICATI — backtestati, nessun edge (15)

**→ [EDGE-falsificati.md](EDGE-falsificati.md)** — verdetti completi + le 3
lezioni permanenti. Non ritestare senza un angolo genuinamente nuovo. Sintesi:

- **CFD/prezzo US500 (13):** Macro core · Fade sessioni · Continuation sessioni ·
  ORB · Overnight drift · Trend breakdown · Late-day drift (A) · Turn-of-Month (E) ·
  Intraday MR 15m (B) · VWAP MR (C) · First-hour filter (D) · Midswing-fade ·
  Volatility squeeze (G) · Accum/Dist (H)
- **Opzioni (2 + varianti):** **Iron condor VRP** (morto al pricing reale — storia
  completa in [STORIA-iron-condor.md](STORIA-iron-condor.md)) · hedge bull-put sui dip ·
  tail-hedge long-vol · weekly ladder
- **⚪ Marginali non adottati:** dip-call (positivo ma contingente al pricing IG)

---

## Mappa completa dei documenti

| File | Contenuto | Categoria |
|---|---|---|
| [INDICE-EDGE.md](INDICE-EDGE.md) | questo indice | — |
| [STATO-PROGETTO.md](STATO-PROGETTO.md) | **checkpoint 15 lug 2026**: cosa gira da solo + checklist ripresa ~5 ago | 📌 |
| [OPTION-CHAIN-IG.md](OPTION-CHAIN-IG.md) | **COME si interroga la catena opzioni IG** senza farsi bloccare (metodo obbligatorio + checklist per ogni nuovo codice) | 📌 |
| [PIANO-RISCRITTURA-BOT.md](PIANO-RISCRITTURA-BOT.md) | **quali strategie vanno nel bot e architettura modulare** (4 strati, interfaccia comune, to-do, invarianti di sicurezza) | 📌 |
| [EDGE-1-compra-il-dip.md](EDGE-1-compra-il-dip.md) | edge #1 dip-buy CFD: regole, numeri, leva, comandi | ✅ |
| [EDGE-2-vendi-put-lontane.md](EDGE-2-vendi-put-lontane.md) | edge #2 put-spread opzioni: doc vivo, gate, next steps | 🟡 |
| [EDGE-candidati-da-testare.md](EDGE-candidati-da-testare.md) | 7 candidati DA backtestare, spec pre-registrate | ⬜ |
| [EDGE-falsificati.md](EDGE-falsificati.md) | tutti i morti: verdetti, script, 3 lezioni | ❌ ⚪ |
| [STORIA-iron-condor.md](STORIA-iron-condor.md) | storia del condor (falsificato) + infrastruttura opzioni | ❌ storia |
| [STORIA-copertura-put-sui-dip.md](STORIA-copertura-put-sui-dip.md) | hedge bull-put sui dip (bocciato) | ❌ storia |
| [report/report-edges.html](report/report-edges.html) | **report GRAFICO dei 2 edge** (14 figure, esempi reali, sim in €; rigenera: `make_edge_charts.py` + `make_edge_report.py`) | ✅ 🟡 |
| [archive/](archive/) | proposte pre-test originali (Tier 1-3, spec midswing) | archivio |

Dati: `data/research/` (vedi il suo README). Infrastruttura live opzioni:
`src/options/` (riusabile per qualunque strategia in opzioni su IG).
