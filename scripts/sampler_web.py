#!/usr/bin/env python3
"""
Mini interfaccia web READ-ONLY del sampler (per il Cloudflare Tunnel del Pi).

Espone SOLO (whitelist, nessun path arbitrario, nessun segreto):
  /                   pagina di stato: verdetto del gate + ultimi campioni + log
  /skew_samples.csv   download del CSV dei campioni
  /sampler.log        download del log del demone
  /salute             healthcheck

Nessuna azione possibile (solo GET, solo lettura). Il compose la pubblica solo
su 127.0.0.1 del Pi: da fuori ci si arriva SOLO via Cloudflare Tunnel (+Access).
"""
import html
import io
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

CSV = "data/research/skew_samples.csv"
LOG = "logs/sampler.log"
PORT = int(os.getenv("WEB_PORT", "8890"))

FILES = {  # whitelist: path URL -> (file, mime)
    "/skew_samples.csv": (CSV, "text/csv"),
    "/sampler.log": (LOG, "text/plain; charset=utf-8"),
}

STYLE = """<style>
body{font:15px/1.5 Georgia,serif;background:#F7F6F2;color:#16211E;
max-width:760px;margin:0 auto;padding:24px 16px}
h1{font-size:22px} h2{font-size:17px;margin-top:1.6em}
.ok{color:#175E54;font-weight:bold} .warn{color:#A63232;font-weight:bold}
table{border-collapse:collapse;width:100%;font:12.5px Consolas,monospace}
td,th{padding:4px 8px;border-bottom:1px solid #DDD9CE;text-align:right}
th{text-align:right;color:#6B7570} td:first-child,th:first-child{text-align:left}
pre{background:#EFEDE6;padding:10px;font:11.5px Consolas,monospace;
overflow-x:auto;white-space:pre-wrap}
a{color:#175E54} .btn{display:inline-block;border:1px solid #175E54;
padding:6px 14px;margin:4px 8px 4px 0;text-decoration:none;border-radius:3px}
small{color:#6B7570}</style>"""


def gate_report():
    """Verdetto del gate dai campioni (stessa logica di sample_skew --report)."""
    try:
        import pandas as pd
        df = pd.read_csv(CSV)
    except Exception as e:
        return f"<p class='warn'>nessun campione ancora ({html.escape(str(e))})</p>"
    n = len(df)
    out = [f"<p><b>{n} campioni</b> dal {str(df['ts'].iloc[0])[:10]} "
           f"al {str(df['ts'].iloc[-1])[:10]} — VIX range "
           f"[{df['vix'].min():.1f}, {df['vix'].max():.1f}]</p><table>"
           "<tr><th>parametro</th><th>media</th><th>min</th><th>max</th>"
           "<th>backtest</th><th>verdetto</th></tr>"]
    for col, ref, soglia in [("atm_ratio", 0.77, 0.08),
                             ("put_slope", 0.30, 0.08),
                             ("call_slope", 0.16, 99)]:
        s = df[col].dropna()
        if not len(s):
            continue
        ok = abs(s.mean() - ref) < soglia
        out.append(f"<tr><td>{col}</td><td>{s.mean():.3f}</td>"
                   f"<td>{s.min():.3f}</td><td>{s.max():.3f}</td><td>{ref}</td>"
                   f"<td class='{'ok' if ok else 'warn'}'>"
                   f"{'✅ regge' if ok else '⚠️ devia'}</td></tr>")
    out.append("</table>")
    gate_n = n >= 15
    s = df["atm_ratio"].dropna()
    gate_v = len(s) > 0 and s.mean() <= 0.82
    if gate_n and gate_v:
        out.append("<p class='ok'>🎯 GATE CHIUDIBILE: campioni sufficienti e "
                   "ATM medio ≤ 0.82 → si può decidere il pilot.</p>")
    else:
        why = []
        if not gate_n:
            why.append(f"servono ~15 campioni (ora {n})")
        if not gate_v:
            why.append("ATM medio sopra 0.82")
        out.append(f"<p>Gate ancora aperto: {', '.join(why)}.</p>")
    # ultimi campioni
    out.append("<h2>Ultimi campioni</h2><table><tr><th>data</th><th>vix</th>"
               "<th>spot</th><th>atm</th><th>put_slope</th></tr>")
    for _, r in df.tail(10).iloc[::-1].iterrows():
        out.append(f"<tr><td>{str(r['ts'])[:16]}</td><td>{r['vix']:.1f}</td>"
                   f"<td>{r['spot']:.0f}</td><td>{r['atm_ratio']}</td>"
                   f"<td>{r['put_slope']}</td></tr>")
    out.append("</table>")
    return "".join(out)


def log_tail(nlines=35):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-nlines:]
        return html.escape("".join(lines))
    except Exception as e:
        return f"log non disponibile: {html.escape(str(e))}"


def page():
    return f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IGEdge — sampler</title>{STYLE}
<h1>📡 IGEdge — sampler opzioni</h1>
<small>generata {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · read-only ·
nessuna azione possibile da qui</small>
<h2>Verdetto del gate (skew IG)</h2>
{gate_report()}
<h2>Download</h2>
<a class="btn" href="/skew_samples.csv">⬇ skew_samples.csv</a>
<a class="btn" href="/sampler.log">⬇ sampler.log</a>
<h2>Ultime righe del log</h2>
<pre>{log_tail()}</pre>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = page().encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/salute":
            self._send(200, "text/plain", b"ok")
        elif self.path in FILES:
            fp, mime = FILES[self.path]
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    self._send(200, mime, f.read())
            else:
                self._send(404, "text/plain", b"file non ancora creato")
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, mime, body):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):   # log sobrio su stdout
        print(f"{datetime.now().isoformat(timespec='seconds')} web {self.address_string()} {fmt % args}",
              flush=True)


if __name__ == "__main__":
    print(f"sampler-web in ascolto su :{PORT} (read-only)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
