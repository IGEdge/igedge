"""
Stagionalità mensile dell'S&P 500 — due fonti, in ordine di autorità:

1. TABELLA STORICA CANONICA (1950-2024, ~75 anni): le statistiche PUBBLICHE e
   note (Stock Trader's Almanac e letteratura) — settembre è il peggior mese
   (~45% positivi, media −0.7%), ago/feb/giu piatti, nov/dic/apr i migliori.
   È la fonte PRIMARIA del bias (richiesta esplicita dell'utente: la tabella
   famosa, non ricalcolata sui nostri pochi anni).
2. I NOSTRI dati locali (us500_daily.csv, IG 2007-2026) come CONTROPROVA:
   compaiono nella nota, non decidono il bias.

Zero chiamate esterne. Fattore della guardia soft: un mese storicamente debole
rende la modulazione più prudente, MAI la spegne.
"""
import os
from functools import lru_cache

import pandas as pd

CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "research", "us500_daily.csv")

MESI = ["gen", "feb", "mar", "apr", "mag", "giu",
        "lug", "ago", "set", "ott", "nov", "dic"]

# S&P 500 1950-2024 (price return): (media % mese, % mesi positivi) — valori
# canonici arrotondati dalla statistica pubblica di lungo periodo.
CANONICA = {
    1:  (+1.0, 59), 2: (+0.0, 53), 3: (+1.1, 64), 4: (+1.5, 70),
    5:  (+0.2, 58), 6: (+0.0, 53), 7: (+1.1, 58), 8: (+0.0, 54),
    9:  (-0.7, 45), 10: (+0.8, 60), 11: (+1.7, 68), 12: (+1.4, 73),
}


@lru_cache(maxsize=1)
def monthly_table(csv_path: str = None) -> "pd.DataFrame":
    """Per ogni mese dell'anno: n campioni, % positivi, ritorno medio, peggiore."""
    df = pd.read_csv(csv_path or CSV)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    m = df.set_index("ts")["close"].resample("ME").last().pct_change().dropna()
    g = m.groupby(m.index.month)
    out = pd.DataFrame({
        "n": g.size(),
        "win_rate": (g.apply(lambda s: (s > 0).mean()) * 100).round(0),
        "media_pct": (g.mean() * 100).round(2),
        "peggiore_pct": (g.min() * 100).round(1),
    })
    out.index = [MESI[i - 1] for i in out.index]
    return out


def month_bias(month: int):
    """('debole'|'neutro'|'forte', nota). Il bias lo decide la TABELLA CANONICA
    1950-2024 (regole dichiarate: debole = media <+0.3% E positivi <57%;
    forte = media ≥+1.0% E positivi ≥60%). I dati locali sono solo controprova."""
    media, win = CANONICA[month]
    note = f"canonica 1950-2024: media {media:+.1f}%, positivi {win}%"
    try:
        r = monthly_table().iloc[month - 1]
        note += (f" | nostri dati {int(r['n'])} anni: {r['media_pct']:+.1f}%, "
                 f"positivi {r['win_rate']:.0f}%")
    except Exception:
        pass
    if media < 0.3 and win < 57:
        return "debole", note
    if media >= 1.0 and win >= 60:
        return "forte", note
    return "neutro", note


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout,):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(monthly_table().to_string())
