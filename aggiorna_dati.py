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

KEYS = [
    ("top 10 buys last 2 qtrs by %", "Acquisti ultimi 2 trimestri, per peso"),
    ("top 10 buys last 2 qtrs", "Acquisti ultimi 2 trimestri, per numero"),
    ("top 10 buys last qtr by %", "Acquisti ultimo trimestre, per peso"),
    ("top 10 buys last qtr", "Acquisti ultimo trimestre, per numero"),
    ("top 10 stocks by %", "Maggior peso nei portafogli (top 10)"),
    ("most owned", "Più posseduti (top 10)"),
    ("big bets", "Scommesse forti (peso massimo · n. gestori)"),
    ("near 52 week low", "Vicini al minimo a 52 settimane (% sopra il minimo)"),
    ("most insider buys", "Più acquisti insider, 3 mesi (n. · importo $)"),
    ("latest significant", "Ultimi acquisti insider (data · importo $)"),
]

def parse_dataroma(html):
    """Le liste di Dataroma hanno il titolo come testo semplice: si riconosce dal testo e si
    attribuiscono i link ai titoli (stock.php?sym=) all'ultimo titolo incontrato."""
    from bs4 import BeautifulSoup, NavigableString
    soup, secs, cur, allsym = BeautifulSoup(html, "html.parser"), [], None, {}
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            if node.parent.name in ("script", "style", "a"):
                continue
            t = " ".join(str(node).split()).lower()
            if 3 < len(t) < 140:
                for key, title in KEYS:
                    if key in t:
                        cur = {"title": title, "items": []}
                        secs.append(cur)
                        break
        elif node.name == "a" and "stock.php?sym=" in (node.get("href") or ""):
            sym = node["href"].split("sym=")[-1].split("&")[0]
            text = " ".join(node.get_text(" ", strip=True).split())
            tr = node.find_parent("tr")
            if tr is not None:
                cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all("td")]
                n = " · ".join(c for c in cells if c and text not in c)
            else:
                n = text.split(" - ", 1)[1] if " - " in text else ""
            allsym.setdefault(sym, n)
            if cur is not None and len(cur["items"]) < 30 and all(i["t"] != sym for i in cur["items"]):
                cur["items"].append({"t": sym, "n": n})
    secs = [s for s in secs if s["items"]]
    if not secs and allsym:
        secs = [{"title": "Titoli sulla pagina", "items": [{"t": k, "n": v} for k, v in list(allsym.items())[:30]]}]
    return secs

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
        out["error"] = f"Nessuna sezione trovata ({len(r.text)} caratteri letti, {r.text.count('stock.php?sym=')} link ai titoli)"
        out["debug"] = {"stato": r.status_code, "byte": len(r.text), "link_titoli": r.text.count("stock.php?sym="), "inizio": r.text[:200]}
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
        
