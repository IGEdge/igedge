#!/usr/bin/env bash
# Scarica dal Raspberry i dati del sampler dentro il repo locale.
# Uso:  ./pull-data.sh                     (default pi@raspberrypi.local, ~/ig-trading)
#       PI=pi@192.168.1.42 ./pull-data.sh
set -e
PI="${PI:-pi@raspberrypi.local}"
PIDIR="${PIDIR:-ig-trading}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "Scarico da $PI:$PIDIR ..."
scp "$PI:$PIDIR/data/research/skew_samples.csv" "$ROOT/data/research/skew_samples.csv"
scp "$PI:$PIDIR/logs/sampler.log" "$ROOT/logs/sampler-pi.log" || true

echo
echo "OK. Verdetto del gate:"
python "$ROOT/scripts/sample_skew_us500.py" --report
