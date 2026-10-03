"""Temporary probe: where the Danish and German turbine registers are, and what their fields look like. No rain data."""
import json, os, re, time, urllib.request, zipfile, io, collections
UA = "kvantixtech offshore-wind-rain probe (github actions; validation@kvantix.tech)"
OUT = "probe"
log = {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

def get(url, method="GET", limit=None):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}, method=method), timeout=300)
    return r.status, dict(r.headers), (r.read(limit) if method == "GET" else b"")

# 1. ENS pages: every link
ens = {}
for u in ["https://ens.dk/service/statistik-data-noegletal-og-kort/data-oversigt-over-energisektoren",
          "https://ens.dk/analyser-og-statistik/data-oversigt-over-energisektoren",
          "https://sologvindinfo.dk/spatialmap"]:
    try:
        st, h, b = get(u)
        t = b.decode("utf-8", "replace")
        links = sorted(set(re.findall(r'(?:href|src)="([^"]+)"', t)))
        ens[u] = {"status": st, "bytes": len(b), "links": [l for l in links if re.search(r"(?i)media|download|xls|csv|stamdata|vind|arcgis|rest/services|api|json", l)][:80],
                  "arcgis": sorted(set(re.findall(r'https?://[^"\'\s]+(?:arcgis|MapServer|FeatureServer)[^"\'\s]*', t)))[:30]}
    except Exception as e:
        ens[u] = {"error": str(e)[:200]}
log["ens"] = ens
cand = {}
for u in ["https://ens.dk/sites/ens.dk/files/Statistik/anlaegprodtilnettet.xlsx",
          "https://ens.dk/media/3958/download", "https://ens.dk/media/6206/download"]:
    try:
        st, h, _ = get(u, "HEAD"); cand[u] = {"status": st, "type": h.get("Content-Type"), "len": h.get("Content-Length"), "disp": h.get("Content-Disposition")}
    except Exception as e:
        cand[u] = {"error": str(e)[:200]}
log["ens_candidates"] = cand

# 2. MaStR: member list and offshore field values
try:
    st, h, b = get("https://www.marktstammdatenregister.de/MaStR/Datendownload")
    links = sorted(set(re.findall(r'https://download\.marktstammdatenregister\.de/[^"\']+\.zip', b.decode("utf-8", "replace"))))
    url = links[0]; log["mastr_url"] = url
    path = "/tmp/mastr.zip"
    t = time.time()
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=3600) as r, open(path, "wb") as f:
        while True:
            c = r.read(1 << 22)
            if not c: break
            f.write(c)
    log["mastr_bytes"] = os.path.getsize(path); log["mastr_seconds"] = round(time.time() - t)
    z = zipfile.ZipFile(path)
    names = z.namelist(); log["mastr_members"] = len(names)
    wind = [n for n in names if "EinheitenWind" in n]; log["mastr_wind_files"] = wind
    import xml.etree.ElementTree as ET
    tags = collections.Counter(); vals = {k: collections.Counter() for k in ("Lage", "WindAnLandOderAufSee", "Seelage", "EinheitBetriebsstatus", "ClusterNordsee", "ClusterOstsee")}
    offshore = []
    for n in wind:
        with z.open(n) as fh:
            for ev, el in ET.iterparse(fh):
                if el.tag == "EinheitWind":
                    d = {c.tag: (c.text or "") for c in el}
                    tags.update(d.keys())
                    for k in vals:
                        if k in d: vals[k][d[k]] += 1
                    if d.get("Lage") == "889" or d.get("WindAnLandOderAufSee") == "889":
                        offshore.append(d)
                    el.clear()
    log["mastr_tags"] = dict(tags.most_common())
    log["mastr_values"] = {k: dict(v.most_common(20)) for k, v in vals.items()}
    log["mastr_offshore_count"] = len(offshore)
    log["mastr_offshore_sample"] = offshore[:3]
    parks = collections.Counter(d.get("NameWindpark", "") for d in offshore)
    log["mastr_offshore_parks"] = dict(parks.most_common(60))
    others = [n for n in names if re.search(r"(?i)katalog|Werte", n)]
    log["mastr_catalog_files"] = others
except Exception as e:
    log["mastr_error"] = repr(e)[:400]
json.dump(log, open(os.path.join(OUT, "result.json"), "w"), indent=1, ensure_ascii=False)
print("done")
