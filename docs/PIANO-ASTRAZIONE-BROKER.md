# PIANO — Astrazione broker (motore multi-adapter)

> **Stato:** piano di migrazione (non implementato).  
> **Issue di tracking:** [#2](https://github.com/IGEdge/igedge/issues/2)  
> **Owner:** Antonio / agente su issue GitHub collegata.  
> **Modello:** adapter **aperto** — qualunque broker con API adeguate e capability
> sufficienti per la strategia; non una lista chiusa di vendor.  
> **Prime implementazioni di riferimento (non esaustive):** IG (già live),
> Interactive Brokers (IBKR), tastytrade — usate per validare le porte; altri
> adapter si aggiungono senza toccare il dominio.  
> **Leggere insieme a:** [ARCHITETTURA-BOT.md](ARCHITETTURA-BOT.md), [PIANO-RISCRITTURA-BOT.md](PIANO-RISCRITTURA-BOT.md), [OPTION-CHAIN-IG.md](OPTION-CHAIN-IG.md), [STATO-PROGETTO.md](STATO-PROGETTO.md).

---

## 0. Perché questo documento esiste

Oggi IGEdge è un **motore di trading quantitativo** (strategie, rischio, reconcile, opzioni a rischio definito) ma lo **strato di esecuzione e mercato è accoppiato a IG**:

- `src/core/ig_client.py` — REST IG (CST / X-SECURITY-TOKEN, `/positions/otc`, …)
- `src/options/chain_resolver.py` — epic `OP.D.…`, search terms US500 IG
- `src/options/session.py`, `throttle.py`, `executor.py` — assumono il contratto IG
- `OrderManager` / `RiskManager` / `dip_buy` — chiamano metodi e concetti IG (`epic`, `dealId`, …)
- Principio operativo attuale: **broker = IG** (conti CFD e opzioni separati)

Questo è coerente con la fase “validare edge su un broker reale”, ma **blocca il prodotto** se il motore deve poter girare su **qualsiasi intermediario** con API mature e prodotti adatti alla strategia, senza riscrivere le strategie.

Obiettivo di questo piano: rendere il **cuore** (segnali, sizing, rischio, strutture put/call spread, guardia, store logico) **indipendente dal broker**, e isolare **ogni** broker in un **modulo adapter** plug-in.

### Principio prodotto (non negoziabile)

> Un broker entra nel motore **se e solo se** implementa le porte richieste e
> passa la suite di **conformance** per le capability dichiarate (opzioni
> verticali, CFD, multi-leg atomico, ecc.).  
> Non esiste una whitelist chiusa di marchi. Esiste un **contratto** + test.  
> Nuovo broker = nuovo package `src/broker/<vendor>/` + registrazione in
> `factory.py` + conformance verde — **zero modifiche** alle strategie.

IBKR e tastytrade compaiono sotto come **prime implementazioni di prova** del
contratto (oltre a IG già esistente), non come lista esaustiva.

---

## 1. Cosa significa “astrazione broker” (definizione operativa)

### 1.1 Cosa deve essere astratto (cuore / dominio)

Queste parti **non** devono conoscere endpoint, header, nomi epic IG, o SDK di un vendor:

| Dominio | Esempi nel repo oggi | Deve parlare in termini di… |
|--------|----------------------|-----------------------------|
| Strategie | `dip_buy`, put/call spread signals | strumento logico, barre OHLC, azioni ENTER/EXIT, build di **legs** astratte |
| Rischio | `risk_manager` | equity, esposizione, kill switch, size in unità di rischio |
| Orchestrazione | `spread_orchestrator.plan_spread` | spot, IV/σ, strike target, credito/debito, max loss |
| Persistenza logica | `position_store`, `condors.db` | `position_id` interno + mapping broker |
| Guardia | `gamma_guard`, `seasonality` | già quasi agnostica (legge JSON/CSV esterni) |

### 1.2 Cosa resta specifico per broker (adapter)

| Adapter | Responsabilità |
|---------|----------------|
| Sessione / auth | login, refresh token, account switch |
| Market data | prezzi, barre, quote bid/ask per strumento |
| Instrument map | tradurre `SymbolRef` interno → identificativo broker |
| Trading | open/close, multi-leg se supportato, confirm/fill |
| Positions | elenco posizioni aperte per reconcile |
| Options chain | elencare/costruire strike disponibili su underlying+expiry |
| Capability flags | cosa il broker sa fare (multi-leg atomico? CFD? solo opzioni?) |

### 1.3 Cosa NON è “astrazione”

- Non è “un file `.env` con URL diversi” sullo stesso client IG.
- Non è copiare-incollare `IGClient` e rinominarlo.
- Non è far sì che *tutti* i broker si comportino uguali: se IBKR ha combo orders e IG apre gamba-per-gamba, l’adapter espone capability diverse; il **executor di dominio** sceglie il percorso in base alle capability, senza if sparsi nelle strategie.

---

## 2. Stato AS-IS (inventario accoppiamento)

### 2.1 CFD path

```
bot.py
  → IGClient
  → PositionStore.reconcile(ig.get_positions())
  → DipBuyStrategy(ig) → ig.get_prices_v2(epic, …)
  → RiskManager(ig)
  → OrderManager(ig, store) → ig.open_position / close_position → dealId
```

Accoppiamenti critici: `epic`, `dealId`/`dealReference`, conferma ACCEPTED, sizing CFD IG (`value_per_point`), host DEMO/LIVE.

### 2.2 Options path

```
run_spread.py / sampler_daemon
  → PersistentIGSession(IGClient)
  → ThrottledClient
  → SpreadOrchestrator → get_market / build_epic IG
  → CondorExecutor.open_condor (longs-first, anti-naked)
  → CondorStore (SQLite)
```

Accoppiamenti critici: formato epic opzioni, discovery codice mensile (`OTCSPX…`), parità put-call per spot, throttle 2.5s anti rate-limit IG, conti LIVE `IG_LIVE_*`.

### 2.3 Dati esterni già agnostici (da preservare)

- CBOE VIX / VIX3M (`run_spread.gather_signals`, `sample_skew`, daemon)
- `us500_daily.csv` / research backtest
- Gamma scanner (mount RO) + stagionalità 1950–2024

Questi restano nello **strato Contesto** (come in PIANO-RISCRITTURA §2): non vanno dentro l’adapter broker.

### 2.4 Vincolo consapevole attuale

In [PIANO-RISCRITTURA-BOT.md](PIANO-RISCRITTURA-BOT.md) lo “Strato 1” è etichettato **infrastruttura IG** e si evita astrazione prematura *tra strategie*.  
Questo piano **non contraddice** quello: astrae lo **strato broker sotto** le strategie, proprio perché il prodotto deve poter cambiare intermediario senza toccare put-spread / call-spread / dip-buy.

---

## 3. Architettura TO-BE

### 3.1 Diagramma a strati

```
┌─────────────────────────────────────────────────────────────────┐
│  App / CLI / Daemon / Dashboard                                 │
│  bot.py · run_spread.py · sampler_daemon.py · dashboard         │
├─────────────────────────────────────────────────────────────────┤
│  Dominio (broker-agnostico)                                     │
│  strategies · spread planning · risk · guard · logical store    │
├─────────────────────────────────────────────────────────────────┤
│  Porte (interfacce)          src/broker/ports.py                │
│  BrokerGateway · MarketDataPort · TradingPort ·                   │
│  OptionsChainPort · AccountPort · SessionPort                     │
├─────────────────────────────────────────────────────────────────┤
│  Adapter (un package per broker — lista APERTA)                 │
│  src/broker/ig/           ← refactor dell’attuale               │
│  src/broker/ibkr/         ← prima prova oltre IG (esempio)      │
│  src/broker/tastytrade/   ← seconda prova (esempio)             │
│  src/broker/<altro>/      ← qualunque vendor conforme           │
├─────────────────────────────────────────────────────────────────┤
│  Vendor SDK / REST / FIX (dipendono dall’adapter)                │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Modello dati interno (contratti minimi)

Da introdurre in `src/broker/types.py` (nomi indicativi, da congelare in ADR):

```text
BrokerId          = "ig" | "ibkr" | "tastytrade" | …
AccountKind       = "cfd" | "margin_securities" | "options" | …
SymbolRef         = { asset_class, underlying, currency, … }   # logico
BrokerInstrument  = { broker_id, native_id, symbol_ref, meta }
Bar               = { ts, open, high, low, close, volume? }
Quote             = { bid, ask, mid?, ts, bid_size?, ask_size? }
OrderRequest      = { instrument, side, qty, order_type, tif, legs? }
OrderAck          = { client_order_id, broker_order_id, status }
Fill              = { … avg_price, qty, ts }
Position          = { position_id, instrument, qty, avg_price, broker_keys }
OptionContract    = { underlying, expiry, strike, right, multiplier, native_id }
Capability        = frozenset{ "atomic_multileg", "cfd", "native_stop", … }
```

Regola: lo **store SQLite** salva sempre `position_id` interno + `broker_id` + `native_keys` (JSON). Mai assumere che `dealId` esista su tutti i broker.

### 3.3 Porte obbligatorie (API interna)

```text
SessionPort
  connect() / close() / ensure_alive()

AccountPort
  list_accounts() → equity, currency, buying_power / margin available

MarketDataPort
  get_bars(symbol_ref | instrument, resolution, n) → list[Bar]
  get_quote(instrument) → Quote

TradingPort
  place(OrderRequest) → OrderAck
  cancel(broker_order_id) → …
  confirm(client_order_id | broker_order_id) → Fill | Reject  # semántica “mai assumere fill”
  list_open_positions() → list[Position]
  close_position(Position, qty?) → OrderAck

OptionsChainPort
  resolve_underlying(symbol_ref) → BrokerInstrument
  list_expiries(underlying, style=monthly|weekly) → …
  find_contract(underlying, expiry, strike, right) → OptionContract
  # opzionale: snapshot_chain(expiry) se il broker lo permette in modo economico

BrokerGateway
  session + account + market + trading + options? + capabilities()
```

`ThrottledClient` diventa un **decorator/policy** generico (`RateLimitedGateway`) parametrizzato per broker (IG: 2.5s; IBKR: limiti diversi).

### 3.4 Executor di dominio (dove vive la logica “longs-first”)

Oggi `CondorExecutor` è pieno di assunzioni IG ma la **policy** è di dominio:

- aprire prima le gambe long (rischio definito)
- non lasciare short nudi
- hold incompleti vs unwind
- audit

TO-BE:

- `DomainMultiLegExecutor` usa `TradingPort` + `capabilities`
- se `atomic_multileg` ∈ capabilities → un solo ordine combo (tipico IBKR / spesso tastytrade)
- altrimenti → sequenza longs-first (path IG attuale)

Le strategie costruiscono solo `list[Leg]` logiche; non chiamano `get_market` IG.

---

## 4. Broker — contratto aperto + prime implementazioni di prova

Il motore non elenca i broker ammessi. Elenca **capability** e **conformance**.
Qualunque vendor (retail, prop, institutional) può entrare se:

1. Espone API sufficientemente affidabili (auth, quote, ordini, posizioni, idealmente catena opzioni).
2. Implementa le porte in `src/broker/<vendor_id>/`.
3. Dichiara un set di `Capability` onesto (es. ha CFD? multi-leg atomico?).
4. Passa `tests/broker/conformance/` per quelle capability.
5. Ha (o avrà) campionamento skew/`broker_id` proprio prima del live opzioni.

Sotto: tre implementazioni usate per **calibrare** il contratto. Non sono un tetto.

### 4.1 IG (adapter di riferimento, già esistente da estrarre)

| Area | Note |
|------|------|
| API | REST Labs IG; DEMO vs LIVE host/chiavi diverse |
| Auth | CST + X-SECURITY-TOKEN |
| CFD | sì — path `bot.py` attuale |
| Opzioni | mensili OTC stile epic; **non** stesso modello di un broker titoli USA |
| Multi-leg | tipicamente **non** atomico → sequenza + throttle |
| Rischio prodotto | conti CFD e opzioni **separati** |
| Rate limit | critico — session persistente obbligatoria |

L’adapter IG è il **golden path**: ogni porta deve avere un test di conformità che IG passa già oggi.

### 4.2 Interactive Brokers (IBKR)

| Area | Note |
|------|------|
| API | TWS API / IB Gateway e/o Client Portal Web API — scegliere **una** stack per adapter v1 e documentarla |
| Auth | sessione TWS/Gateway o OAuth Client Portal |
| Strumenti | actions, options OCC-style, futures; **non** CFD IG-equivalenti 1:1 |
| Multi-leg | BAG/combo orders — mappare su `atomic_multileg` |
| Dati | spesso permesso mercato separato; barre storiche vs live |
| Paper | paper trading account IBKR come analogo della demo IG |
| Attenzione | mapping underlying SPX/SPY/ES vs “US500 CFD” del backtest — **il dominio deve dichiarare quale underlying usa ogni strategia** |

### 4.3 tastytrade

| Area | Note |
|------|------|
| API | REST/streaming tastytrade (ex tastyworks) — account retail opzioni USA |
| Forza | opzioni, spreads, DXLink/quote — allineato al book put/call spread |
| Limite | non sostituisce il conto CFD IG per EDGE #1 senza prodotto equivalente |
| Multi-leg | supporta strutture verticali; verificare atomicità e margine netting |
| Auth | session token / OAuth secondo docs correnti al momento dell’implementazione |

### 4.4 Matrice capability (v1)

| Capability | IG | IBKR | tastytrade |
|------------|----|------|------------|
| CFD cash index tipo US500 | sì | no (servono futures/ETF/CFD altrove) | no |
| Equity/index options | sì (formato IG) | sì | sì |
| Atomic multileg | no (pratico) | sì | da verificare in adapter |
| Native stop on CFD | sì | N/A o diverso | N/A |
| Separate cash accounts CFD vs opt | sì | modello conto diverso | modello conto diverso |

**Implicazione prodotto:** EDGE #1 (CFD) può restare **solo IG** (o un futuro adapter CFD) mentre EDGE #2/#3 migrano prima su IBKR/tastytrade. Il motore deve permettere **broker diversi per account kind**, non un solo broker globale.

---

## 5. Piano di migrazione (fasi, ordine obbligato)

Principio: **nessuna big-bang**. IG resta funzionante a ogni fase. Feature flag `BROKER=ig` default.

### Fase 0 — ADR e confini (1–2 giorni di lavoro concentrato)

**Deliverable**

- Questo documento accettato + issue GitHub.
- ADR breve in `docs/adr/001-broker-ports.md`: porte, tipi, “due conti / due gateway”.
- Inventario file da toccare (checklist sotto §7).

**Exit criteria:** accordo scritto su: SymbolRef, Position IDs, multi-account.

### Fase 1 — Introdurre porte + adapter IG “a facciata” (nessun nuovo broker)

**Lavoro**

1. Creare `src/broker/ports.py`, `types.py`, `factory.py` (`get_gateway(broker_id, account_kind)`).
2. Spostare/wrappare `IGClient` → `src/broker/ig/client.py` + `src/broker/ig/gateway.py` che implementa le porte.
3. `OrderManager`, `RiskManager`, `PositionStore.reconcile`, `DipBuyStrategy` dipendono da **porte**, non da `IGClient` concreto (injection da `bot.py`).
4. Opzioni: `PersistentIGSession` → `IgSessionAdapter`; `ThrottledClient` → rate limiter generico; `SpreadOrchestrator` riceve `OptionsChainPort` + `MarketDataPort`.
5. Tenere alias di compatibilità (`from src.core.ig_client import IGClient`) deprecati per non rompere script.

**Exit criteria**

- `python bot.py --once` e `python scripts/run_spread.py --strat both --live` (plan-only) identici nel comportamento.
- Test unitari con `FakeGateway` (mock porte) per open/confirm/reject/reconcile.
- Zero regressione throttle/session su IG.

### Fase 2 — Instrument registry (simboli logici)

**Lavoro**

1. `config/instruments.yaml` (o Python) che mappa:
   - `US500_CFD` → IG epic `IX.D.SPTRD.IFE.IP`
   - `SPX_OPT` / `SPY_OPT` → catene IBKR/tastytrade / IG monthly code discovery
2. Strategie referenziano solo chiavi logiche (`underlying="US500"` + `vehicle="cfd"|"option"`).
3. Adapter risolve in `BrokerInstrument`.

**Exit criteria:** cambiare epic IG = solo config, non codice strategia.

### Fase 3 — Domain multi-leg executor

**Lavoro**

1. Estrarre da `CondorExecutor` la policy di dominio.
2. Path A: sequential longs-first (IG).
3. Path B: atomic combo (IBKR/tastytrade) dietro capability.
4. Audit log invariato (`logs/condor_audit.jsonl` o rename neutro `trade_audit.jsonl`).

**Exit criteria:** test di policy con fake gateway (incomplete → HOLD/UNWIND; naked → force close).

### Fase 4 — Adapter IBKR (paper first)

**Lavoro**

1. Package `src/broker/ibkr/` (connessione paper, market data, place/cancel, positions).
2. OptionsChainPort su underlying scelto (documentare SPX vs SPY vs MES — decisione prodotto).
3. Paper: plan-only mirror di `run_spread` + poi arm su paper.
4. Non spezzare sampler skew IG: lo skew IG resta **misura del broker IG**; per IBKR/tastytrade servirà un **sampler parallelo** (stesso CSV schema, colonna `broker_id`) perché lo smile **non è trasferibile** 1:1 tra broker.

**Exit criteria:** un put-spread e un call-spread plan-only su paper IBKR con strike reali; report differenze vs piano IG stesso giorno.

### Fase 5 — Adapter tastytrade (paper/sandbox)

**Lavoro** analogo a Fase 4; priorità alle verticali options (cuore EDGE #2/#3).

**Exit criteria:** stesso test di conformità porte di IBKR.

### Fase 6 — Runtime multi-gateway + prodotto

**Lavoro**

1. Config: `BROKER_CFD=<vendor>`, `BROKER_OPTIONS=<vendor>` (stringhe registry, non enum chiuso nel dominio).
2. Daemon: può campionare skew sul broker opzioni attivo; gate usa colonna `broker_id`.
3. Dashboard: mostra broker per posizione.
4. Documentare limiti per capability (es. EDGE #1 solo dove esiste CFD o veicolo equivalente).
5. Template issue “Nuovo adapter broker X” per estensioni future.

**Exit criteria:** un deploy di staging con CFD su IG e opzioni su secondo broker (paper), plan-only 5 giorni senza errori di sessione.

### Fase 7 — Hardening

- Chaos: disconnect mid-multileg, partial fill, reboot reconcile.
- Contract tests CI: ogni adapter deve passare la suite `tests/broker/conformance/`.
- Rimuovere import diretti residui di `IGClient` dal dominio.

---

## 6. Strategia di test (obbligatoria)

| Livello | Cosa |
|---------|------|
| Unit | FakeGateway: reject, retry, idempotenza, reconcile orphan |
| Conformance | stessa batteria su IG demo, IBKR paper, tastytrade paper |
| Golden | snapshot di un `plan_spread` (strike/σ) con quote registrate |
| Replay | registrare risposte market data → riprodurre piano offline |
| Smoke | script `scripts/test_broker_gateway.py --broker ig\|ibkr\|tastytrade` |

Divieto: merge di un adapter senza conformance minima (session + quote + list positions + dry-run order path).

---

## 7. Checklist file (migrazione meccanica)

### Da introdurre

```text
docs/PIANO-ASTRAZIONE-BROKER.md          (questo file)
docs/adr/001-broker-ports.md             (Fase 0)
src/broker/__init__.py
src/broker/types.py
src/broker/ports.py
src/broker/factory.py
src/broker/rate_limit.py
src/broker/ig/...
src/broker/ibkr/...
src/broker/tastytrade/...
tests/broker/conformance/...
config/instruments.yaml                  (o equivalente)
```

### Da rifattorizzare (dipendenza → porte)

```text
bot.py
src/core/order_manager.py
src/core/risk_manager.py
src/core/position_store.py
src/strategies/dip_buy.py
src/options/executor.py
src/options/spread_orchestrator.py
src/options/orchestrator.py
src/options/session.py
src/options/throttle.py
src/options/chain_resolver.py            → spezzare: logica strike vs IG epic codec
scripts/run_spread.py
scripts/sampler_daemon.py
scripts/sample_skew_us500.py             → broker_id nello schema CSV
```

### Da non “astrarre via” troppo presto

- Backtest offline (`scripts/*_us500.py`) — restano su CSV; non dipendono dal broker live.
- Smile modello nei backtest — resta; il gate skew resta **per-broker**.

---

## 8. Rischi e mitigações

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| Astrazione prematura rompe IG live | Alto | Fase 1 facciata + test smoke ogni PR |
| Smile/gate misurato su IG usato su altro broker | Alto (edge falso) | CSV skew con `broker_id`; vietare reuse cross-broker |
| EDGE #1 non esiste fuori IG | Medio | Capability `cfd`; UI/config chiara |
| Differenze margine/netting | Alto | check margine pre-trade per adapter; pilot piccolo |
| Due API IBKR (TWS vs Client Portal) | Medio | ADR sceglie una sola per v1 |
| Rate limit / market data permissions IBKR | Medio | capability + fail soft in plan-only |
| Scope creep “implementare 20 broker subito” | Alto | Contratto aperto sì; **implementazioni** una alla volta dopo porte stabili. Nuovi vendor = nuove issue figlie, non gonfiare questa. |

---

## 9. Cosa resta vero del progetto (non si butta)

- Apparato di falsificazione e backtest multi-anno.
- Edge candidati #1/#2/#3 e lista falsificati.
- Principi: plan-only default, `--arm` + ok esplicito, guardia modula mai blocca, hold-to-expiry put, rischio definito.
- Sampler e gate: restano, ma **per broker di esecuzione opzioni**.

L’astrazione serve a **non riscrivere questo cuore** quando cambia l’intermediario.

---

## 10. Criteri di “fatto” (Definition of Done del programma)

1. Strategie e orchestrazione dominio **senza** import di SDK/vendor.
2. Factory/registry che carica **qualsiasi** adapter registrato (`BROKER_*=<vendor_id>`), non un enum chiuso hardcoded nel dominio.
3. Contratto + conformance documentati; verde su IG + **almeno un** secondo broker paper (IBKR o tastytrade o altro scelto).
4. Guida “come aggiungere un broker” (checklist package + test) nel piano o ADR.
5. Documentazione aggiornata: ARCHITETTURA-BOT punta qui; STATO aggiornato quando un adapter è paper-ready.
6. Nessuna apertura live su broker nuovo senza lo stesso schema di arm + pilot + skew/gate di **quel** broker.

---

## 11. Ordine di lavoro suggerito (sprint-like)

1. Fase 0 ADR  
2. Fase 1 IG-behind-ports (priorità assoluta: zero regressione)  
3. Fase 2 instrument registry  
4. Fase 3 domain executor  
5. Fase 4 **oppure** 5 (scegliere il primo broker opzioni non-IG in base a: qualità API paper, costo dati, sottostante allineato al book)  
6. Fase 6 multi-gateway  
7. Fase 7 hardening  

Stima grezza (indicativa, da ricalibrare): Fase 1–3 = fondamento motore; Fase 4–5 = un adapter ciascuno non banale; non parallelizzare due adapter nuovi prima che le porte siano stabili.

---

## 12. Riferimenti esterni (da rileggere al momento dell’implementazione)

- IG REST: https://labs.ig.com/rest-trading-api-reference  
- Interactive Brokers API center: https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/  
- tastytrade API / developer docs: documentazione ufficiale tastytrade vigente alla data di implementazione  

I link e i dettagli auth cambiano: l’ADR di Fase 0 deve **congelare versioni** scelte.

---

*Fine piano. Implementazione solo tramite issue GitHub e PR che referenziano le fasi (es. `Refs #N` / `Implements Fase 1`).*
