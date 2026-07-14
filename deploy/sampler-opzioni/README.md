# Sampler opzioni sul Raspberry — istruzioni

Container autonomo che ogni giorno di borsa, **alle 16:30 italiane** (10:30 di
New York, mercato USA aperto), fa 3 cose e va a dormire:

1. **Aggiorna VIX e VIX3M** dal CBOE (nessuna chiamata a IG);
2. **Campiona lo SKEW reale di IG** (~14 chiamate lente, read-only) →
   aggiunge una riga a `data/research/skew_samples.csv`.
   **È il gate che decide se gli edge #2 e #3 vanno live**;
3. **Controlla i segnali** dei due edge (`run_spread --strat both`, PLAN-ONLY):
   nel log vedi se OGGI il sistema avrebbe venduto un put-spread (post-panico)
   o comprato una call (uptrend) e a che prezzi reali.

**⚠️ Non apre MAI posizioni.** È tutto read-only: l'apertura vera richiede il
comando manuale con `--arm --i-understand-live-risk`.

---

## 1. Avvio sul Raspberry (una volta sola)

Prerequisito: il repo è già sul Pi (come per il bot, vedi `docs/DEPLOY.md`).

```bash
cd ~/ig-trading
git pull

# il .env del Pi deve avere ANCHE le chiavi del conto REALE opzioni:
nano .env      # aggiungi/verifica:
               #   IG_LIVE_API_KEY=...
               #   IG_LIVE_IDENTIFIER=...
               #   IG_LIVE_PASSWORD=...
               #   IG_LIVE_ACCOUNT_ID=TVYYM

cd deploy/sampler-opzioni
docker compose up -d --build      # build (~5-10 min la prima volta su Pi) + avvio
```

## 2. Controllare che vada

```bash
docker compose ps                  # deve dire healthy (dopo ~1 min)
docker compose logs -f             # il diario: prossima esecuzione, job, esiti
tail -20 ../../logs/sampler.log    # stesso diario, su file persistente
```

Test immediato senza aspettare le 16:30 (esegue i 3 job ORA ed esce):
```bash
docker compose run --rm sampler python scripts/sampler_daemon.py --once
```

## 3. Tirare giù i dati sul PC (per l'analisi)

Dal PC Windows, nella cartella del repo:
```
deploy\sampler-opzioni\pull-data.bat            # usa pi@raspberrypi.local
set PI=pi@192.168.1.42 && deploy\sampler-opzioni\pull-data.bat   # host custom
```
Scarica `skew_samples.csv` + `sampler.log` dal Pi dentro il repo locale.
Poi il verdetto del gate si legge con:
```
python scripts/sample_skew_us500.py --report
```

**⚠️ Da quando il Pi è attivo, NON lanciare più il sampler dal PC**: il Pi è la
fonte unica di `skew_samples.csv` (il pull sovrascrive la copia locale).

## 4. Fermare / aggiornare

```bash
docker compose stop                # pausa (riparte con `start`)
docker compose down                # rimuove il container (dati salvi: bind mount)
git pull && docker compose up -d --build     # aggiornamento codice
```

## Note

- **Sessione IG**: il Pi fa UN login la prima volta e riusa i token
  (`data/ig_session_live.json` suo, separato dal PC). Niente login ripetuti.
- **Festivi USA**: il sampler fallisce le quote → ritenta 3 volte e rinuncia
  fino al giorno dopo (normale, lo vedi nel log).
- **Orario**: cambia `SAMPLER_RUN_AT` nel `docker-compose.yml` se serve
  (sempre a mercato USA aperto: 15:30–22:00 italiane).
- Il gate è chiuso quando `--report` mostra ~10-20 campioni con
  `atm_ratio` medio ≤ 0.82 → a quel punto si decide il pilot (manuale).
