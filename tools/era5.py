#!/usr/bin/env python3
"""Step 3 of the order of work in METHOD.md: ERA5 for every gauge and farm cell, summed over each gauge network's day window.

  python3 tools/era5.py prepare      land-sea mask, and the cells: nearest land cell (R) and nearest cell (wind) for every
                                     valid gauge series, and every cell holding a turbine point (100 m wind for R13)
  python3 tools/era5.py year 1991    hourly ERA5 for one year (plus the hours either side), reduced to day windows

Reads no rain-gauge value. ERA5 comes from the Copernicus Climate Data Store (CC BY 4.0); the key is the GitHub secret
CDSAPI_KEY and is never written to the repository. The raw hourly downloads are too large to keep (about 4 GB): their
SHA-256 is listed in data/era5/downloads_<year>.csv, and the reduced day values are committed.

Day windows (CHANGELOG 2026-10-03, check 2): an hourly ERA5 value at time t is the amount in the hour ending at t.
  DMI         D 00:00 to D+1 00:00 Danish local time
  DWD_UTC06   D 06:00 to D+1 06:00 UTC                       (automatic stations)
  DWD_LT0730  D 07:30 to D+1 07:30 legal local time (CET/CEST) (manual stations)
Window ends are converted to UTC and rounded to the nearest hour, halves down; a day sums the hours t with start < t <= end.
"""
import csv, datetime as dt, hashlib, io, json, lzma, math, os, sys, tempfile, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "era5")
AREA = [58.5, 4.0, 52.8, 13.5]          # N, W, S, E
LOCAL = ZoneInfo("Europe/Copenhagen")   # same rules as German legal time
UTC = dt.timezone.utc
TYPES = ("DMI", "DWD_UTC06", "DWD_LT0730")
SINGLE = ["total_precipitation", "10m_u_component_of_wind", "10m_v_component_of_wind",
          "100m_u_component_of_wind", "100m_v_component_of_wind"]


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ windows
def round_hour(t):
    """UTC datetime rounded to the nearest whole hour, halves down."""
    base = t.replace(minute=0, second=0, microsecond=0)
    return base + dt.timedelta(hours=1) if (t - base).total_seconds() > 1800 else base


def window(kind, day):
    """(start, end) in UTC for the daily value of `day` in network window `kind`."""
    nxt = day + dt.timedelta(days=1)
    if kind == "DMI":
        a = dt.datetime.combine(day, dt.time(0, 0), LOCAL); b = dt.datetime.combine(nxt, dt.time(0, 0), LOCAL)
    elif kind == "DWD_UTC06":
        a = dt.datetime.combine(day, dt.time(6, 0), UTC); b = dt.datetime.combine(nxt, dt.time(6, 0), UTC)
    elif kind == "DWD_LT0730":
        a = dt.datetime.combine(day, dt.time(7, 30), LOCAL); b = dt.datetime.combine(nxt, dt.time(7, 30), LOCAL)
    else:
        raise ValueError(kind)
    return round_hour(a.astimezone(UTC)), round_hour(b.astimezone(UTC))


# ------------------------------------------------------------------ CDS
def cds_client():
    import cdsapi
    key = os.environ.get("CDSAPI_KEY", "").strip()
    if not key:
        sys.exit("CDSAPI_KEY is not set")
    return cdsapi.Client(url="https://cds.climate.copernicus.eu/api", key=key, quiet=True, progress=False)


def retrieve(client, dataset, req, tag, downloads):
    for attempt in range(4):
        try:
            with tempfile.NamedTemporaryFile(suffix=".dl", delete=False) as fh:
                path = fh.name
            client.retrieve(dataset, req, path)
            b = open(path, "rb").read(); os.unlink(path)
            downloads.append([tag, dataset, len(b), hashlib.sha256(b).hexdigest()])
            return b
        except Exception as e:
            log(f"  retry {tag}: {str(e)[:200]}")
            if attempt == 3:
                raise
            time.sleep(60 * (attempt + 1))


def open_nc(b):
    """CDS NetCDF, possibly zipped (one file per step type). Returns one merged xarray Dataset."""
    import xarray as xr
    parts = []
    if b[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(b))
        blobs = [z.read(n) for n in z.namelist() if n.endswith(".nc")]
    else:
        blobs = [b]
    for blob in blobs:
        with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as fh:
            fh.write(blob); p = fh.name
        ds = xr.open_dataset(p).load(); os.unlink(p)
        if "valid_time" in ds.dims or "valid_time" in ds.coords:
            ds = ds.rename({"valid_time": "time"})
        for d in ("number", "expver", "pressure_level"):
            if d in ds.dims and ds.sizes[d] == 1:
                ds = ds.squeeze(d, drop=True)
            elif d in ds.coords and d not in ds.dims:
                ds = ds.drop_vars(d)
        parts.append(ds)
    return xr.merge(parts, compat="override", join="outer")


def base_req(times):
    return {"product_type": ["reanalysis"], "area": AREA, "data_format": "netcdf", "download_format": "unarchived",
            "time": [f"{h:02d}:00" for h in range(24)], **times}


# ------------------------------------------------------------------ prepare
def prepare():
    import numpy as np
    os.makedirs(OUT, exist_ok=True)
    client = cds_client()
    downloads = []
    b = retrieve(client, "reanalysis-era5-single-levels",
                 base_req({"variable": ["land_sea_mask"], "year": ["2020"], "month": ["01"], "day": ["01"], "time": ["00:00"]}),
                 "lsm", downloads)
    ds = open_nc(b)
    lsm = ds["lsm"].isel(time=0).values if "time" in ds["lsm"].dims else ds["lsm"].values
    lat, lon = ds["latitude"].values, ds["longitude"].values
    cells = [(i, j, float(lat[i]), float(lon[j]), float(lsm[i, j])) for i in range(len(lat)) for j in range(len(lon))]
    with open(os.path.join(OUT, "grid.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["cell", "lat", "lon", "lsm"])
        for i, j, a, o, m in cells:
            w.writerow([f"{i}_{j}", a, o, round(m, 4)])

    def nearest(la, lo, land):
        best, bd = None, 1e18
        for i, j, a, o, m in cells:
            if land and m < 0.5:
                continue
            d = (a - la) ** 2 + ((o - lo) * math.cos(math.radians(la))) ** 2
            if d < bd:
                best, bd = f"{i}_{j}", d
        return best

    valid = set(l.strip() for l in open(os.path.join(ROOT, "data", "gauges", "valid_series.csv")) if l[:3] in ("DMI", "DWD"))
    rows = []
    for s in csv.DictReader(open(os.path.join(ROOT, "data", "gauges", "series.csv"), encoding="utf-8")):
        if s["series_id"] not in valid:
            continue
        la, lo = float(s["lat"]), float(s["lon"])
        rows.append({"series_id": s["series_id"], "network": s["network"], "cell_r": nearest(la, lo, True), "cell_w": nearest(la, lo, False)})
    with open(os.path.join(OUT, "series_cells.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["series_id", "network", "cell_r", "cell_w"], lineterminator="\n"); w.writeheader(); w.writerows(rows)
    farm = sorted({nearest(float(t["lat"]), float(t["lon"]), False) for t in csv.DictReader(open(os.path.join(ROOT, "data", "turbines.csv"), encoding="utf-8"))
                   if AREA[2] <= float(t["lat"]) <= AREA[0] and AREA[1] <= float(t["lon"]) <= AREA[3]})
    open(os.path.join(OUT, "farm_cells.csv"), "w").write("cell\n" + "\n".join(farm) + "\n")
    with open(os.path.join(OUT, "downloads_prepare.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["tag", "dataset", "bytes", "sha256"]); w.writerows(downloads)
    log(f"grid {len(lat)}x{len(lon)}, valid series {len(rows)}, R cells {len({r['cell_r'] for r in rows})}, "
        f"wind cells {len({r['cell_w'] for r in rows})}, farm cells {len(farm)}")


# ------------------------------------------------------------------ one year
def year(y):
    import numpy as np
    client = cds_client()
    sc = list(csv.DictReader(open(os.path.join(OUT, "series_cells.csv"))))
    kinds_r, kinds_w = {}, {}
    for r in sc:
        ks = ("DMI",) if r["network"] == "DMI" else ("DWD_UTC06", "DWD_LT0730")
        kinds_r.setdefault(r["cell_r"], set()).update(ks); kinds_w.setdefault(r["cell_w"], set()).update(ks)
    farm = [l.strip() for l in open(os.path.join(OUT, "farm_cells.csv")) if "_" in l]

    # requests: the 12 months, plus 31 Dec of the year before and 1-2 Jan of the year after (windows reach across)
    jobs = []
    months = range(1, int(os.environ.get("ERA5_TEST_MONTHS", "12")) + 1)
    for m in months:
        jobs.append((f"{y}-{m:02d}", {"year": [str(y)], "month": [f"{m:02d}"], "day": [f"{d:02d}" for d in range(1, 32)]}))
    jobs.append((f"{y - 1}-12-31", {"year": [str(y - 1)], "month": ["12"], "day": ["31"]}))
    jobs.append((f"{y + 1}-01-01", {"year": [str(y + 1)], "month": ["01"], "day": ["01", "02"]}))
    downloads, parts = [], []

    def one(job):
        tag, t = job
        s = retrieve(client, "reanalysis-era5-single-levels", base_req({**t, "variable": SINGLE}), "single " + tag, downloads)
        p = retrieve(client, "reanalysis-era5-pressure-levels", base_req({**t, "variable": ["u_component_of_wind", "v_component_of_wind"],
                                                                            "pressure_level": ["850"]}), "p850 " + tag, downloads)
        a, b = open_nc(s), open_nc(p).rename({"u": "u850", "v": "v850"})
        log(f"  {tag}: {a.sizes.get('time')} h")
        return a.merge(b[["u850", "v850"]], compat="override", join="inner")

    import xarray as xr
    with ThreadPoolExecutor(max_workers=4) as ex:
        parts = list(ex.map(one, jobs))
    ds = xr.concat(parts, dim="time").sortby("time")
    _, idx = np.unique(ds["time"].values, return_index=True)
    ds = ds.isel(time=idx)
    times = [dt.datetime.utcfromtimestamp(t.astype("datetime64[s]").astype(int)).replace(tzinfo=UTC) for t in ds["time"].values]
    pos = {t: k for k, t in enumerate(times)}
    lat, lon = ds["latitude"].values, ds["longitude"].values
    arr = {v: ds[v].values for v in ("tp", "u10", "v10", "u100", "v100", "u850", "v850")}
    ws100 = np.hypot(arr["u100"], arr["v100"])

    def idx_for(kind, day):
        a, b = window(kind, day)
        out, t = [], a + dt.timedelta(hours=1)
        while t <= b:
            if t not in pos:
                raise RuntimeError(f"missing ERA5 hour {t} for {kind} {day}")
            out.append(pos[t]); t += dt.timedelta(hours=1)
        return out

    days = [dt.date(y, 1, 1) + dt.timedelta(days=k) for k in range((dt.date(y + 1, 1, 1) - dt.date(y, 1, 1)).days)]
    if len(months) < 12:   # test mode: only the days the fetched months cover
        days = [d for d in days if d.month <= len(months) and not (d.month == len(months) and d.day == max(x.day for x in days if x.month == len(months)))]
    win = {(k, d): idx_for(k, d) for k in TYPES for d in days}
    ij = lambda c: tuple(int(x) for x in c.split("_"))
    gbuf, fbuf = io.StringIO(), io.StringIO()
    gbuf.write("kind,cell,date,R_mm,u850,v850,u10,v10\n"); fbuf.write("kind,cell,date,ws100_mean,hours_3_25\n")
    gcells = sorted(set(kinds_r) | set(kinds_w))
    for c in gcells:
        i, j = ij(c)
        for k in sorted(kinds_r.get(c, set()) | kinds_w.get(c, set())):
            for d in days:
                w = win[(k, d)]
                r = arr["tp"][w, i, j].sum() * 1000.0
                gbuf.write(f"{k},{c},{d.isoformat()},{r:.2f},{arr['u850'][w, i, j].mean():.2f},{arr['v850'][w, i, j].mean():.2f},"
                           f"{arr['u10'][w, i, j].mean():.2f},{arr['v10'][w, i, j].mean():.2f}\n")
    for c in farm:
        i, j = ij(c)
        for k in TYPES:
            for d in days:
                w = win[(k, d)]
                s = ws100[w, i, j]
                fbuf.write(f"{k},{c},{d.isoformat()},{s.mean():.2f},{int(((s >= 3) & (s <= 25)).sum())}\n")
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, f"gauge_days_{y}.csv.xz"), "wb").write(lzma.compress(gbuf.getvalue().encode(), preset=9))
    open(os.path.join(OUT, f"farm_days_{y}.csv.xz"), "wb").write(lzma.compress(fbuf.getvalue().encode(), preset=9))
    with open(os.path.join(OUT, f"downloads_{y}.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["tag", "dataset", "bytes", "sha256"]); w.writerows(sorted(downloads))
    log(f"year {y}: {len(times)} hours, {len(gcells)} gauge cells, {len(farm)} farm cells")


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "year":
        year(int(sys.argv[2]))
