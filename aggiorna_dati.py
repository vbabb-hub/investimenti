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

def parse_dataroma(html):
    """Raggruppa i link ai titoli sotto l'ultima intestazione incontrata (struttura non verificata)."""
    from bs4 import BeautifulSoup
    soup, secs, cur = BeautifulSoup(html, "html.parser"), [], None
    for el in soup.find_all(True):
        txt = el.get_text(" ", strip=True)
        if el.name in ("h1", "h2", "h3", "h4", "h5", "caption", "th") and 3 < len(txt) < 80:
            cur = {"title": txt, "items": []}
            secs.append(cur)
        elif el.name == "a" and "stock.php?sym=" in (el.get("href") or "") and cur is not None:
            sym = el["href"].split("sym=")[-1].split("&")[0]
            if sym and all(i["t"] != sym for i in cur["items"]) and len(cur["items"]) < 30:
                cur["items"].append({"t": sym, "n": el.get("title") or txt})
    return [s for s in secs if s["items"]]

def dataroma():
    import requests
    out = {"updated": dt.datetime.utcnow().isoformat(timespec="minutes") + "Z", "sections": []}
    if os.environ.get("ENABLE_DATAROMA") != "true":
        out["error"] = "Dataroma disattivato: controlla le condizioni d'uso e imposta ENABLE_DATAROMA=true"
        return out
    r = requests.get("https://www.dataroma.com/m/home.php", headers={"User-Agent": "Mozilla/5.0 (uso personale)"}, timeout=30)
    r.raise_for_status()
    out["sections"] = parse_dataroma(r.text)
    if not out["sections"]:
        out["error"] = "Nessuna sezione trovata: la struttura della pagina è cambiata"
    return out

if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    os.makedirs("dati", exist_ok=True)
    for name, fn in (("dataroma", dataroma), ("azioni", lambda: azioni(lim))):
        try:
            data = fn()
        except Exception as exc:
            print(f"{name}: errore {exc}", file=sys.stderr)
            continue  # mantiene il file precedente
        json.dump(data, open(f"dati/{name}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"{name}: scritto", file=sys.stderr)
