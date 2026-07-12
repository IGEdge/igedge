# Deploy — Docker su Raspberry Pi

Il bot e la dashboard girano in due container dallo stesso image (multi-arch
amd64 + arm64). Config: `Dockerfile` + `docker-compose.yml`.

## Prerequisiti (sul Pi)
- Docker + Docker Compose plugin (`docker compose version`).
- Raspberry Pi 64-bit (arm64). Consigliato 2GB+ RAM.

## 1. Prepara la cartella sul Pi
```bash
git clone <repo> ig-trading && cd ig-trading
cp .env.example .env
nano .env                     # compila IG_API_KEY / IG_IDENTIFIER / IG_PASSWORD / IG_ACCOUNT_ID
```
Servono anche:
- **`data/research/us500_daily.csv`** — per l'analisi di regime della dashboard.
  Generalo sul Pi con `python scripts/download_us500_ig.py` (dopo il build puoi
  eseguirlo nel container) oppure copialo dal PC. `positions.db` lo crea il bot.

## 2. Build + avvio
```bash
docker compose up -d --build      # build arm64 + avvia bot + dashboard
docker compose ps                 # stato + healthcheck
./docker-logs.sh                  # log del bot (Ctrl+C esce, il bot resta su)
```

## 3. Persistenza (importante)
`./data`, `./logs`, `./.env` sono **bind mount** del filesystem host: sopravvivono
a `docker compose down` e ai rebuild. In `./data` ci sono `positions.db` (stato
posizioni) e i CSV dei backtest. NON sono volumi gestiti da Docker → `prune` non
li tocca.

## 4. Operazioni
```bash
docker compose restart bot        # riavvia solo il bot
docker compose stop               # ferma tutto (restart: unless-stopped riparte al reboot)
docker compose down               # rimuove i container (dati salvi nei bind mount)
./docker-shell.sh                 # shell nel container bot
docker compose logs -f dashboard  # log dashboard
```

## 5. Dashboard (accesso)
Esposta **solo su `127.0.0.1:8501`** del Pi (per sicurezza). Per accedervi da fuori:
- **Cloudflare Tunnel + Access** (consigliato — la dashboard mostra posizioni/stato);
- oppure SSH tunnel: `ssh -L 8501:localhost:8501 pi@raspberry` → apri `localhost:8501`.

## 6. Salute e riavvio automatico
- `restart: unless-stopped` = i container ripartono da soli dopo crash o reboot.
- Healthcheck bot: vivo se `logs/bot.log` è stato scritto negli ultimi 30 min
  (il loop gira ~ogni 15 min, anche a mercato chiuso decide FLAT e logga).
- Healthcheck dashboard: endpoint `/_stcore/health` di Streamlit.

## 7. Aggiornare
```bash
git pull
docker compose up -d --build      # ricostruisce e riavvia
```

## Note
- Su Linux `truststore` è un no-op (niente proxy che intercetta il TLS): la
  verifica certificati standard funziona.
- `IG_ACC_TYPE=DEMO` per il paper trading; passare a `LIVE` solo dopo settimane
  di demo che confermano il backtest (e con capitale/leva adeguati).
- Fuso orario container: `TZ=Europe/Rome` (per il reset giornaliero del kill switch).
