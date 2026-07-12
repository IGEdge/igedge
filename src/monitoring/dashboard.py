"""
Dashboard bot IG — monitoraggio operativo + analisi quant del regime di mercato.

Due tab:
  1. Operativo — posizioni live, P&L, esposizione, kill switch, reconcile
     (dal PositionStore SQLite, che il bot aggiorna).
  2. Regime   — classificazione BULL/BEAR/TRANSIZIONE + regime di volatilità,
     metriche e favorevolezza per il dip-buy. Dati da data/research/us500_daily.csv
     (IG), NIENTE yfinance.

Avvio:  streamlit run src/monitoring/dashboard.py
"""
import os
import sqlite3

import numpy as np
import pandas as pd
import streamlit as st

DAILY_CSV = "data/research/us500_daily.csv"
POS_DB = os.getenv("POSITIONS_DB", "data/positions.db")

st.set_page_config(page_title="IGEdge — Monitoraggio & Regime", layout="wide")


# ---------------------------------------------------------------- indicatori
def _rsi(close: pd.Series, period: int) -> pd.Series:
    d = close.diff()
    ru = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    rd = (-d).clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + ru / rd.replace(0, np.nan))


@st.cache_data(ttl=3600)
def load_daily():
    df = pd.read_csv(DAILY_CSV)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df["sma50"] = df["close"].rolling(50).mean()
    df["sma200"] = df["close"].rolling(200).mean()
    df["rsi2"] = _rsi(df["close"], 2)
    df["rsi14"] = _rsi(df["close"], 14)
    ret = df["close"].pct_change()
    df["vol20"] = ret.rolling(20).std() * np.sqrt(252)     # vol annualizzata
    df["dd_52w"] = df["close"] / df["close"].rolling(252).max() - 1
    return df


def regime(df: pd.DataFrame):
    r = df.iloc[-1]
    sma200_slope = df["sma200"].iloc[-1] - df["sma200"].iloc[-21]  # vs 20g fa
    # trend
    if r["close"] > r["sma200"] and sma200_slope > 0:
        trend = "BULL"
    elif r["close"] < r["sma200"] and sma200_slope < 0:
        trend = "BEAR"
    else:
        trend = "TRANSIZIONE"
    # volatilità: percentile della vol20 sulla storia
    vpct = (df["vol20"] < r["vol20"]).mean() * 100
    vlab = "ALTA" if vpct > 66 else "BASSA" if vpct < 33 else "NORMALE"
    # favorevolezza dip-buy: bull + vol >= normale
    fav = trend == "BULL" and vpct >= 33
    return trend, vlab, vpct, fav, r, sma200_slope


# ---------------------------------------------------------------- posizioni
def load_positions():
    if not os.path.exists(POS_DB):
        return pd.DataFrame(), pd.DataFrame()
    con = sqlite3.connect(POS_DB)
    try:
        op = pd.read_sql("SELECT * FROM positions WHERE status='OPEN'", con)
        hi = pd.read_sql("SELECT * FROM positions ORDER BY id DESC LIMIT 100", con)
    except Exception:
        op, hi = pd.DataFrame(), pd.DataFrame()
    con.close()
    return op, hi


# ================================================================ UI
st.title("🤖 IGEdge — Monitoraggio & Regime di mercato")
tab_op, tab_reg = st.tabs(["📊 Operativo", "🌡️ Regime di mercato"])

with tab_op:
    op, hi = load_positions()
    c1, c2, c3 = st.columns(3)
    c1.metric("Posizioni aperte", len(op))
    c2.metric("Trade storici", len(hi))
    if not hi.empty and "pnl" in hi:
        closed = hi[hi["status"] == "CLOSED"]
        wr = (closed["pnl"] > 0).mean() * 100 if len(closed) else 0
        c3.metric("Win rate (chiusi)", f"{wr:.0f}%")
    st.subheader("Posizioni aperte")
    st.dataframe(op if not op.empty else pd.DataFrame({"info": ["nessuna posizione"]}),
                 use_container_width=True)
    st.subheader("Storico (ultimi 100)")
    st.dataframe(hi, use_container_width=True)
    st.caption("Fonte: position_store (SQLite) aggiornato dal bot. Il reconcile "
               "col venue lo esegue il bot a ogni ciclo.")

with tab_reg:
    try:
        df = load_daily()
        trend, vlab, vpct, fav, r, slope = regime(df)
        badge = {"BULL": "🟢", "BEAR": "🔴", "TRANSIZIONE": "🟡"}[trend]
        st.subheader(f"{badge} Regime: **{trend}**  ·  Volatilità: **{vlab}** "
                     f"(percentile {vpct:.0f})")
        favtxt = "✅ FAVOREVOLE al dip-buy" if fav else "⚠️ poco favorevole al dip-buy"
        st.markdown(f"**{favtxt}** — la mean-reversion rende di più in *bull + vol ≥ normale*.")

        m = st.columns(4)
        m[0].metric("Prezzo", f"{r['close']:.0f}")
        m[1].metric("vs SMA200", f"{(r['close']/r['sma200']-1)*100:+.1f}%")
        m[2].metric("Drawdown 52w", f"{r['dd_52w']*100:+.1f}%")
        m[3].metric("Vol annua (20g)", f"{r['vol20']*100:.0f}%")
        m2 = st.columns(4)
        m2[0].metric("RSI(2) — segnale dip", f"{r['rsi2']:.0f}",
                     "≤10 = ENTRA" if r["rsi2"] <= 10 else "no dip")
        m2[1].metric("RSI(14)", f"{r['rsi14']:.0f}")
        m2[2].metric("SMA50", f"{r['sma50']:.0f}")
        m2[3].metric("Pendenza SMA200 (20g)", f"{slope:+.0f}")

        st.line_chart(df[["close", "sma50", "sma200"]].tail(500))
        st.caption(f"Dati: {DAILY_CSV} (IG daily, aggiornato al "
                   f"{df.index[-1].date()}). Rigenera con "
                   f"scripts/download_us500_ig.py. Zero yfinance.")
    except FileNotFoundError:
        st.warning(f"{DAILY_CSV} non trovato — esegui scripts/download_us500_ig.py")
