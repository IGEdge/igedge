# Arm per-strategia (opzioni) — come funziona

> Aggiornato: **19 luglio 2026**.  
> Conti **CFD** e **opzioni** sono separati: qui solo **opzioni**.  
> Diario completo dei fix del giorno: [FIXLOG-2026-07-19.md](FIXLOG-2026-07-19.md) · Indice: [INDICE.md](INDICE.md)

## In una frase

Di default **non apre nulla**. Per aprire serve un interruttore globale **e**
una lista di strategie autorizzate (config). Il demone **non** hardcoda “apri la put”.

---

## Cosa è stato fatto (codice)

| File | Ruolo |
|------|--------|
| `src/options/arming.py` | Allowlist: chi può aprire |
| `scripts/run_spread.py` | Gate + arma **per strategia** |
| `scripts/sampler_daemon.py` | Se i flag demone sono on, passa `--arm` — **non** sceglie la strategia |
| `.env.example` | `OPTIONS_DAEMON_*`, `OPTIONS_ARMED_STRATEGIES` |
| `scripts/test_arming_policy.py` | Test della sola policy (senza IG) |

Issue di tracking: [#15](https://github.com/IGEdge/igedge/issues/15) (meccanismo ok; attivazione in prod ancora aperta).

---

## Regole del gate (importante)

| Conto | Come si arma |
|-------|----------------|
| **DEMO** (senza `--live`) | Basta `--arm`. Usa credenziali `IG_*` / sessione demo. |
| **LIVE** (`--live`) | Serve `--arm` **e** `--i-understand-live-risk`. Usa `IG_LIVE_*`. |

Allowlist:

- Env: `OPTIONS_ARMED_STRATEGIES=putspread` (csv, es. `putspread,callspread`)
- Oppure CLI: `--arm-strategies putspread`
- `--strat putspread --arm` senza lista → arma **solo** quella (implicito)
- `--strat both --arm` senza lista → **plan-only totale** (nessuno apre)

Demone (Pi), default **spento** (nessuna regressione sul giro attuale):

```env
OPTIONS_DAEMON_ARM=false
OPTIONS_DAEMON_I_UNDERSTAND_LIVE_RISK=false
OPTIONS_ARMED_STRATEGIES=
```

Per far aprire solo la put dal cron (quando Antonio decide):

```env
OPTIONS_DAEMON_ARM=true
OPTIONS_DAEMON_I_UNDERSTAND_LIVE_RISK=true
OPTIONS_ARMED_STRATEGIES=putspread
```

Poi restart del container. Per spegnere subito: `OPTIONS_DAEMON_ARM=false` + restart.

---

## Regressioni? (path reale)

| Situazione | Effetto |
|------------|---------|
| Demone con flag default `false` | Come prima: **solo plan-only**, nessun ordine |
| Pi non ancora syncato | Continua il codice vecchio del 15 lug → **nessun cambiamento in prod Pi** |
| LIVE + `--arm` senza `--i-understand-live-risk` | Plan-only (come prima) |
| LIVE + allowlist solo `putspread` | Call resta plan-only; put può aprire se segnale+margine OK |
| DEMO + `--arm` | **Novità voluta:** può tentare ordini sul DEMO (prima era bloccato senza `--live`) |

Test apertura DEMO fatto il **19 lug 2026** (domenica):

```bash
python scripts/run_spread.py --strat putspread --arm --vix 22 --vix10max 30
```

- Conto DEMO opzioni, put **ARMATO**, piano+margine OK  
- Apertura **abortita** con errore chiaro IG: gambe `EDITS_ONLY` (mercato chiuso)  
- `opened=False`, stato `ABORTED`  
- **Nessun uso del conto CFD / dip-buy**

Test policy (senza IG): `python scripts/test_arming_policy.py`

---

## Comandi utili

```bash
# Solo leggere il piano (LIVE read-only, nessun ordine)
python scripts/run_spread.py --strat both --live

# Pilot LIVE solo put (quando autorizzato)
python scripts/run_spread.py --strat putspread --live --arm --i-understand-live-risk

# both ma apre solo put (LIVE)
python scripts/run_spread.py --strat both --live --arm --i-understand-live-risk --arm-strategies putspread
```

Flag test segnale: `--vix`, `--vix10max` (non usare in produzione se non per prove).

---

## Cosa NON è ancora fatto

Vedi checklist in issue **#15**: sync Pi, accensione flag solo quando deciso, smoke demone arm OFF, eventuale prima apertura reale, runbook già in parte qui sopra.
