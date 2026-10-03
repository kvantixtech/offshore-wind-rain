#!/usr/bin/env python3
"""Step 1 of the order of work in METHOD.md: offshore turbines and farms, with capacity per day.

Sources (no rain data is read here):
  - Energistyrelsen, Stamdataregister for vindkraftanlæg: "Vinddata.xlsx" (turbines in the register now)
    and "Historiske vinddata.xlsx" (decommissioned turbines). Offshore = "Type af placering" HAV.
  - Marktstammdatenregister, full export, member EinheitenWind.xml, read with HTTP range requests.
    Offshore = WindAnLandOderAufSee 889 ("Windenergie auf See").
  - EMODnet Human Activities, layer emodnet:windfarmspoly: farm names and polygons.
  - data/farms_manual.csv: dates with sources for farms that have no turbine register here (Dutch, Swedish).
  - DMI and DWD station lists (metadata only), to know which farms lie within 150 km of a station.

Writes data/turbines.csv, data/farms.csv, data/farms_check.json, data/raw/*, and updates data/manifest.json.
"""
import csv, datetime as dt, hashlib, io, json, lzma, math, os, re, sys, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rangezip import RangeFile
import openpyxl
from pyproj import Transformer
from shapely.geometry import shape, Point
from shapely.ops import transform as shp_transform
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, RAW = os.path.join(ROOT, "data"), os.path.join(ROOT, "data", "raw")
UA = "kvantixtech offshore-wind-rain (github actions; validation@kvantix.tech)"
BOX = (4.5, 53.3, 13.0, 57.9)                      # lon/lat box of METHOD.md
ENS = {"ens_vinddata.xlsx": "https://ens.dk/media/8748/download",
       "ens_historiske_vinddata.xlsx": "https://ens.dk/media/8746/download"}
MASTR_PAGE = "https://www.marktstammdatenregister.de/MaStR/Datendownload"
EMODNET = "https://ows.emodnet-humanactivities.eu/wfs?" + urllib.parse.urlencode(
    {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "emodnet:windfarmspoly",
     "outputFormat": "application/json", "srsName": "EPSG:4326"})
DMI_STATIONS = "https://opendataapi.dmi.dk/v2/climateData/collections/station/items?bbox=4.5,53.3,13.0,57.9&limit=10000"
DWD_STATIONS = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/more_precip/historical/RR_Tageswerte_Beschreibung_Stationen.txt"
END_2025 = dt.date(2025, 12, 31)
manifest_add = {}
to3035 = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True).transform
utm32 = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True).transform


def log(*a):
    print(*a, flush=True)


def http(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=600) as r:
                return r.read(), dict(r.headers)
        except Exception:
            if attempt == 4:
                raise
            time.sleep(10 * (attempt + 1))


def save_raw(name, b, url, what):
    p = os.path.join(RAW, name)
    open(p, "wb").write(b)
    manifest_add["raw/" + name] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "source": url, "what": what,
                                   "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(".", "").replace(",", ".") if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$", str(v).strip())
                     else str(v).strip().replace(",", "."))
    except ValueError:
        return None


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


# ------------------------------------------------------------------ Danish register
def ens_turbines():
    out, report = {}, {}
    for name, url in ENS.items():
        b, h = http(url)
        save_raw(name, b, url, "Energistyrelsen, Stamdataregister for vindkraftanlæg (" + (h.get("Content-Disposition") or name) + ")")
        wb = openpyxl.load_workbook(io.BytesIO(b), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        hi = next(i for i, r in enumerate(rows) if any(norm(c) == "møllenummer (gsrn)" for c in r if c))
        head = [norm(c) for c in rows[hi]]
        col = lambda pat: next(i for i, c in enumerate(head) if re.search(pat, c))
        c_id, c_con, c_dec, c_kw = col(r"gsrn"), col(r"oprindelig nettilslutning"), col(r"afmeldning"), col(r"kapacitet")
        c_x, c_y = col(r"x.*koordinat"), col(r"y.*koordinat")
        c_park = next((i for i, c in enumerate(head) if "parknummer" in c), None)
        body = [r for r in rows[hi + 1:] if r and r[c_id]]
        # the location-type column is the one whose values are LAND/HAV (headers and values are swapped in one file)
        c_type = max(range(len(head)), key=lambda i: sum(1 for r in body[:2000] if i < len(r) and str(r[i]).strip().upper() in ("LAND", "HAV")))
        n_hav = n_bad = 0
        for r in body:
            if str(r[c_type]).strip().upper() != "HAV":
                continue
            n_hav += 1
            x, y = num(r[c_x]), num(r[c_y])
            gsrn = str(r[c_id]).strip()
            if not x or not y or (abs(x - 500000) < 1 and abs(y - 6250000) < 1):
                n_bad += 1
                report.setdefault("dropped_no_position", []).append(gsrn)
                continue
            lon, lat = utm32(x, y)
            rec = {"turbine_id": "DK-" + gsrn, "register": "ENS", "register_park": str(r[c_park] or "").strip() if c_park is not None else "",
                   "lat": round(lat, 6), "lon": round(lon, 6), "mw": (num(r[c_kw]) or 0) / 1000,
                   "start": parse_date(r[c_con]), "end": parse_date(r[c_dec]), "file": name}
            if rec["turbine_id"] not in out or name == "ens_vinddata.xlsx":
                out[rec["turbine_id"]] = rec
        report[name] = {"header_row": hi + 1, "rows": len(body), "offshore_rows": n_hav, "dropped_no_position": n_bad,
                        "location_type_column": rows[hi][c_type]}
        log(f"ENS {name}: {len(body)} turbines, {n_hav} offshore, {n_bad} without position")
    return list(out.values()), report


# ------------------------------------------------------------------ German register
def mastr_turbines():
    page, _ = http(MASTR_PAGE)
    url = sorted(set(re.findall(r'https://download\.marktstammdatenregister\.de/[^"\']+\.zip', page.decode("utf-8", "replace"))))[0]
    rf = RangeFile(url, UA)
    z = zipfile.ZipFile(io.BufferedReader(rf, buffer_size=1 << 20))
    info = z.getinfo("EinheitenWind.xml")
    units, fields = [], []
    with z.open("EinheitenWind.xml") as fh:
        for ev, el in ET.iterparse(fh):
            if el.tag == "EinheitWind":
                d = {c.tag: (c.text or "") for c in el}
                if d.get("WindAnLandOderAufSee") == "889":
                    units.append(d)
                    for k in d:
                        if k not in fields:
                            fields.append(k)
                el.clear()
    units.sort(key=lambda d: d.get("EinheitMastrNummer", ""))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n"); w.writeheader(); w.writerows(units)
    raw = lzma.compress(buf.getvalue().encode("utf-8"), preset=9)
    save_raw("mastr_offshore_units.csv.xz", raw, url,
             f"Marktstammdatenregister full export, member EinheitenWind.xml (CRC {info.CRC:08x}, {info.file_size} bytes): every unit with WindAnLandOderAufSee = 889, all fields, unchanged")
    out, dropped = [], []
    for d in units:
        lat, lon = num(d.get("Breitengrad")), num(d.get("Laengengrad"))
        start = parse_date(d.get("Inbetriebnahmedatum"))
        if not lat or not lon or not start:
            dropped.append({"id": d.get("EinheitMastrNummer"), "park": d.get("NameWindpark"), "status": d.get("EinheitBetriebsstatus"),
                            "reason": "no position" if not lat or not lon else "no commissioning date"})
            continue
        out.append({"turbine_id": "DE-" + d["EinheitMastrNummer"], "register": "MaStR", "register_park": d.get("NameWindpark", ""),
                    "lat": round(lat, 6), "lon": round(lon, 6), "mw": (num(d.get("Nettonennleistung")) or 0) / 1000,
                    "start": start, "end": parse_date(d.get("DatumEndgueltigeStilllegung")), "file": "mastr_offshore_units.csv.xz",
                    "sea": {"640": "North Sea", "639": "Skagerrak-Kattegat-Baltic"}.get(d.get("Seelage"), "")})
    log(f"MaStR: {len(units)} offshore units, {len(out)} with position and date, {len(dropped)} left out")
    return out, {"zip": url, "member_crc": f"{info.CRC:08x}", "member_bytes": info.file_size, "bytes_fetched": rf.fetched,
                 "offshore_units": len(units), "used": len(out), "left_out": dropped}


# ------------------------------------------------------------------ stations (metadata only)
def stations():
    pts = set()
    b, _ = http(DMI_STATIONS)
    for f in json.loads(b)["features"]:
        if "acc_precip" in (f["properties"].get("parameterId") or []):
            pts.add(tuple(round(c, 4) for c in f["geometry"]["coordinates"][:2]))
    b, _ = http(DWD_STATIONS)
    for line in b.decode("latin-1").splitlines()[2:]:
        p = line.split()
        if len(p) > 6:
            lat, lon = float(p[4]), float(p[5])
            if BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]:
                pts.add((round(lon, 4), round(lat, 4)))
    pts = [p for p in pts if BOX[0] <= p[0] <= BOX[2] and BOX[1] <= p[1] <= BOX[3]]
    log(f"stations with precipitation in the box (any period): {len(pts)}")
    return [Point(to3035(*p)) for p in pts]


# ------------------------------------------------------------------ groups for randomization inference (METHOD.md)
def group_of(farm, country, lat, lon, sea):
    n = farm.lower()
    if "horns rev" in n: return "Horns Rev"
    if "vesterhav" in n: return "Vesterhav"
    if n.startswith("thor"): return "Thor"
    if country == "Netherlands": return "Dutch farms"
    if country == "Sweden" or "lillgrund" in n: return "Lillgrund"
    if "nysted" in n or "rødsand" in n or "rodsand" in n: return "Nysted and Rødsand"
    if "anholt" in n: return "Anholt"
    if "kriegers" in n or re.search(r"\bbaltic ?[12]\b|baltic 1|baltic 2", n): return "Kriegers Flak and Baltic 1/2"
    if country == "Germany":
        if sea == "North Sea": return "German Bight north of 54.3N" if lat >= 54.3 else "German Bight south of 54.3N"
        return "Other German Baltic farms"
    return "Other Danish inner-water farms"


def main():
    os.makedirs(RAW, exist_ok=True)
    t0 = time.time()
    dk, dk_rep = ens_turbines()
    de, de_rep = mastr_turbines()
    eb, _ = http(EMODNET)
    save_raw("emodnet_windfarmspoly.geojson.xz", lzma.compress(eb, preset=9), EMODNET, "EMODnet Human Activities, wind farm polygons (WFS GetFeature, GeoJSON), xz-compressed")
    em = [f for f in json.loads(eb)["features"] if f.get("geometry")]
    polys = []
    for f in em:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        polys.append((f["properties"], g, shp_transform(to3035, g)))
    st = stations()
    st_tree = STRtree(st)

    def km_to_station(g3035):
        i = st_tree.nearest(g3035)
        return g3035.distance(st[i]) / 1000

    # farms in the EMODnet layer that matter: production, construction or dismantled, within 150 km of a station
    relevant = [(p, g, g3) for p, g, g3 in polys if p.get("status") in ("Production", "Construction", "Dismantled")]
    rel_dist = [km_to_station(g3) for _, _, g3 in relevant]
    poly3 = [g3 for _, _, g3 in relevant]
    ptree = STRtree(poly3)

    # assign register turbines to EMODnet farms (inside, or nearest within 2 km)
    turbines = []
    for t in dk + de:
        p3 = Point(to3035(t["lon"], t["lat"]))
        i = ptree.nearest(p3)
        d = poly3[i].distance(p3)
        props = relevant[i][0]
        t["farm"] = props["name"] if d <= 2000 else (t["register_park"] or "unmatched")
        t["farm_match_m"] = round(d)
        t["country"] = "Denmark" if t["turbine_id"].startswith("DK-") else "Germany"
        turbines.append(t)
    log(f"register turbines: {len(turbines)}; matched to an EMODnet farm within 2 km: {sum(1 for t in turbines if t['farm_match_m'] <= 2000)}")

    # farms without a turbine register here: points on a 500 m grid inside the polygon, capacity ramped between the two dates
    manual = list(csv.DictReader(open(os.path.join(DATA, "farms_manual.csv"), encoding="utf-8")))
    to4326 = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True).transform
    for m in manual:
        hit = [(p, g3) for p, g, g3 in relevant if p["name"] == m["emodnet_name"]]
        if len(hit) != 1:
            sys.exit(f"manual farm {m['emodnet_name']!r}: {len(hit)} matches in the EMODnet layer")
        p, g3 = hit[0]
        x0, y0, x1, y1 = g3.bounds
        pts = [(x, y) for x in [x0 + 250 + 500 * i for i in range(int((x1 - x0) // 500) + 1)]
               for y in [y0 + 250 + 500 * j for j in range(int((y1 - y0) // 500) + 1)] if g3.contains(Point(x, y))]
        a, b_ = dt.date.fromisoformat(m["first_power"]), dt.date.fromisoformat(m["full_commissioning"])
        end = dt.date.fromisoformat(m["decommissioned"]) if m["decommissioned"] else None
        n = len(pts)
        for k, (x, y) in enumerate(sorted(pts)):
            lon, lat = to4326(x, y)
            start = a + dt.timedelta(days=round((b_ - a).days * k / max(n - 1, 1)))
            turbines.append({"turbine_id": f"PT-{m['emodnet_name'][:12].replace(' ', '_')}-{k:04d}", "register": "polygon grid 500 m",
                             "register_park": m["emodnet_name"], "lat": round(lat, 6), "lon": round(lon, 6), "mw": float(m["capacity_mw"]) / n,
                             "start": start, "end": end, "file": "farms_manual.csv", "farm": m["emodnet_name"], "farm_match_m": 0,
                             "country": m["country"]})
        log(f"manual farm {m['emodnet_name']}: {n} grid points")

    # sea basin, distance, group
    for t in turbines:
        if not t.get("sea"):   # German turbines carry Seelage; elsewhere: west of 8.65 E is the North Sea side
            t["sea"] = "North Sea" if t["lon"] < 8.65 else "Skagerrak-Kattegat-Baltic"
        t["km_to_station"] = round(km_to_station(Point(to3035(t["lon"], t["lat"]))), 1)
        t["group"] = group_of(t["farm"], t["country"], t["lat"], t["lon"], t["sea"])
    turbines.sort(key=lambda t: t["turbine_id"])
    cols = ["turbine_id", "country", "farm", "group", "sea", "lat", "lon", "mw", "start", "end", "register", "register_park", "farm_match_m", "km_to_station", "file"]
    with open(os.path.join(DATA, "turbines.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore", lineterminator="\n"); w.writeheader()
        for t in turbines:
            w.writerow({**t, "mw": round(t["mw"], 4), "start": t["start"].isoformat() if t["start"] else "", "end": t["end"].isoformat() if t["end"] else ""})

    # farm table
    farms = {}
    for t in turbines:
        f = farms.setdefault(t["farm"], {"farm": t["farm"], "country": t["country"], "group": t["group"], "sea": t["sea"], "points": 0,
                                         "mw_total": 0.0, "mw_end_2025": 0.0, "first": None, "last": None, "decommissioned_points": 0,
                                         "min_km_to_station": 1e9, "source": t["register"]})
        f["points"] += 1; f["mw_total"] += t["mw"]
        if t["start"] and t["start"] <= END_2025 and (not t["end"] or t["end"] > END_2025):
            f["mw_end_2025"] += t["mw"]
        ds = [x for x in (f["first"], t["start"]) if x]
        f["first"] = min(ds) if ds else None
        ds = [x for x in (f["last"], t["start"]) if x]
        f["last"] = max(ds) if ds else None
        f["decommissioned_points"] += 1 if t["end"] else 0
        f["min_km_to_station"] = min(f["min_km_to_station"], t["km_to_station"])
    with open(os.path.join(DATA, "farms.csv"), "w", newline="", encoding="utf-8") as fh:
        cols = ["farm", "country", "group", "sea", "points", "mw_total", "mw_end_2025", "first", "last", "decommissioned_points", "min_km_to_station", "source"]
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n"); w.writeheader()
        for f in sorted(farms.values(), key=lambda f: (f["first"] or dt.date.max, f["farm"])):
            w.writerow({**f, "mw_total": round(f["mw_total"], 1), "mw_end_2025": round(f["mw_end_2025"], 1),
                        "first": f["first"].isoformat() if f["first"] else "", "last": f["last"].isoformat() if f["last"] else ""})

    # check 1 (METHOD.md): every relevant EMODnet farm within 150 km of a station has turbines; national totals at end of 2025
    have = set(t["farm"] for t in turbines)
    missing = [{"name": p["name"], "country": p["country"], "status": p["status"], "year": p.get("year"), "power_mw": p.get("power_mw"),
                "km_to_station": round(d, 1)} for (p, g, g3), d in zip(relevant, rel_dist) if d <= 150 and p["name"] not in have]
    totals = {}
    for t in turbines:
        if t["start"] and t["start"] <= END_2025 and (not t["end"] or t["end"] > END_2025):
            totals[t["country"]] = round(totals.get(t["country"], 0) + t["mw"], 1)
    check = {"emodnet_farms_within_150km_without_turbines": missing, "mw_in_operation_end_2025_by_country": totals,
             "turbines_by_source": {s: sum(1 for t in turbines if t["register"] == s) for s in sorted(set(t["register"] for t in turbines))},
             "unmatched_register_turbines": sorted(set((t["country"], t["register_park"]) for t in turbines if t["farm_match_m"] > 2000)),
             "ens": dk_rep, "mastr": de_rep, "seconds": round(time.time() - t0)}
    json.dump(check, open(os.path.join(DATA, "farms_check.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    log("missing farms within 150 km:", json.dumps(missing, ensure_ascii=False))
    log("MW in operation at end of 2025:", totals)

    # manifest
    mp = os.path.join(DATA, "manifest.json")
    man = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {"files": {}}
    man["files"].update(manifest_add)
    for f, what in (("turbines.csv", "Every offshore turbine point with capacity, dates, farm and group (tools/farms.py)"),
                    ("farms.csv", "Farm table: capacity, first and last commissioning, distance to the nearest station"),
                    ("farms_check.json", "Check 1 inputs: farms without turbines, national totals, what was left out"),
                    ("farms_manual.csv", "Hand-entered dates with sources for farms without a turbine register here")):
        p = os.path.join(DATA, f)
        man["files"][f] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p), "what": what}
    json.dump(man, open(mp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True); open(mp, "a").write("\n")
    log(f"done in {round(time.time() - t0)} s: {len(turbines)} turbine points, {len(farms)} farms")


if __name__ == "__main__":
    main()
