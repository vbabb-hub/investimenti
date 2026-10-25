#!/usr/bin/env python3
"""Genera dati/azioni.json (screener azioni USA) e dati/dataroma.json per la PWA."""
import datetime as dt, json, os, sys
import numpy as np
import aggiorna_azioni_usa as m

def num(v, nd=2):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), nd)

def azioni(limit=None):
    uni = m.get_universe().sort_values("marketCap", ascending=False)
    if limit:
        uni = uni.head(limit)
    t = uni["symbol"].tolist()
    d, w, h = m.fetch_closes(t, "1d", "2y"), m.fetch_closes(t, "1wk", "5y"), m.fetch_closes(t, "1h", "60d")
    rows = []
    for _, u in uni.iterrows():
        k = u["symbol"]
        price = u["price"] if u["price"] == u["price"] else (float(d[k].iloc[-1]) if k in d else None)
        rows.append([k, u["name"], num(u["marketCap"], 0), num(price),
                     num(m.sma(d[k])) if k in d else None,
                     num(m.rsi(h[k]), 1) if k in h else None,
                     num(m.rsi(d[k]), 1) if k in d else None,
                     num(m.rsi(w[k]), 1) if k in w else None])
    return {"updated": dt.datetime.utcnow().isoformat(timespec="minutes") + "Z", "count": len(rows), "rows": rows}

TITOLI = [  # (testo cercato nella pagina, titolo mostrato): l'ordine conta
    ("buys last 2 qtrs by %", "Acquisti ultimi 2 trimestri, per peso"),
    ("buys last 2 qtrs", "Acquisti ultimi 2 trimestri"),
    ("buys last qtr by %", "Acquisti ultimo trimestre, per peso"),
    ("buys last qtr", "Acquisti ultimo trimestre (dato parziale)"),
    ("top 10 most owned", "Più posseduti"),
