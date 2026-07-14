# IGEdge — bot quant su CFD IG (US500)

Bot di trading quantitativo su **CFD IG**, costruito attorno a **un edge reale e
validato** (mean-reversion "buy-the-dip" su US500). Modulare, con esecuzione
sicura, gestione del rischio, e dashboard con analisi di regime. Deployabile via
Docker su Raspberry Pi.

> **Filosofia: validare prima, costruire dopo.** Ogni strategia passa un apparato
> rigoroso (backtest netto costi + in/out-of-sample + test del nulla) *prima* di
> essere messa live. 6 idee popolari sono state **falsificate** dai dati; 1 ha
> retto. Vedi [docs/EDGES.md](docs/EDGES.md).

---

## L'edge (in una riga)
Long su ipervenduto di breve (`RSI(2)<10`) in uptrend (`close>SMA200`), con
scale-in sui dip più profondi, uscita sul rimbalzo, **intraday** (flat overnight).
WR **86%**, regge out-of-sample, sopravvive ai costi CFD. Dettaglio e numeri:
**[docs/EDGE_BUYTHEDIP.md](docs/EDGE_BUYTHEDIP.md)**.

## Come funziona il bot
```
loop ogni 15 min:
  reconcile con IG  (mai perdere le posizioni)
  → per ogni strategia: calcola segnale → decide (ENTER/ADD/EXIT/HOLD)
  → risk check (kill switch, cap leva) → esegui ordine (conferma il fill)
```

## Avvio rapido (locale)
```bash
pip install -r requirements.txt
cp .env.example .env            # compila IG_API_KEY / IG_IDENTIFIER / IG_PASSWORD
python scripts/test_ig_connection.py     # verifica credenziali demo
python bot.py --once            # un ciclo di prova
python bot.py                   # loop continuo
streamlit run src/monitoring/dashboard.py   # dashboard (localhost:8501)
```

## Deploy Docker (Raspberry Pi)
```bash
docker compose up -d --build    # bot + dashboard (arm64)
./docker-logs.sh
```
Guida completa: **[docs/DEPLOY.md](docs/DEPLOY.md)**.

---

## Struttura
```
IGEdge/
├── bot.py                      entrypoint: loop reconcile → decide → esegui
├── src/
│   ├── core/
│   │   ├── ig_client.py        REST IG: auth, prezzi, esecuzione (open/close/confirm)
│   │   ├── position_store.py   stato SQLite + reconcile (non perdere posizioni)
│   │   ├── risk_manager.py     sizing CFD leva, kill switch, cap esposizione
│   │   └── order_manager.py    conferma fill, retry, idempotenza
│   ├── strategies/
│   │   ├── base_strategy.py    interfaccia
│   │   └── dip_buy.py          EDGE #1 (aggiungerne = 1 modulo + 1 flag .env)
│   ├── data/dukascopy_cache.py cache tick → barre 1m/1h
│   └── monitoring/dashboard.py Streamlit: operativo + analisi regime
├── scripts/                    download dati, backtest, ricerca edge
├── data/research/              dataset US500 (vedi il suo README)
└── docs/                       documentazione completa (sotto)
```

## Documentazione
| Documento | Contenuto |
|---|---|
| [docs/EDGE_BUYTHEDIP.md](docs/EDGE_BUYTHEDIP.md) | L'edge #1: regole, validazione, leva, comandi |
| [docs/EDGE_SHORTVOL.md](docs/EDGE_SHORTVOL.md) | Edge #2 (candidato): short-vol VRP con iron condor su opzioni US500 |
| [docs/EDGES.md](docs/EDGES.md) | Registro edge: validati / falsificati / da indagare |
| [docs/BOT_ARCHITECTURE.md](docs/BOT_ARCHITECTURE.md) | Architettura modulare + checklist sicurezza |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Deploy Docker su Raspberry Pi |
| [docs/IG_CONVERSION.md](docs/IG_CONVERSION.md) | Log del progetto: setup IG, tutti i risultati |
| [data/research/README.md](data/research/README.md) | Dove sono i dati e come rigenerarli |

## Stato
Edge #1 validato e implementato. Bot core (esecuzione + rischio + reconcile +
dashboard) **funzionante end-to-end** su demo. Prossimo: paper trading su demo a
mercato aperto, e backtest delle nuove idee edge ([docs/EDGES.md](docs/EDGES.md)).

## Disclaimer
Software per ricerca e trading del proprio capitale. Il trading con leva comporta
rischio di perdita. I risultati di backtest non garantiscono i risultati futuri.
Contatto: **lantoniotrento@gmail.com**
