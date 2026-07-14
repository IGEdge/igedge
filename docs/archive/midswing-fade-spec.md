> **ARCHIVIO STORICO** — spec metodologica del Midswing-Fade (falsificato al Test 1, 13 lug 2026 — verdetto in `../EDGE-falsificati.md`). La spec resta come TEMPLATE di rigore riutilizzabile per futuri progetti.

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