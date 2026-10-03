#!/usr/bin/env python3
"""Step 2 of the order of work in METHOD.md: the gauge list and day counts.

What this script outputs about measurements is ONLY:
  - per gauge series and calendar year, the number of days that have a value
  - counts of quality flags and of the day windows (start and end time of each daily value)
It never prints, plots, summarises or stores a precipitation amount. Downloads are hashed in
data/gauges/downloads.csv and discarded; the values are fetched again, and committed, in steps 5 and 6.

Sources:
  - DMI climateData API: station metadata (all versions) and daily acc_precip per station, 1991-2025
  - DWD CDC daily precipitation (more_precip), historical and recent zips: station metadata files
    (location history, instrument history, parameter description) and the daily product file
Writes data/gauges/{series.csv, day_counts.csv, valid_series.csv, flags.json, windows.json, downloads.csv,
meta/*}, data/gauges_run.log, and updates data/manifest.json.
"""
import csv, datetime as dt, gzip, hashlib, io, json, math, os, re, sys, time, urllib.request, zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "gauges")
META = os.path.join(OUT, "meta")
UA = "kvantixtech offshore-wind-rain (github actions; validation@kvantix.tech)"
BOX = (4.5, 53.3, 13.0, 57.9)
Y0, Y1 = 1991, 2025
DMI = "https://opendataapi.dmi.dk/v2/climateData/collections"
DWD = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/"
downloads = []


def log(*a):
    print(*a, flush=True)


def http(url, tries=5):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=600) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
            downloads.append([url, len(b), hashlib.sha256(b).hexdigest()])
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def in_box(lat, lon):
    return BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]


def split_positions(versions):
    """versions: list of (from_date, to_date, lat, lon, height, label). Returns list of periods, a new one at every
    move of more than 1 km or 20 m in height, and at every change of label (instrument)."""
    versions = sorted(versions, key=lambda v: v[0])
    out = []
    for v in versions:
        if out:
            last = out[-1]
            moved = km(last["lat"], last["lon"], v[2], v[3]) > 1.0 or (v[4] is not None and last["height"] is not None and abs(v[4] - last["height"]) > 20)
            if not moved and v[5] == last["label"]:
                last["to"] = max(last["to"], v[1]); continue
            reason = "moved" if moved else "instrument"
        else:
            reason = "first"
        out.append({"from": v[0], "to": v[1], "lat": v[2], "lon": v[3], "height": v[4], "label": v[5], "reason": reason})
    return out


# ------------------------------------------------------------------ DMI
def dmi():
    b = http(f"{DMI}/station/items?bbox={BOX[0]},{BOX[1]},{BOX[2]},{BOX[3]}&limit=10000")
    open(os.path.join(META, "dmi_climate_stations.json"), "wb").write(b)
    feats = json.loads(b)["features"]
    by = defaultdict(list)
    for f in feats:
        p = f["properties"]
        if "acc_precip" not in (p.get("parameterId") or []) or p.get("country") != "DNK":
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        if not in_box(lat, lon):
            continue
        fr = (p.get("validFrom") or p.get("operationFrom") or "1900-01-01")[:10]
        to = (p.get("validTo") or p.get("operationTo") or "2999-12-31")[:10]
        by[p["stationId"]].append((fr, to, lat, lon, p.get("stationHeight"), "DMI " + p["stationId"], p.get("name") or "",
                                   (p.get("operationFrom") or "1900-01-01")[:10], (p.get("operationTo") or "2999-12-31")[:10]))
    log(f"DMI: {len(by)} stations with acc_precip in the box")
    series = []
    for sid, vs in by.items():
        name = sorted(vs, key=lambda v: v[0])[-1][6]
        pers = split_positions([v[:6] for v in vs])
        # metadata versions may start after the station did: the first period starts at the earliest operationFrom,
        # the last ends at the latest operationTo
        pers[0]["from"] = min([pers[0]["from"]] + [v[7] for v in vs])
        pers[-1]["to"] = max([pers[-1]["to"]] + [v[8] for v in vs])
        for k, per in enumerate(pers):
            if per["to"] < f"{Y0}-01-01" or per["from"] > f"{Y1}-12-31":
                continue
            series.append({"series_id": f"DMI-{sid}-{k}", "network": "DMI", "station_id": sid, "name": name, "lat": per["lat"], "lon": per["lon"],
                           "height": per["height"], "from": per["from"], "to": per["to"], "instrument": "", "split_reason": per["reason"]})

    flags, windows = Counter(), Counter()
    counts = defaultdict(Counter)   # (station) -> Counter(date strings with a value)

    def one(sid):
        url = f"{DMI}/stationValue/items?stationId={sid}&parameterId=acc_precip&timeResolution=day&datetime={Y0}-01-01T00:00:00Z/{Y1 + 1}-01-01T00:00:00Z&limit=300000"
        fs = json.loads(http(url)).get("features", [])
        days, fl, wi = [], Counter(), Counter()
        for f in fs:
            p = f["properties"]
            fl[(str(p.get("qcStatus")), str(p.get("validity")))] += 1
            frm, to = p.get("from", ""), p.get("to", "")
            wi[(frm[11:19], to[11:19])] += 1
            if p.get("value") is not None:
                days.append(frm[:10])
        return sid, days, fl, wi

    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, (sid, days, fl, wi) in enumerate(ex.map(one, sorted(by)), 1):
            for d in days:
                counts[sid][d] += 1
            flags.update(fl); windows.update(wi)
            if n % 50 == 0:
                log(f"DMI values counted for {n}/{len(by)} stations")
    return series, counts, {"qcStatus,validity": {f"{a},{b}": c for (a, b), c in flags.most_common()}}, \
        {f"{a}->{b}": c for (a, b), c in windows.most_common()}


# ------------------------------------------------------------------ DWD
def dwd():
    parent = http(DWD).decode("latin-1")
    docs = sorted(set(re.findall(r'href="([^"]+\.pdf)"', parent)))
    for d in docs:
        open(os.path.join(META, "dwd_" + d), "wb").write(http(DWD + d))
    lst = http(DWD + "historical/RR_Tageswerte_Beschreibung_Stationen.txt").decode("latin-1").splitlines()
    open(os.path.join(META, "dwd_RR_Tageswerte_Beschreibung_Stationen.txt"), "w", encoding="utf-8").write("\n".join(lst) + "\n")
    stations = {}
    for line in lst[2:]:
        p = line.split()
        if len(p) < 7:
            continue
        sid, fr, to, lat, lon = p[0], p[1], p[2], float(p[4]), float(p[5])
        if in_box(lat, lon) and to[:4] >= str(Y0) and fr[:4] <= str(Y1):
            stations[sid] = " ".join(p[6:-2]) if len(p) > 8 else p[6]
    files = {}
    for sub in ("historical/", "recent/"):
        names = set(re.findall(r'href="(tageswerte_RR_\d{5}_[^"]+\.zip)"', http(DWD + sub).decode("latin-1")))
        for n in names:
            sid = n.split("_")[2]
            if sid in stations:
                files.setdefault(sid, []).append(DWD + sub + n)
    log(f"DWD: {len(stations)} stations in the box overlapping {Y0}-{Y1}, {sum(len(v) for v in files.values())} files")

    flags, windows, series, counts = Counter(), Counter(), [], defaultdict(Counter)
    param_text = {}

    def parse_meta(text):
        rows = [r.split(";") for r in text.splitlines() if ";" in r]
        if not rows:
            return [], []
        head = [h.strip() for h in rows[0]]
        return head, [[c.strip() for c in r] for r in rows[1:] if len(r) >= len(head) - 1 and r[0].strip().isdigit()]

    def one(sid):
        geo, dev, days = [], [], defaultdict(set)
        fl = Counter()
        ptxt = None
        for url in sorted(files.get(sid, [])):
            z = zipfile.ZipFile(io.BytesIO(http(url)))
            for n in z.namelist():
                t = z.read(n).decode("latin-1")
                if n.startswith("Metadaten_Geographie"):
                    h, rows = parse_meta(t)
                    for r in rows:
                        d = dict(zip(h, r))
                        geo.append((d.get("von_datum", ""), d.get("bis_datum", "") or "29991231", float(d["Geogr.Breite"]), float(d["Geogr.Laenge"]),
                                    float(d.get("Stationshoehe") or "nan")))
                elif n.startswith("Metadaten_Geraete_Niederschlagshoehe") or n.startswith("Metadaten_Geraete_Niederschlag"):
                    h, rows = parse_meta(t)
                    for r in rows:
                        d = dict(zip(h, r))
                        dev.append((d.get("Von_Datum") or d.get("von_datum", ""), d.get("Bis_Datum") or d.get("bis_datum", "") or "29991231",
                                    d.get("Geraetetyp Name") or d.get("Geraetetyp_Name") or ""))
                elif n.startswith("Metadaten_Parameter") and ptxt is None:
                    ptxt = t
                elif n.startswith("produkt_nieder_tag"):
                    lines = t.splitlines()
                    h = [c.strip() for c in lines[0].split(";")]
                    i_d, i_rs, i_q = h.index("MESS_DATUM"), h.index("RS"), h.index("QN_6")
                    for line in lines[1:]:
                        c = [x.strip() for x in line.split(";")]
                        if len(c) <= i_rs:
                            continue
                        day = c[i_d]
                        if not (str(Y0) <= day[:4] <= str(Y1)):
                            continue
                        fl[c[i_q]] += 1
                        if c[i_rs] != "-999":          # the only test made on a value: is it the missing-value code?
                            days[c[i_q]].add(day)
        return sid, geo, dev, days, fl, ptxt

    with ThreadPoolExecutor(max_workers=6) as ex:
        for n, (sid, geo, dev, days, fl, ptxt) in enumerate(ex.map(one, sorted(files)), 1):
            flags.update(fl)
            if ptxt and not param_text:
                param_text["example_station"] = sid; param_text["text"] = ptxt
            # versions: geography periods intersected with instrument periods
            dev = sorted(set(dev)) or [("18000101", "29991231", "unknown")]
            versions = []
            for g in sorted(set(geo)):
                for d in dev:
                    fr, to = max(g[0], d[0]), min(g[1], d[1])
                    if fr <= to:
                        versions.append((f"{fr[:4]}-{fr[4:6]}-{fr[6:8]}", f"{to[:4]}-{to[4:6]}-{to[6:8]}", g[2], g[3], g[4] if g[4] == g[4] else None, d[2]))
            for k, per in enumerate(split_positions(versions)):
                if per["to"] < f"{Y0}-01-01" or per["from"] > f"{Y1}-12-31" or not in_box(per["lat"], per["lon"]):
                    continue
                series.append({"series_id": f"DWD-{sid}-{k}", "network": "DWD", "station_id": sid, "name": stations[sid], "lat": per["lat"], "lon": per["lon"],
                               "height": per["height"], "from": per["from"], "to": per["to"], "instrument": per["label"], "split_reason": per["reason"]})
            for q, ds in days.items():
                for d in ds:
                    counts[sid][f"{d[:4]}-{d[4:6]}-{d[6:8]}"] += 1
            if n % 100 == 0:
                log(f"DWD files read for {n}/{len(files)} stations")
    if param_text:
        open(os.path.join(META, f"dwd_Metadaten_Parameter_example_{param_text['example_station']}.txt"), "w", encoding="utf-8").write(param_text["text"])
    return series, counts, {"QN_6": dict(flags.most_common())}, {"see": "Metadaten_Parameter and the DESCRIPTION pdf in data/gauges/meta"}


def main():
    os.makedirs(META, exist_ok=True)
    t0 = time.time()
    s1, c1, f1, w1 = dmi()
    s2, c2, f2, w2 = dwd()
    series = s1 + s2
    counts = {**{("DMI", k): v for k, v in c1.items()}, **{("DWD", k): v for k, v in c2.items()}}
    # days with a value, per series and year (a day counts once, inside the series' own period)
    rows, valid = [], []
    for s in series:
        cs = counts.get((s["network"], s["station_id"]), {})
        per_year = Counter(d[:4] for d in cs if s["from"] <= d <= s["to"])
        good = 0
        for y in range(Y0, Y1 + 1):
            n = per_year.get(str(y), 0)
            ndays = 366 if y % 4 == 0 else 365
            if n:
                rows.append({"series_id": s["series_id"], "year": y, "days_with_value": n, "days_in_year": ndays})
            if n >= 0.9 * ndays:
                good += 1
        s["complete_years"] = good
        if good >= 3:
            valid.append(s["series_id"])
    cols = ["series_id", "network", "station_id", "name", "lat", "lon", "height", "from", "to", "instrument", "split_reason", "complete_years"]
    with open(os.path.join(OUT, "series.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n"); w.writeheader(); w.writerows(sorted(series, key=lambda s: s["series_id"]))
    with open(os.path.join(OUT, "day_counts.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["series_id", "year", "days_with_value", "days_in_year"], lineterminator="\n"); w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["series_id"], r["year"])))
    open(os.path.join(OUT, "valid_series.csv"), "w").write("series_id\n" + "\n".join(sorted(valid)) + "\n")
    json.dump({"DMI": f1, "DWD": f2}, open(os.path.join(OUT, "flags.json"), "w"), indent=1)
    json.dump({"DMI": w1, "DWD": w2}, open(os.path.join(OUT, "windows.json"), "w"), indent=1)
    with open(os.path.join(OUT, "downloads.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["url", "bytes", "sha256"]); w.writerows(sorted(downloads))
    by_net = Counter(s["network"] for s in series); val_net = Counter(v.split("-")[0] for v in valid)
    log(f"series: {dict(by_net)}; valid (>=3 complete years): {dict(val_net)}")
    log(f"split reasons: {dict(Counter((s['network'], s['split_reason']) for s in series))}")
    mp = os.path.join(ROOT, "data", "manifest.json")
    man = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"files": {}}
    for root, _, fs in os.walk(OUT):
        for f in fs:
            p = os.path.join(root, f); rel = os.path.relpath(p, os.path.join(ROOT, "data"))
            man["files"][rel] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p), "what": "step 2: gauge list, day counts and metadata (tools/gauges.py)"}
    json.dump(man, open(mp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True); open(mp, "a").write("\n")
    log(f"done in {round(time.time() - t0)} s")


if __name__ == "__main__":
    main()
