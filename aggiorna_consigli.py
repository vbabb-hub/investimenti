#!/usr/bin/env python3
"""Genera dati/consigli.json: candidati da acquistare o shortare, con punteggio a blocchi.
Non sono consigli personalizzati: regole fisse applicate ai dati di Yahoo e Dataroma."""
import datetime as dt, json, os, sys, time
import numpy as np, pandas as pd

POOL, TOP, MAX_SETTORE = 100, 5, 2
PESI = dict(q=30, v=25, m=25, c=10, e=10)   # qualità, valore, momentum, conferme, ingresso

def load(n, d=None):
    try:
        return json.load(open(f"dati/{n}.json", encoding="utf-8"))
    except Exception:
        return d

def pct(s, alto=True):
    r = pd.to_numeric(s, errors="coerce").rank(pct=True) * 100
    return r if alto else 100 - r

def dati_titolo(t):
    import yfinance as yf
    try:
        i = yf.Ticker(t).info or {}
    except Exception:
        return {}
    cap, fcf = i.get("marketCap") or 0, i.get("freeCashflow")
    return dict(roe=i.get("returnOnEquity"), om=i.get("operatingMargins"), rg=i.get("revenueGrowth"),
                eg=i.get("earningsGrowth"), de=i.get("debtToEquity"), fpe=i.get("forwardPE"),
                ev=i.get("enterpriseToEbitda"), fy=(fcf / cap if fcf and cap else None),
                si=i.get("shortPercentOfFloat"), earn=i.get("earningsTimestamp"), sett=i.get("sector"))

def fx(v, f):
    return f.format(v) if isinstance(v, (int, float)) and not np.isnan(v) else "n.d."

def blocchi(df):
    q = pd.concat([pct(df.roe), pct(df.om), pct(df.rg), pct(df.eg), pct(df.de, False)], axis=1)
    df["q"] = q.mean(axis=1).where(q.count(axis=1) >= 3)
    pe = pct(df.fpe.where(df.fpe > 0), False)
    pe[(df.fpe <= 0)] = 0
    ev = pct(df.ev.where(df.ev > 0), False)
    ev[(df.ev <= 0)] = 0
    v = pd.concat([pe, ev, pct(df.fy)], axis=1)
    df["v"] = v.mean(axis=1).where(v.count(axis=1) >= 1)
    df["m"] = pd.concat([pct(df.mom), pct(df.price / df.sma - 1)], axis=1).mean(axis=1)
    return df

def punteggio(df, lato):
    d = df.copy()
    if lato == "long":
        c = d.cnt.clip(upper=3) / 3 * 100
        e = np.select([d.rsi_d <= 40, d.rsi_d <= 55, d.rsi_d < 70], [100, 60, 30], 0)
        parts = dict(q=d.q, v=d.v, m=d.m, c=c, e=e)
    else:
        c = np.select([d.cnt == 0, d.cnt == 1], [100, 50], 0)
        e = np.select([d.rsi_d >= 60, d.rsi_d >= 50, d.rsi_d >= 40], [100, 60, 30], 0)
        parts = dict(q=100 - d.q, v=100 - d.v, m=100 - d.m, c=c, e=e)
    for k, v in parts.items():
        d["b_" + k] = pd.Series(v, index=d.index).fillna(50)
    d["score"] = sum(d["b_" + k] * PESI[k] for k in PESI) / sum(PESI.values())
    return d

def motivi(r, lato):
    w = []
    if lato == "long":
        if r.b_q >= 70: w.append(f"Qualità alta (ROE {fx(r.roe*100,'{:.0f}')}%, margine operativo {fx(r.om*100,'{:.0f}')}%)")
        if r.b_v >= 70: w.append(f"Valutazione bassa nel gruppo (P/E atteso {fx(r.fpe,'{:.0f}')})")
        if r.b_m >= 70: w.append(f"Rendimento a 12 mesi {fx(r.mom*100,'{:+.0f}')}% e prezzo sopra la media")
        if r.cnt: w.append(f"Presente in {int(r.cnt)} liste Dataroma")
        if r.rsi_d <= 40: w.append(f"RSI giornaliero {r.rsi_d:.0f}: ritracciamento nel trend")
    else:
        if r.b_q >= 70: w.append(f"Qualità debole (ROE {fx(r.roe*100,'{:.0f}')}%, margine operativo {fx(r.om*100,'{:.0f}')}%)")
        if r.b_v >= 70: w.append("Utili negativi" if (r.fpe is None or np.isnan(r.fpe) or r.fpe <= 0) else f"Valutazione alta nel gruppo (P/E atteso {r.fpe:.0f})")
        if r.b_m >= 70: w.append(f"Rendimento a 12 mesi {fx(r.mom*100,'{:+.0f}')}% e prezzo sotto la media")
        if r.rsi_d >= 55: w.append(f"RSI giornaliero {r.rsi_d:.0f}: rimbalzo in un trend debole")
        if r.si == r.si and r.si: w.append(f"Interesse short già al {r.si*100:.0f}% del flottante")
    return w or ["Punteggio complessivo nel gruppo migliore"]

def scegli(df, lato):
    d = punteggio(df, lato).sort_values("score", ascending=False)
    out, per = [], {}
    for _, r in d.iterrows():
        s = r.sett if isinstance(r.sett, str) else "?"
        if per.get(s, 0) >= MAX_SETTORE:
            continue
        per[s] = per.get(s, 0) + 1
        out.append(dict(t=r.t, n=r.n, p=r.price, sma=r.sma, s=round(r.score, 1), w=motivi(r, lato),
                        b={k: int(round(r["b_" + k])) for k in PESI}, sett=s))
        if len(out) == TOP:
            break
    return out

def storico(oggi, righe):
    """Registra la lista di oggi e valuta quelle passate con i prezzi attuali."""
    prezzi = {r[0]: r[3] for r in righe if r[3]}
    h = load("storico_consigli", [])
    h = [x for x in h if x["d"] != oggi["d"]] + [oggi]
    h = h[-120:]
    json.dump(h, open("dati/storico_consigli.json", "w", encoding="utf-8"), separators=(",", ":"))
    ris = []
    for x in h[:-1][-10:]:
        g = (dt.date.fromisoformat(oggi["d"]) - dt.date.fromisoformat(x["d"])).days
        def media(lista, segno):
            v = [segno * (prezzi[t] / p0 - 1) for t, p0 in lista if t in prezzi and p0]
            return round(float(np.mean(v)), 4) if v else None
        ris.append(dict(d=x["d"], g=g, l=media(x["long"], 1), s=media(x["short"], -1)))
    return ris

def main():
    az = load("azioni")
    if not az or not az["rows"] or len(az["rows"][0]) < 11:
        sys.exit("azioni.json mancante o senza i nuovi campi: lancia prima aggiorna_dati.py")
    dr = load("dataroma", {"sections": []})
    cnt = {}
    for s in dr.get("sections", []):
        for i in s["items"]:
            cnt[i["t"]] = cnt.get(i["t"], 0) + 1
    cols = ["t", "n", "cap", "price", "sma", "rsi_h", "rsi_d", "rsi_w", "mom", "vol", "dd"]
    d = pd.DataFrame([r[:11] for r in az["rows"]], columns=cols)
    for c in cols[2:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["price", "sma", "mom", "vol", "rsi_d"])
    d["cnt"] = d.t.map(cnt).fillna(0)
    lg = d[(d.price > d.sma) & (d.mom > 0) & (d.vol <= .7) & (d.rsi_d < 75)].nlargest(POOL, "mom")
    sh = d[(d.price < d.sma) & (d.mom < 0) & (d.vol <= .8)].nsmallest(POOL, "mom")
    info = {}
    for t in pd.concat([lg.t, sh.t]).unique():
        info[t] = dati_titolo(t)
        time.sleep(0.2)
    ora = time.time()
    def prepara(p, lato):
        p = p.copy()
        f = pd.DataFrame([info.get(t, {}) for t in p.t], index=p.index)
        for c in ["roe", "om", "rg", "eg", "de", "fpe", "ev", "fy", "si", "earn"]:
            p[c] = pd.to_numeric(f.get(c), errors="coerce") if c in f else np.nan
        p["sett"] = f["sett"] if "sett" in f else None
        p = p[~p.earn.between(ora, ora + 7 * 86400)]
        if lato == "short":
            p = p[~(p.si > .15)]
        return blocchi(p)
    long, short = scegli(prepara(lg, "long"), "long"), scegli(prepara(sh, "short"), "short")
    oggi = dt.date.today().isoformat()
    out = dict(updated=dt.datetime.utcnow().isoformat(timespec="minutes") + "Z", pool=[len(lg), len(sh)],
               long=long, short=short,
               storico=storico(dict(d=oggi, long=[[x["t"], x["p"]] for x in long], short=[[x["t"], x["p"]] for x in short]), az["rows"]))
    json.dump(out, open("dati/consigli.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"consigli: {len(long)} acquisto, {len(short)} short", file=sys.stderr)

if __name__ == "__main__":
    main()
