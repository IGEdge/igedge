#!/usr/bin/env python3
"""Assembla docs/report/report-edges.html: nota di ricerca con i 14 grafici
(base64 inline, file unico portabile) + tabella di esempi reali dai CSV."""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass
import pandas as pd

OUT = "docs/report"
USD2EUR = 0.93


def eur(x, sign=False):
    s = ("{:+,.0f}" if sign else "{:,.0f}").format(x).replace(",", ".")
    return f"€{s}" if not sign else (s[0] + "€" + s[1:])


def img(name):
    with open(f"{OUT}/{name}", "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def fig(name, caption):
    return (f'<figure><img src="{img(name)}" alt="">'
            f"<figcaption>{caption}</figcaption></figure>")


ps = pd.read_csv(f"{OUT}/data/ps_postspike.csv", parse_dates=["date"])
cal = pd.read_csv(f"{OUT}/data/ps_calendar.csv", parse_dates=["date"])
mr = pd.read_csv(f"{OUT}/data/mr_union.csv", parse_dates=["entry_ts"])
t6 = pd.read_csv(f"{OUT}/data/mr_t6.csv")

# --- statistiche (dagli stessi CSV dei grafici) ---
def sim(t, start):
    eq = start
    for _, r in t.iterrows():
        eq += max(1, int(eq // 1000)) * r["maxloss"] * r["ret"] * USD2EUR
    return eq

yrs = (ps["date"].iloc[-1] - ps["date"].iloc[0]).days / 365.25
fin_ps, fin_cal = sim(ps, 1000), sim(cal, 1000)
wr = (ps["ret"] > 0).mean() * 100
risk_med = ps["maxloss"].median() * USD2EUR
worst_cal_eur = (cal["maxloss"] * cal["ret"]).min() * USD2EUR

# --- tabella esempi: un trade per anno-chiave + LA perdita ---
rows = []
loss_i = int(ps["ret"].idxmin())
for y in (2010, 2011, 2015, 2018, 2020, 2025):
    rows.append(ps[ps["year"] == y].iloc[0])
rows.insert(5, ps.iloc[loss_i])          # la perdita (2022) in ordine cronologico
tab = ""
for r in rows:
    pnl = r["maxloss"] * r["ret"] * USD2EUR
    cls = ' class="loss"' if pnl < 0 else ""
    tab += (f"<tr{cls}><td>{r['date'].date()}</td><td>{r['vix']:.0f}</td>"
            f"<td>{r['spot']:.0f}</td>"
            f"<td>{r['k_short']:.0f} <span class='dim'>({(r['k_short']/r['spot']-1)*100:+.0f}%)</span></td>"
            f"<td>{r['k_wing']:.0f} <span class='dim'>({(r['k_wing']/r['spot']-1)*100:+.0f}%)</span></td>"
            f"<td>{eur(r['credit']*USD2EUR)}</td><td>{eur(r['maxloss']*USD2EUR)}</td>"
            f"<td>{r['spx_move']*100:+.1f}%</td><td><b>{eur(pnl, sign=True)}</b></td></tr>")

CSS = """
:root{--paper:#F7F6F2;--ink:#16211E;--green:#175E54;--brass:#A0742A;--red:#A63232;
--slate:#4A5D6E;--edge:#B9B4A5;--grid:#DDD9CE;--dim:#6B7570}
html{background:var(--paper)}
body{margin:0;padding:0;background:var(--paper);color:var(--ink);
font:16px/1.65 Georgia,'Times New Roman',serif}
.wrap{max-width:880px;margin:0 auto;padding:48px 24px 80px}
.eyebrow{font:600 12px/1 'Segoe UI',system-ui,sans-serif;letter-spacing:.22em;
text-transform:uppercase;color:var(--brass)}
h1{font-size:clamp(30px,5vw,44px);line-height:1.12;margin:.35em 0 .3em;
font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.lede{font-size:19px;color:#39443F;max-width:60ch;margin:0 0 6px}
.meta{font:12.5px 'Segoe UI',system-ui,sans-serif;color:var(--dim);margin-top:14px;
padding-top:12px;border-top:1px solid var(--edge)}
h2{font-size:26px;margin:2.6em 0 .2em;letter-spacing:-.01em;text-wrap:balance}
h2 .no{color:var(--brass);font-style:italic;margin-right:.35em}
h3{font-size:18.5px;margin:2.1em 0 .4em}
p{max-width:68ch}
section{border-top:2px solid var(--ink);margin-top:3em;padding-top:.4em}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
gap:1px;background:var(--edge);border:1px solid var(--edge);margin:1.6em 0}
.stat{background:var(--paper);padding:14px 14px 12px}
.stat b{display:block;font:700 24px/1.1 Consolas,'Cascadia Mono',monospace;
letter-spacing:-.02em}
.stat.green b{color:var(--green)} .stat.red b{color:var(--red)}
.stat span{font:11.5px 'Segoe UI',system-ui,sans-serif;color:var(--dim);
letter-spacing:.04em;text-transform:uppercase}
figure{margin:1.8em 0;border:1px solid var(--grid);background:#FDFCFA;padding:10px}
figure img{width:100%;height:auto;display:block}
figcaption{font:13px/1.55 'Segoe UI',system-ui,sans-serif;color:var(--dim);
padding:10px 6px 2px}
.caveat{border-left:4px solid var(--red);background:#F2EAE4;padding:14px 18px;
margin:1.8em 0;font-size:15px}
.caveat b:first-child{color:var(--red)}
.note{border-left:4px solid var(--green);background:#EAEFEA;padding:14px 18px;
margin:1.8em 0;font-size:15px}
.tablewrap{overflow-x:auto;margin:1.6em 0;border:1px solid var(--grid)}
table{border-collapse:collapse;width:100%;font:13.5px/1.5 Consolas,'Cascadia Mono',monospace;
font-variant-numeric:tabular-nums;min-width:720px}
th{font:600 11px 'Segoe UI',system-ui,sans-serif;letter-spacing:.06em;
text-transform:uppercase;color:var(--dim);text-align:right;padding:9px 10px;
border-bottom:2px solid var(--ink);background:#F1EFE9}
th:first-child,td:first-child{text-align:left}
td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--grid)}
tr.loss td{background:#F2E7E3;color:var(--red)}
.dim{color:var(--dim);font-size:12px}
.toc{font:14px 'Segoe UI',system-ui,sans-serif;margin:1.4em 0 0;padding:0;
list-style:none;display:flex;gap:1.6em;flex-wrap:wrap}
.toc a{color:var(--green);text-decoration:none;border-bottom:1px solid var(--edge)}
.cmd{background:#EFEDE6;border:1px solid var(--grid);padding:12px 16px;
font:12.5px/1.7 Consolas,'Cascadia Mono',monospace;overflow-x:auto;margin:1em 0;
white-space:pre}
footer{margin-top:4em;padding-top:1.2em;border-top:2px solid var(--ink);
font:13px 'Segoe UI',system-ui,sans-serif;color:var(--dim)}
a{color:var(--green)}
@media(prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
"""

html = f"""<title>IGEdge — Report grafico degli edge</title>
<style>{CSS}</style>
<div class="wrap">

<header>
  <div class="eyebrow">IGEdge · Nota di ricerca № 1 · 14 luglio 2026</div>
  <h1>Vendere la paura quando rientra</h1>
  <p class="lede">Due strategie validate sui dati 2007–2026, raccontate in grafici
  e in euro veri: il <b>put-spread post-panico</b> (l'edge operativo, parte da
  €1.000) e l'<b>ensemble compra-il-dip</b> (in riserva, serve più capitale).</p>
  <ul class="toc">
    <li><a href="#edge2">§1 L'edge operativo (opzioni)</a></li>
    <li><a href="#edge1">§2 L'edge in riserva (CFD)</a></li>
    <li><a href="#metodo">§3 Metodo, ipotesi, limiti</a></li>
  </ul>
  <div class="meta">Backtest netti dei costi reali IG · pricing con lo smile
  misurato sui prezzi veri · cambio assunto EUR/USD 1,08 · niente qui è un
  consiglio d'investimento: è il diario di ricerca del progetto.</div>
</header>

<section id="edge2">
<h2><span class="no">§1</span>L'edge operativo — vendere put lontane, solo dopo il panico</h2>

<p><b>L'idea in una frase:</b> le assicurazioni contro i crolli (le put) sono
<i>sistematicamente pagate troppo</i>; noi le vendiamo con la rete di sicurezza
(un'ala comprata più in basso: perdita massima nota in anticipo), e <b>solo nei
giorni in cui il panico c'è già stato e sta rientrando</b> — mai nella calma
piatta, mai nella tempesta in corso.</p>

<div class="stats">
  <div class="stat green"><b>{len(ps)}</b><span>trade in {yrs:.0f} anni</span></div>
  <div class="stat green"><b>{wr:.0f}%</b><span>trade vinti</span></div>
  <div class="stat red"><b>1</b><span>perdita (−1%) su 59</span></div>
  <div class="stat"><b>~4/anno</b><span>frequenza</span></div>
  <div class="stat"><b>{eur(risk_med)}</b><span>rischio mediano/contratto</span></div>
  <div class="stat green"><b>{eur(fin_ps-1000, sign=True)}</b><span>su €1.000 dal 2009</span></div>
</div>

<h3>1.1 · Che cosa si vende, esattamente</h3>
<p>Ogni trade è una coppia di opzioni sulla scadenza mensile IG: <b>vendi</b> una
put ~7-10% sotto il mercato (incassi il premio), <b>compri</b> una put più in
basso (l'ala: il paracadute che rende la perdita massima fissa e nota). Se in un
mese l'S&amp;P non crolla oltre il ~10%, tieni l'incasso. Cash-settled, si tiene
fino a scadenza: zero costi overnight.</p>
{fig("ps_payoff.png", "Un trade vero del backtest (aprile 2026, VIX 24). La zona "
     "verde è dove si guadagna: OVUNQUE sopra il pareggio, cioè anche se il mercato "
     "scende fino a −10%. La zona rossa è cappata dall'ala: qui la perdita massima "
     "è nota il giorno dell'apertura. Il rapporto premio/rischio del singolo trade "
     "è piccolo — l'edge sta nel vincere il 98% delle volte.")}

<h3>1.2 · Perché il premio esiste (misurato, non teorico)</h3>
<p>Il VIX dice quanto “dovrebbe” costare la volatilità. Sulle opzioni IG reali le
put lontane costano <b>fino al 73% in più</b> del giusto (skew): è la paura dei
crolli, ed è strutturale — documentata da decenni su tutti i mercati azionari.
Questo grafico confronta i prezzi VERI letti dal conto IG col modello usato nel
backtest: combaciano. (È il controllo che ha ucciso l'iron condor: le call, a
sconto, si vendevano in perdita.)</p>
{fig("ps_smile.png", "Punti = volatilità implicita misurata sui prezzi reali IG "
     "(14 lug 2026) in rapporto al VIX. Linea tratteggiata = il modello del "
     "backtest. La pendenza put misurata (0,301) coincide col modello (0,30) fino "
     "a 3σ: anche l'estrapolazione sulle put lontanissime regge.")}

<h3>1.3 · Quando si entra: la regola del post-panico</h3>
<p>Tre condizioni, tutte insieme: <b>(a)</b> VIX sopra 20 (il panico c'è stato),
<b>(b)</b> VIX sceso di almeno il 10% dal picco degli ultimi 10 giorni (sta
rientrando), <b>(c)</b> term structure normalizzata, VIX/VIX3M ≤ 1 (il mercato
non prezza più emergenza immediata). In 17 anni queste condizioni si sono
presentate 59 volte — in media 4 l'anno, concentrate proprio nelle crisi.</p>
{fig("ps_vix.png", "Ogni pallino è un'entrata reale del backtest, appoggiata sul "
     "VIX del giorno. Le entrate si accendono nelle code delle crisi (2010, 2011, "
     "2015, 2018, 2020, 2022, 2025) — mai sui massimi del panico, mai nella calma. "
     "58 verdi, 1 rossa.")}

<h3>1.4 · Sedici anni con €1.000 veri</h3>
<p>Simulazione con contratti INTERI (1 contratto per ogni €1.000 di equity, $1 al
punto). Il confronto è col programma “calendario” che vende ogni mese
qualunque cosa accada: alla fine incassa qualcosa in più
({eur(fin_cal-1000, sign=True)} contro {eur(fin_ps-1000, sign=True)}), ma nel
feb 2020 <b>perde l'intero rischio in un mese</b> — e solo per fortuna quel mese
il rischio era piccolo (VIX basso all'entrata). Il post-panico non ha mai avuto
un mese sotto il −2%.</p>
{fig("ps_equity.png", "€1.000 iniziali, 2009–2026, contratti interi, netto dei "
     "costi. La linea verde (post-panico) sale a gradini regolari; l'ocra "
     "(calendario) fa un po' di più ma passa dal buco del 2020.")}
{fig("ps_trades.png", "Ogni barra è un trade in euro (1 contratto). Sopra: il "
     "post-panico — tanti piccoli incassi regolari, una sola barra rossa "
     "microscopica (2022). Sotto: il calendario — stessa musica finché arriva "
     "feb 2020, che si mangia due anni di premi in un colpo.")}
{fig("ps_dist.png", "La distribuzione degli esiti (scala log). Le due strategie "
     "hanno lo stesso corpo — la differenza è tutta nella coda sinistra: il "
     "calendario ha un trade a −100% del rischio, il post-panico si ferma a −36% "
     "nel caso peggiore della sua storia (e −1% dal 2009 col filtro completo).")}

<h3>1.5 · Anno per anno, in euro</h3>
{fig("ps_yearly.png", "P&L annuo in euro su €1.000 (1 contratto). Nessun anno in "
     "rosso oltre il rumore; gli anni migliori sono proprio quelli DOPO le crisi "
     "(2020-2022), quando il premio venduto è più ricco.")}

<h3>1.6 · E con più capitale?</h3>
<p>Il compounding qui scatta <b>a gradini</b>: ogni €1.000 di equity in più = un
contratto in più per trade. Con €3.000 si parte già con 3 contratti.</p>
{fig("ps_capital.png", "Stessa strategia, tre capitali di partenza. In media "
     "~€20/anno per ogni €1.000 (≈ +2%/anno sul capitale, netto): piccolo ma "
     "quasi senza drawdown — è il mattone di reddito su cui costruire, non il "
     "motore che raddoppia il conto.")}

<h3>1.7 · Il limite, senza trucco</h3>
{fig("ps_2008.png", "Il post-panico SENZA il filtro term-structure, portato "
     "indietro fino al 2007: nel novembre 2008 vende dopo lo spike di ottobre e "
     "il mercato fa un secondo tonfo: −79% del rischio in un trade. Il filtro "
     "term-structure avrebbe probabilmente bloccato quelle entrate (backwardation "
     "persistente per mesi) — ma i dati VIX3M partono da set-2009, quindi NON è "
     "verificabile.")}
<div class="caveat"><b>Regola di sizing che ne segue:</b> si dimensiona sempre
come se il <b>−100% del rischio potesse accadere</b> (1 contratto per €1.000,
mai di più). Se domani arriva un 2008, il conto da €1.000 perde ~€200-400 —
male, ma sopravvive e riparte. Chi dimensiona sul “non è mai successo dal 2009”
prima o poi lo scopre nel modo costoso.</div>

<h3>1.8 · Sette trade veri, dal registro del backtest</h3>
<p>Un contratto ciascuno. La riga rossa è <b>l'unica perdita</b> del programma
completo dal 2009.</p>
<div class="tablewrap"><table>
<tr><th>entrata</th><th>vix</th><th>s&amp;p</th><th>vendi put a</th>
<th>ala a</th><th>incassi</th><th>rischio max</th><th>s&amp;p a scadenza</th>
<th>esito</th></tr>
{tab}
</table></div>
</section>

<section id="edge1">
<h2><span class="no">§2</span>L'edge in riserva — compra-il-dip, versione ensemble</h2>

<p>È l'edge storico del progetto (comprare l'S&amp;P nei giorni di ipervenduto
estremo, solo in uptrend), potenziato a luglio 2026 con <b>5 segnali della stessa
famiglia</b> + un satellite short per gli anni di orso. I numeri sono più grossi
del put-spread — ma il contratto CFD minimo vale ~€7.500 di nozionale, quindi
<b>resta in riserva finché il capitale non supera ~€2.500</b>.</p>

<div class="stats">
  <div class="stat green"><b>342</b><span>trade in 18 anni</span></div>
  <div class="stat"><b>~20/anno</b><span>frequenza (2,5× la base)</span></div>
  <div class="stat green"><b>79%</b><span>trade vinti</span></div>
  <div class="stat green"><b>+27%</b><span>CAGR a leva 3x</span></div>
  <div class="stat red"><b>30%</b><span>maxDD a leva 3x</span></div>
  <div class="stat red"><b>≥€2.500</b><span>capitale minimo reale</span></div>
</div>

{fig("mr_equity.png", "Base 100, leva 3x, scala log. L'ensemble (verde) triplica "
     "il risultato della sola base RSI2 (ocra) a parità di natura del rischio: "
     "stessa famiglia di segnali, più occasioni.")}
{fig("mr_triggers.png", "Il controllo che conta: ogni trigger aggiunto è stato "
     "misurato SOLO sui giorni che la base non copre già. Tutti guadagnano più "
     "delle entrate casuali (linea rossa) — nessuno è un doppione travestito.")}
{fig("mr_yearly.png", "Anno per anno a leva 3x: 16 su 18 positivi; i due negativi "
     "(2018, 2022) restano piccoli. Da notare il 2011: −0% — l'anno peggiore non "
     "perde, semplicemente non guadagna.")}
{fig("mr_t6.png", "Il satellite short (vendi l'euforia sotto la media a 200 "
     "giorni): quasi sempre fermo, si accende negli anni di orso — 2008, 2020, "
     "2022 — esattamente dove il compra-il-dip soffre. 27 trade in 18 anni, "
     "guadagno medio +0,96% a trade, batte il 100% delle entrate casuali.")}
{fig("mr_capital.png", "Il vincolo in una figura: con €2.500 (1 contratto ≈ leva "
     "3x) il motore gira; sotto, il contratto minimo forza una leva fuori dal "
     "profilo validato. Con €1.000 questo edge NON si può tradare in sicurezza — "
     "per questo oggi si parte dalle opzioni.")}

<div class="note"><b>Perché teniamo entrambi:</b> il put-spread produce reddito
quasi piatto col capitale piccolo di oggi; l'ensemble è il motore di crescita che
si accende appena l'equity tocca ~€2.500. Sono anche complementari nel tempo: il
put-spread lavora <i>dopo</i> le crisi, il dip-buy <i>dentro</i> i ribassi in
uptrend, il satellite short negli orsi conclamati.</div>
</section>

<section id="metodo">
<h2><span class="no">§3</span>Metodo, ipotesi, e che cosa ucciderebbe questi numeri</h2>

<p><b>La barra di validazione</b> (identica per ogni idea; 15 idee l'hanno
fallita e sono archiviate): battere entrate casuali nello stesso regime ·
netto dei costi reali IG · reggere su dati mai visti (in-sample/out-of-sample) ·
essere un altopiano di parametri, non un picco · essere stabile anno per anno.
Le opzioni, in più: prezzate con lo <b>smile reale misurato dal broker</b>, mai
col VIX piatto (l'errore che aveva gonfiato 2,3× il credito dell'iron condor,
poi falsificato).</p>

<p><b>Ipotesi dichiarate:</b> cambio EUR/USD fisso a 1,08 · spread opzioni 1
punto per gamba (misurato: 0,5–1,8) · hold a scadenza, settlement cash a
intrinseco (confermato sul conto reale) · contratti interi, nessun frazionamento
· lo smile viene da UNA istantanea (14 lug 2026) — un sampler giornaliero lo sta
verificando per 2–4 settimane prima di ogni euro vero.</p>

<p><b>Cosa ucciderebbe l'edge (e come lo vedremmo):</b> lo skew delle put IG si
normalizza (→ il sampler lo mostra: ATM verso 0,9, pendenza sotto 0,25) · un
crash a doppia gamba stile 2008 (→ perdita piena ma cappata: è il costo già
prezzato nel sizing) · spread reali molto peggiori dei misurati (→ il pilot con
1 contratto lo rivela prima della size piena).</p>

<h3>Riprodurre tutto</h3>
<div class="cmd"># l'edge operativo (put-spread post-panico)
python scripts/short_vol_us500.py --strat putspread --a 1.5 --b 2.5 \\
    --spread-leg 1.0 --real-smile --entry-mode postspike \\
    --spike-min 20 --cool 0.90 --ts-max 1.0

# l'ensemble compra-il-dip
python scripts/mean_reversion_us500.py --trigger union --exit-ma 10 \\
    --scale-in 2 --add-thr 5

# questi grafici
python scripts/make_edge_charts.py &amp;&amp; python scripts/make_edge_report.py</div>

<p><b>Prossimi passi</b> (in ordine): completare il sampler dello skew (2–4
settimane di campioni) → adapter d'esecuzione a 2 gambe (riusa l'infrastruttura
del condor: sessione persistente, apertura longs-first, monitor) → pilot con
1 contratto e €1.000 → confronto fill reali vs modello → solo allora, size
piena.</p>
</section>

<footer>
IGEdge · nota di ricerca generata il 14 luglio 2026 · dati: IG (US500 daily
2007-2026, catena opzioni reale), CBOE (VIX, VIX3M) · documentazione completa:
docs/INDICE-EDGE.md · i trade di questi grafici: docs/report/data/*.csv
</footer>
</div>
"""

path = f"{OUT}/report-edges.html"
with open(path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"OK {path}  ({os.path.getsize(path)/1e6:.1f} MB)")
print(f"   post-panico su €1000: finale {eur(fin_ps)}  |  calendario: {eur(fin_cal)}"
      f"  |  perdita peggiore calendario: {eur(worst_cal_eur)}")
