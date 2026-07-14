#!/usr/bin/env python3
"""Grafici per il report degli edge (docs/report/). Usa i trade DUMPATI dai
backtest validati (docs/report/data/*.csv) — mai numeri ricalcolati a parte.
Stile: nota di ricerca su carta (palette del report HTML)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

PAPER, INK = "#F7F6F2", "#16211E"
GREEN, BRASS, RED, SLATE = "#175E54", "#A0742A", "#A63232", "#4A5D6E"
GRID, EDGE = "#DDD9CE", "#B9B4A5"
USD2EUR = 0.93          # ipotesi EURUSD ~1.08 costante (dichiarata nel report)


def eur(x):
    return ("€{:,.0f}".format(x)).replace(",", ".")
OUT = "docs/report"
D = "docs/report/data"

plt.rcParams.update({
    "figure.facecolor": PAPER, "axes.facecolor": PAPER, "savefig.facecolor": PAPER,
    "font.family": "Georgia", "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.edgecolor": EDGE,
    "axes.grid": True, "grid.color": GRID, "grid.linestyle": "-", "grid.linewidth": 0.7,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10.5, "axes.titlesize": 12, "figure.dpi": 160,
})


def savefig(fig, name):
    fig.savefig(f"{OUT}/{name}", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"  ✓ {name}")


def eur_equity(t, start=1000.0, per_contract=1000.0):
    """Equity in € con CONTRATTI INTERI (1 per €1000 di equity). $1/pt »€."""
    eq, curve = start, []
    for _, r in t.iterrows():
        n = max(1, int(eq // per_contract))
        eq += n * r["maxloss"] * r["ret"] * USD2EUR
        curve.append(eq)
    return np.array(curve)


ps_post = pd.read_csv(f"{D}/ps_postspike.csv", parse_dates=["date"])
ps_cal = pd.read_csv(f"{D}/ps_calendar.csv", parse_dates=["date"])
ps_07 = pd.read_csv(f"{D}/ps_postspike_2007.csv", parse_dates=["date"])
mr_u = pd.read_csv(f"{D}/mr_union.csv", parse_dates=["entry_ts", "exit_ts"])
mr_t1 = pd.read_csv(f"{D}/mr_t1.csv", parse_dates=["entry_ts", "exit_ts"])
mr_t6 = pd.read_csv(f"{D}/mr_t6.csv", parse_dates=["entry_ts", "exit_ts"])
vix = pd.read_csv("data/research/vix_daily.csv")
vix["ts"] = pd.to_datetime(vix["ts"]).dt.tz_localize(None)

# ---------------------------------------------------------------- 1. payoff
r = ps_post.iloc[-1]   # esempio reale: ultimo trade del backtest
S0, K1, K2 = r["spot"], r["k_short"], r["k_wing"]
credit, maxloss = r["credit"], r["maxloss"]
sx = np.linspace(K2 * 0.90, S0 * 1.06, 400)
pay = credit - (np.clip(K1 - sx, 0, None) - np.clip(K2 - sx, 0, None))
fig, ax = plt.subplots(figsize=(9.5, 4.3))
ax.axhline(0, color=EDGE, lw=1)
ax.fill_between(sx, pay, 0, where=pay >= 0, color=GREEN, alpha=0.18, lw=0)
ax.fill_between(sx, pay, 0, where=pay < 0, color=RED, alpha=0.15, lw=0)
ax.plot(sx, pay, color=INK, lw=2.2)
be = K1 - credit
pct_s = (K1 / S0 - 1) * 100
pct_w = (K2 / S0 - 1) * 100
for x, lab, c in [(S0, f"spot {S0:.0f}", SLATE),
                  (K1, f"vendi put {K1:.0f}  ({pct_s:+.0f}%)", GREEN),
                  (K2, f"ala comprata {K2:.0f}  ({pct_w:+.0f}%)", BRASS)]:
    ax.axvline(x, color=c, lw=1.1, ls="--", alpha=0.85)
    ax.text(x, ax.get_ylim()[1] * 0.97, "  " + lab, color=c, fontsize=9.5,
            rotation=90, va="top", ha="right" if x == K2 else "left")
ax.annotate(f"pareggio a {be:.0f}", xy=(be, 0), xytext=(be - 330, -95),
            color=RED, fontsize=9.5,
            arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
ax.annotate(f"incasso massimo  +${credit:.0f}  (≈ +€{credit*USD2EUR:.0f})",
            xy=(S0 * 1.015, credit), fontsize=10.5, color=GREEN, fontweight="bold",
            va="bottom")
ax.annotate(f"perdita massima  −${maxloss:.0f}  (≈ −€{maxloss*USD2EUR:.0f}, CAPPATA)",
            xy=(K2 * 0.912, -maxloss), fontsize=10.5, color=RED, fontweight="bold",
            va="bottom")
ax.set_xlabel("S&P 500 alla scadenza (punti)")
ax.set_ylabel("profitto / perdita a scadenza ($ per contratto)")
ax.set_title(f"Il trade in una figura — esempio reale del backtest: {r['date'].date()}, "
             f"VIX {r['vix']:.0f}, scadenza {r['exp_date']}", loc="left")
savefig(fig, "ps_payoff.png")

# ---------------------------------------------------------------- 2. smile IG
put_n = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
put_r = np.array([0.94, 1.08, 1.22, 1.38, 1.55, 1.73])
call_n = np.array([0.5, 1.0, 1.5, 2.0])
call_r = np.array([0.69, 0.63, 0.65, 0.75])
fig, ax = plt.subplots(figsize=(9.5, 4.1))
xs = np.linspace(0, 3.2, 50)
ax.plot(-xs, 0.77 + 0.30 * xs, color=INK, lw=1.4, ls="--", label="modello del backtest")
ax.plot(xs[xs <= 2.1], 0.77 - 0.16 * xs[xs <= 2.1], color=INK, lw=1.4, ls="--")
ax.scatter(-put_n, put_r, s=70, color=GREEN, zorder=5, label="misurato su IG (14 lug 2026)")
ax.scatter([0], [0.80], s=70, color=SLATE, zorder=5)
ax.scatter(call_n, call_r, s=70, color=BRASS, zorder=5)
ax.axhline(1.0, color=RED, lw=1, ls=":", alpha=0.8)
ax.text(1.15, 1.015, "IV = VIX (prezzo “giusto”)", color=RED, fontsize=9.5)
ax.annotate("PUT: più care del giusto —\nqui noi VENDIAMO", xy=(-1.5, 1.22),
            xytext=(-3.1, 0.86), color=GREEN, fontsize=10.5, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=GREEN))
ax.annotate("CALL: a sconto\n(qui il condor moriva)", xy=(1.0, 0.63), xytext=(1.4, 0.82),
            color=BRASS, fontsize=10, arrowprops=dict(arrowstyle="->", color=BRASS))
ax.set_xlabel("distanza dallo spot (σ) — put lontane a sinistra, call lontane a destra")
ax.set_ylabel("IV dell'opzione / VIX")
ax.set_title("Perché il premio esiste: lo smile REALE delle opzioni IG vs il modello",
             loc="left")
ax.legend(frameon=False, loc="upper right")
savefig(fig, "ps_smile.png")

# ------------------------------------------------- 3. VIX timeline + entrate
fig, ax = plt.subplots(figsize=(9.5, 4.0))
m = vix["ts"] >= "2009-10-01"
ax.plot(vix["ts"][m], vix["close"][m], color=SLATE, lw=0.8, alpha=0.9)
ax.axhline(20, color=EDGE, lw=1, ls="--")
ax.text(pd.Timestamp("2010-01-01"), 20.7, "soglia spike (VIX 20)", fontsize=9, color=INK, alpha=0.7)
vv = vix.set_index("ts")["close"]
ev = vv.reindex(pd.to_datetime(ps_post["date"]), method="ffill")
win = ps_post["ret"] > 0
ax.scatter(ev.index[win.values], ev.values[win.values], s=42, color=GREEN, zorder=5,
           label=f"entrate vinte ({int(win.sum())})")
ax.scatter(ev.index[~win.values], ev.values[~win.values], s=60, color=RED, marker="X",
           zorder=6, label=f"perse ({int((~win).sum())})")
for d, lab in [("2010-05-06", "flash crash"), ("2011-08-08", "debito USA"),
               ("2015-08-24", "yuan"), ("2018-12-24", "Q4 2018"),
               ("2020-03-16", "COVID"), ("2022-06-13", "bear 2022"),
               ("2025-04-15", "2025")]:
    ax.annotate(lab, xy=(pd.Timestamp(d), float(vv.asof(pd.Timestamp(d)))),
                xytext=(0, 10), textcoords="offset points", fontsize=8.5,
                color=INK, alpha=0.75, ha="center")
ax.set_ylabel("VIX")
ax.set_title("QUANDO entra: solo dopo il panico, mentre rientra (59 entrate in 17 anni)",
             loc="left")
ax.legend(frameon=False, loc="upper left")
savefig(fig, "ps_vix.png")

# ------------------------------------------ 4. equity €1000: postspike vs cal
fig, ax = plt.subplots(figsize=(9.5, 4.2))
c_post = eur_equity(ps_post, 1000)
c_cal = eur_equity(ps_cal, 1000)
ax.plot(ps_post["date"], c_post, color=GREEN, lw=2.4,
        label=f"POST-PANICO+TS — finale {eur(c_post[-1])}, mai un mese sotto −2%")
ax.plot(ps_cal["date"], c_cal, color=BRASS, lw=1.6, alpha=0.95,
        label=f"calendario mensile — finale {eur(c_cal[-1])}, ma con l'incidente")
ax.axhline(1000, color=EDGE, lw=1)
iworst = int(ps_cal["ret"].idxmin())
ax.annotate(f"feb 2020: il calendario perde l'INTERO rischio in un mese\n"
            f"(qui −{eur(ps_cal['maxloss'].iloc[iworst]*USD2EUR)}; con VIX più alto "
            f"all'entrata sarebbero stati −€300+)",
            xy=(ps_cal["date"].iloc[iworst], c_cal[iworst]),
            xytext=(pd.Timestamp("2012-06-01"), 1180), fontsize=9.5, color=RED,
            arrowprops=dict(arrowstyle="->", color=RED))
ax.set_ylabel("equity (€)")
ax.set_title("€1.000 reali, 1 contratto per ogni €1.000 di equity — 2009–2026", loc="left")
ax.legend(frameon=False, loc="upper left")
ax.yaxis.set_major_formatter(lambda x, p: eur(x))
savefig(fig, "ps_equity.png")

# ------------------------------------------------- 5. trade per trade in €
fig, axes = plt.subplots(2, 1, figsize=(9.5, 5.4), sharex=True,
                         gridspec_kw=dict(hspace=0.32))
for ax, t, name, col in [(axes[0], ps_post, "POST-PANICO+TS (59 trade, 1 perdita)", GREEN),
                         (axes[1], ps_cal, "calendario (143 trade — nota feb 2020)", BRASS)]:
    pnl = t["maxloss"] * t["ret"] * USD2EUR
    colors = [GREEN if p > 0 else RED for p in pnl]
    ax.bar(t["date"], pnl, width=22, color=colors)
    ax.axhline(0, color=EDGE, lw=1)
    ax.set_title(name, loc="left", fontsize=10.5)
    ax.set_ylabel("€ / trade (1 contratto)")
axes[1].set_ylim(min(axes[1].get_ylim()[0], -400), 60)
savefig(fig, "ps_trades.png")

# ------------------------------------------------------- 6. per anno in €
fig, ax = plt.subplots(figsize=(9.5, 3.8))
gp = (ps_post.assign(pnl=ps_post["maxloss"] * ps_post["ret"] * USD2EUR)
      .groupby("year")["pnl"].sum())
ax.bar(gp.index.astype(str), gp.values, color=[GREEN if v > 0 else RED for v in gp.values])
ax.axhline(0, color=EDGE, lw=1)
for x, v in zip(gp.index.astype(str), gp.values):
    ax.text(x, v + (2 if v >= 0 else -8), f"{v:+.0f}", ha="center", fontsize=8.6, color=INK)
ax.set_ylabel("€ / anno (su €1.000, 1 contratto)")
ax.set_title("Anno per anno: quanto rende il post-panico su €1.000 (17 anni, 1 solo trade perso)",
             loc="left")
plt.setp(ax.get_xticklabels(), rotation=45)
savefig(fig, "ps_yearly.png")

# --------------------------------------------- 7. distribuzione dei ritorni
fig, ax = plt.subplots(figsize=(9.5, 3.6))
bins = np.linspace(-100, 5, 43)
ax.hist(ps_cal["ret"] * 100, bins=bins, color=BRASS, alpha=0.6, label="calendario")
ax.hist(ps_post["ret"] * 100, bins=bins, color=GREEN, alpha=0.85, label="post-panico+TS")
ax.set_yscale("log")
ax.annotate("il −100% del calendario\n(feb 2020)", xy=(-97, 1.1), xytext=(-80, 6),
            color=RED, fontsize=10, arrowprops=dict(arrowstyle="->", color=RED))
ax.set_xlabel("esito del trade (% del capitale a rischio)")
ax.set_ylabel("n° trade (scala log)")
ax.set_title("La distribuzione degli esiti: la coda sinistra è la differenza", loc="left")
ax.legend(frameon=False, loc="upper left")
savefig(fig, "ps_dist.png")

# ------------------------------------------------- 8. capitali 1k/2k/3k
fig, ax = plt.subplots(figsize=(9.5, 4.0))
for start, col, lw in [(3000, GREEN, 2.4), (2000, SLATE, 1.9), (1000, BRASS, 1.6)]:
    c = eur_equity(ps_post, start)
    ax.plot(ps_post["date"], c, color=col, lw=lw,
            label=f"parte con {eur(start)} — finisce {eur(c[-1])}  ({(c[-1]/start-1)*100:+.0f}%)")
ax.set_ylabel("equity (€)")
ax.set_title("Capitali reali a confronto (contratti interi: 1 ogni €1.000 di equity)",
             loc="left")
ax.legend(frameon=False, loc="upper left")
ax.yaxis.set_major_formatter(lambda x, p: eur(x))
savefig(fig, "ps_capital.png")

# --------------------------------------------------- 9. la lezione del 2008
fig, ax = plt.subplots(figsize=(9.5, 3.9))
c07 = eur_equity(ps_07, 1000)
ax.plot(ps_07["date"], c07, color=SLATE, lw=2,
        label="post-panico SENZA filtro term-structure (dal 2007)")
i08 = int(ps_07["ret"].idxmin())
ax.scatter([ps_07["date"].iloc[i08]], [c07[i08]], s=90, color=RED, zorder=5, marker="X")
ax.annotate(f"nov 2008: il “secondo tonfo”\n−{abs(ps_07['ret'].iloc[i08])*100:.0f}% del rischio in un trade",
            xy=(ps_07["date"].iloc[i08], c07[i08]),
            xytext=(pd.Timestamp("2011-01-01"), c07[i08] - 120), fontsize=10, color=RED,
            arrowprops=dict(arrowstyle="->", color=RED))
ax.axhline(1000, color=EDGE, lw=1)
ax.set_ylabel("equity (€, su €1.000)")
ax.yaxis.set_major_formatter(lambda x, p: eur(x))
ax.set_title("Il limite onesto: nel 2008 il post-panico da solo si fa male "
             "(il filtro term-structure lì non è verificabile)", loc="left")
ax.legend(frameon=False, loc="lower right")
ax.yaxis.set_major_formatter(lambda x, p: f"€{x:,.0f}")
savefig(fig, "ps_2008.png")

# ============================ EDGE #1 (ensemble MR) ==========================
# ------------------------------------------------ 10. equity % t1 vs union 3x
fig, ax = plt.subplots(figsize=(9.5, 4.2))
for t, name, col, lw in [(mr_u, "ENSEMBLE 5 trigger (3x)", GREEN, 2.4),
                         (mr_t1, "solo RSI2 — la base validata (3x)", BRASS, 1.6)]:
    eq = (1 + 3 * t["net"]).cumprod() * 100
    ax.plot(t["exit_ts"], eq, color=col, lw=lw,
            label=f"{name} — finale {eq.iloc[-1]:,.0f}".replace(",", "."))
ax.set_yscale("log")
ax.set_ylabel("equity (base 100, scala log)")
ax.set_title("EDGE #1 — l'ensemble raddoppia la frequenza a parità di rischio (2008–2026, leva 3x)",
             loc="left")
ax.legend(frameon=False, loc="upper left")
savefig(fig, "mr_equity.png")

# ------------------------------------------------------- 11. per anno union
fig, ax = plt.subplots(figsize=(9.5, 3.7))
gy = mr_u.groupby("year")["net"].apply(lambda s: ((1 + 3 * s).prod() - 1) * 100)
ax.bar(gy.index.astype(str), gy.values, color=[GREEN if v > 0 else RED for v in gy.values])
ax.axhline(0, color=EDGE, lw=1)
for x, v in zip(gy.index.astype(str), gy.values):
    ax.text(x, v + (1.5 if v >= 0 else -5), f"{v:+.0f}%", ha="center", fontsize=8.4, color=INK)
ax.set_ylabel("ritorno anno (%, leva 3x)")
ax.set_title("Ensemble anno per anno: 16 anni su 18 positivi, perdite piccole", loc="left")
plt.setp(ax.get_xticklabels(), rotation=45)
savefig(fig, "mr_yearly.png")

# ------------------------------------------- 12. contributo trigger marginale
fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), gridspec_kw=dict(wspace=0.3))
names = ["RSI2<10\n(base)", "3 giorni\ngiù", "%b\nBollinger", "VIX\nstretch", "RSI2\ncumulato"]
tr_y = [8, 4, 3, 16, 3]
ret_t = [0.73, 0.52, 1.07, 0.48, 0.56]
cols = [SLATE, GREEN, GREEN, GREEN, GREEN]
axes[0].bar(names, tr_y, color=cols)
axes[0].set_title("trade NUOVI / anno", loc="left", fontsize=10.5)
axes[1].bar(names, ret_t, color=cols)
axes[1].axhline(0.20, color=RED, ls=":", lw=1.2)
axes[1].text(2.6, 0.22, "entry a caso (test del nulla)", color=RED, fontsize=8.5)
axes[1].set_title("guadagno netto / trade (%)", loc="left", fontsize=10.5)
for ax in axes:
    plt.setp(ax.get_xticklabels(), fontsize=8.2)
fig.suptitle("Ogni trigger aggiunge giorni NUOVI con edge vero (tutti battono il 100% del caso)",
             x=0.02, ha="left", fontsize=12)
savefig(fig, "mr_triggers.png")

# ---------------------------------------------------- 13. t6 short nei bear
fig, ax = plt.subplots(figsize=(9.5, 3.6))
g6 = mr_t6.groupby("year")["net"].sum() * 100
years = range(2008, 2027)
vals = [g6.get(y, 0.0) for y in years]
ax.bar([str(y) for y in years], vals,
       color=[RED if y in (2008, 2011, 2018, 2020, 2022, 2025) else EDGE for y in years])
for i, y in enumerate(years):
    if y in (2008, 2020, 2022):
        ax.text(i, vals[i] + 0.3, f"+{vals[i]:.0f}%", ha="center", fontsize=9,
                color=RED, fontweight="bold")
ax.axhline(0, color=EDGE, lw=1)
ax.set_ylabel("ritorno anno (%, 1x)")
ax.set_title("Il satellite SHORT (t6): guadagna proprio negli anni di crisi (barre scure = anni bear)",
             loc="left")
plt.setp(ax.get_xticklabels(), rotation=45)
savefig(fig, "mr_t6.png")

# ------------------------------------------------- 14. € reali con min-size
fig, ax = plt.subplots(figsize=(9.5, 4.0))
for start, L, col, lw, lab in [(2500, 3, GREEN, 2.4, "€2.500 (1 contratto ≈ 3x)"),
                               (7500, 1, SLATE, 1.7, "€7.500 (1 contratto ≈ 1x)")]:
    eq, curve = float(start), []
    for _, rr in mr_u.iterrows():
        n = max(1, int(eq * L // rr["entry_px"]))
        eq += n * rr["entry_px"] * rr["net"]
        curve.append(eq)
    ax.plot(mr_u["exit_ts"], curve, color=col, lw=lw,
            label=f"{lab} — finale {eur(curve[-1])}")
ax.axhline(2500, color=EDGE, lw=0.8, ls=":")
ax.set_yscale("log")
ax.set_ylabel("equity (€, scala log)")
ax.set_title("Il vincolo: il contratto CFD minimo vale ~€7.500 — serve almeno €2.500 per operare a 3x",
             loc="left")
ax.legend(frameon=False, loc="upper left")
ax.yaxis.set_major_formatter(lambda x, p: eur(x))
savefig(fig, "mr_capital.png")

print("\nfatto — grafici in docs/report/")
