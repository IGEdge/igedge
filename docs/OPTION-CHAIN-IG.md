# OPTION CHAIN SU IG — il metodo GIUSTO (e i 3 modi sbagliati che ci bloccavano)

> **Perché questo documento:** l'abbiamo pagato caro. Prima di scoprire il
> metodo: lockout del login (`invalid-client-security-token`), blocco allowance
> (`exceeded-api-key-allowance` dopo ~20 chiamate ravvicinate), e catene
> TRONCATE che ci nascondevano le scadenze mensili. **Qualunque riscrittura
> delle strategie del bot DEVE seguire questo metodo.** Le implementazioni di
> riferimento sono in `src/options/` — riusarle, non riscriverle.

---

## 1. I TRE MODI SBAGLIATI (vietati — e perché falliscono)

| ❌ Metodo | Cosa succede | Sintomo |
|---|---|---|
| **`search_markets` per la catena** | IG tronca a **~50 risultati**: ti dà i weekly/daily e NASCONDE strike e scadenze mensili. Sembra che "le mensili non esistano" (ci abbiamo creduto per un giorno: esistevano) | catena incompleta, scadenze mancanti |
| **Market navigation** (`/marketnavigation`) | Sul nodo opzioni US500 risponde **404** (sia demo che reale) | non funziona, punto |
| **`get_market` a tappeto sulla catena** | L'allowance si esaurisce: **~20 chiamate ravvicinate → `exceeded-api-key-allowance`** e sei fermo | blocco temporaneo API |

E i due errori di contorno che aggravano tutto:
- **Login ripetuti** (ogni script che fa il suo login): dopo pochi login
  ravvicinati IG dà `invalid-client-security-token` = **lockout** per minuti.
- **Logout a fine script**: butta via la sessione e forza un nuovo login al
  prossimo run → vedi sopra.

---

## 2. IL METODO GIUSTO — passo per passo, col budget di chiamate

### Passo 0 — Sessione e throttle (SEMPRE, prima di tutto)
- **`PersistentIGSession`** (`src/options/session.py`): login UNA volta, token
  salvati in `data/ig_session_live.json` e **riusati anche tra riavvii**;
  relogin solo se scaduti; **MAI logout**. (Verificato: 5 run = 0 login.)
- **`ThrottledClient`** (`src/options/throttle.py`): **minimo 2,5 secondi** tra
  chiamate IG, proattivo (non "riprova dopo l'errore"). Ogni client che tocca
  IG va avvolto qui dentro.

```python
sess = PersistentIGSession(raw_client, "data/ig_session_live.json", audit=audit)
sess.ensure()                                   # 0-1 login, poi sempre riuso
client = ThrottledClient(raw_client, min_interval=2.5)
```

### Passo 1 — La scadenza si CALCOLA, non si cerca (0 chiamate)
Le mensili regolari scadono il **3° venerdì del mese** e esistono SEMPRE.
`monitor.upcoming_standard_expiries()` le calcola in locale;
`Orchestrator._pick_expiry()` sceglie quella con DTE in [20,45] più vicina a 30.
**MAI** dedurre le scadenze dalla search (le tronca) e **MAI** usare le
fine-mese (`OTCSPXEMO`) — non sono le regolari.

### Passo 2 — Scoperta del CODICE epic della scadenza (1-5 chiamate, cacheable)
I codici mensili sono `OTCSPX1..OTCSPX5` ma **RUOTANO** (oggi 1=AUG, 4=JUL,
3=SEP, 5=DEC, 2=MAR — domani cambia): **mai hardcodare il significato**.
`Orchestrator._discover_code()` li sonda: per ogni candidato costruisce UN epic
di prova (`build_epic(code, 7500, "PUT")`), fa `get_market`, legge
`instrument.expiry` e accetta il codice se: formato `MON-YY` (2 pezzi = mensile
standard, non EMO) **e** data = il 3° venerdì target. Si ferma al primo match.

### Passo 3 — Lo SPOT via put-call parity (2 chiamate)
Sul conto opzioni (USD) il sottostante `IX.D.SPTRD.IFE.IP` **non quota**.
`Orchestrator._spot_from_monthly(code)`: get_market su CALL e PUT allo stesso
strike noto (boot 7500) → **S ≈ K + C − P** (r≈0). Robusto, niente search.

### Passo 4 — Gli epic si COSTRUISCONO, non si cercano (1-2 chiamate per gamba)
Anatomia dell'epic opzione US500:

```
OP.D.<CODICE>.<STRIKE><P|C>.IP        es. OP.D.OTCSPX1.7000P.IP
```

- Strike **ogni 50 punti** → `round_strike(target, 50)`.
- `build_epic(code, strike, kind)` costruisce; UNA `get_market` verifica che
  quoti (`marketStatus == TRADEABLE`, bid/offer presenti); se non quota,
  **nudge** ±50/±100 (`resolve_condor_epics_direct` fa tutto questo, con
  sanity check sull'ordine degli strike).
- `get_market` va fatta **SOLO sulle gambe che servono** (2 per uno spread,
  4 per un condor) — mai sulla catena intera.

### Passo 5 — IV senza dipendenze esterne (1 chiamata, opzionale)
`_atm_iv_construct()`: costruisci l'opzione ATM (strike = round_strike(spot)),
get_market, inverti Black-Scholes dal mid → IV ATM autonoma. (Il VIX "vero"
per i segnali arriva dal CBOE, `cdn.cboe.com` — non consuma allowance IG.)

### Budget totale a regime (misurato, con sessione riusata = 0 login)
| Operazione | Chiamate IG |
|---|---|
| Piano di uno spread 2 gambe (`run_spread`) | **~8** |
| Piano condor 4 gambe | ~14 |
| Campione skew (11 strike + scoperta + parity) | **~14** |
| Giornata intera del Pi (sampler + segnali) | **~22, distribuite** |

---

## 3. Tabella codici (stato 15 lug 2026 — SOLO orientativa, la scoperta è dinamica)

| Codice | Cos'è | Uso |
|---|---|---|
| `OTCSPX1..5` | mensili REGOLARI (3° venerdì) — la cifra RUOTA tra i mesi | ✅ trading (via `_discover_code`) |
| `OTCSPXEMO` | fine mese (End of Month) | ❌ MAI (non sono le regolari) |
| `OTCSPXMON` (e simili) | weekly | ❌ trading (premi minuscoli vs spread); ok solo come fallback parity |
| `DO.D.OTCDSPX.*` | daily (solo demo) | ❌ |

⚠️ Il **demo NON ha le mensili** (e ha spread irrealistici): catena e costi si
leggono SOLO dal conto reale (read-only).

---

## 4. Checklist per QUALSIASI nuovo codice che tocca le opzioni IG

- [ ] Client avvolto in `ThrottledClient` (≥2,5s)?
- [ ] Sessione via `PersistentIGSession.ensure()`, **niente login diretto, niente logout**?
- [ ] Scadenza CALCOLATA (3° venerdì) e codice scoperto con `_discover_code`?
- [ ] Epic COSTRUITI con `build_epic` + verifica singola, **zero search per la catena**?
- [ ] `get_market` SOLO sulle gambe necessarie (conta le chiamate: se >15 per
      un'operazione, il design è sbagliato)?
- [ ] Spot via parity (il sottostante non quota sul conto opzioni)?
- [ ] Cache riusata dove possibile (`orchestrator._cache`: gli epic di una
      scadenza non cambiano nella sua vita)?
- [ ] Niente EMO, niente weekly per il trading?

## 5. Dove sta il codice di riferimento (riusare, non riscrivere)

| Funzione | File | Cosa fa |
|---|---|---|
| `PersistentIGSession` | `src/options/session.py` | login una volta, riuso token |
| `ThrottledClient` | `src/options/throttle.py` | 2,5s garantiti tra chiamate |
| `upcoming_standard_expiries` | `src/options/monitor.py` | 3° venerdì calcolati |
| `_pick_expiry` / `_discover_code` / `_spot_from_monthly` / `_atm_iv_construct` | `src/options/orchestrator.py` | scadenza → codice → spot → IV |
| `build_epic` / `round_strike` / `resolve_condor_epics_direct` | `src/options/chain_resolver.py` | costruzione diretta + verifica |
| Esempi d'uso completi | `scripts/run_spread.py`, `scripts/sample_skew_us500.py` | il flusso intero, ~8-14 chiamate |

⚠️ In `chain_resolver.py` esistono ancora `list_option_epics` /
`resolve_condor_epics` **basati su search**: sono il metodo VECCHIO, tenuti solo
per storia — **NON usarli per la catena** (la search tronca). L'unico uso
legittimo della search è trovare UN epic qualsiasi per la parity di emergenza.

## 6. Storia degli errori (per capire il perché delle regole)

1. **13 lug 2026** — search per la catena: mensili "invisibili", credemmo
   esistesse solo la EMO. L'utente le vedeva sul frontend: la search TRONCA.
2. **13 lug 2026** — ~20 get_market di fila per leggere la catena:
   `exceeded-api-key-allowance` → nacque il throttle.
3. **13 lug 2026** — ogni script faceva il suo login: lockout
   `invalid-client-security-token` → nacque la sessione persistente.
4. **14 lug 2026** — soluzione completa: scadenze calcolate + codici sondati +
   epic costruiti + parity. Da allora: **0 blocchi**, 0-1 login/giorno,
   ~22 chiamate/giorno sul Pi.
