#!/usr/bin/env python3
"""Step 3 of the order of work in METHOD.md: ERA5 for every gauge and farm cell, summed over each gauge network's day window.

  python3 tools/era5.py prepare      land-sea mask, and the cells: nearest land cell (R) and nearest cell (wind) for every
                                     valid gauge series, and every cell holding a turbine point (100 m wind for R13)
  python3 tools/era5.py run 300      fetch whole years one at a time (CDS limits queued requests per dataset), reduce each
                                     year to day windows once the next year is in, and stop when the time budget is used;
                                     the next scheduled run carries on from the GitHub Actions cache

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
    b = retrieve_once(client, "reanalysis-era5-single-levels",
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


# ------------------------------------------------------------------ hourly years, fetched one at a time
RAWDIR = os.path.join(ROOT, "era5_raw")          # GitHub Actions cache between runs, never committed
QUEUE_MSG = "Number queued requests"


def retrieve_patient(client, dataset, req, tag, downloads, deadline):
    """CDS allows only a few queued requests per dataset and user. A rejection for that reason is not a failure:
    wait and submit again, until the run's deadline."""
    while True:
        try:
            return retrieve_once(client, dataset, req, tag, downloads)
        except Exception as e:
            msg = str(e)
            if QUEUE_MSG in msg and time.time() + 900 < deadline:
                log(f"  {tag}: CDS queue limit, waiting 10 min"); time.sleep(600); continue
            raise


def retrieve_once(client, dataset, req, tag, downloads):
    with tempfile.NamedTemporaryFile(suffix=".dl", delete=False) as fh:
        path = fh.name
    t0 = time.time()
    client.retrieve(dataset, req, path)
    b = open(path, "rb").read(); os.unlink(path)
    downloads.append([tag, dataset, len(b), hashlib.sha256(b).hexdigest()])
    log(f"  {tag}: {len(b) / 1e6:.1f} MB in {round((time.time() - t0) / 60)} min")
    return b


def fetch_split(client, dataset, extra, y, months, tag, downloads, deadline):
    """Months of year y from one dataset. CDS caps the size of one request ("cost limits exceeded"): a rejected
    selection is split in two by months, as often as needed. Returns one Dataset."""
    import xarray as xr
    days = ["01"] if y == 2026 else [f"{d:02d}" for d in range(1, 32)]
    req = base_req({"year": [str(y)], "month": [f"{m:02d}" for m in months], "day": days, **extra})
    try:
        return open_nc(retrieve_patient(client, dataset, req, f"{tag} {y} {months[0]:02d}-{months[-1]:02d}", downloads, deadline))
    except Exception as e:
        if "cost limits exceeded" in str(e) and len(months) > 1:
            h = len(months) // 2
            log(f"  {tag} {y}: too large, splitting {months[0]:02d}-{months[-1]:02d}")
            return xr.concat([fetch_split(client, dataset, extra, y, months[:h], tag, downloads, deadline),
                              fetch_split(client, dataset, extra, y, months[h:], tag, downloads, deadline)], dim="time")
        raise


def fetch(client, y, deadline):
    """Year y in full (y = 2026: only 1 January, which the 31 December windows of 2025 reach into).
    The two datasets run side by side; within a dataset, requests go one at a time."""
    months = [1] if y == 2026 else list(range(1, 13))
    downloads = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        fs = ex.submit(fetch_split, client, "reanalysis-era5-single-levels", {"variable": SINGLE}, y, months, "single", downloads, deadline)
        fp = ex.submit(fetch_split, client, "reanalysis-era5-pressure-levels",
                       {"variable": ["u_component_of_wind", "v_component_of_wind"], "pressure_level": ["850"]}, y, months, "p850", downloads, deadline)
        a, b = fs.result(), fp.result().rename({"u": "u850", "v": "v850"})
    ds = a.merge(b[["u850", "v850"]], compat="override", join="inner")
    os.makedirs(RAWDIR, exist_ok=True)
    ds.to_netcdf(os.path.join(RAWDIR, f"{y}.nc"))
    with open(os.path.join(RAWDIR, f"downloads_{y}.csv"), "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["tag", "dataset", "bytes", "sha256"]); w.writerows(sorted(downloads))
    log(f"year {y} fetched: {ds.sizes.get('time')} hours")


def process(y):
    """Day windows for year y, from the hourly files of y and y + 1."""
    import numpy as np, xarray as xr
    sc = list(csv.DictReader(open(os.path.join(OUT, "series_cells.csv"))))
    kinds_r, kinds_w = {}, {}
    for r in sc:
        ks = ("DMI",) if r["network"] == "DMI" else ("DWD_UTC06", "DWD_LT0730")
        kinds_r.setdefault(r["cell_r"], set()).update(ks); kinds_w.setdefault(r["cell_w"], set()).update(ks)
    farm = [l.strip() for l in open(os.path.join(OUT, "farm_cells.csv")) if "_" in l]
    a = xr.open_dataset(os.path.join(RAWDIR, f"{y}.nc")).load()
    b = xr.open_dataset(os.path.join(RAWDIR, f"{y + 1}.nc")).load()
    b = b.sel(time=b["time"] < np.datetime64(f"{y + 1}-01-02T00:00"))
    ds = xr.concat([a, b], dim="time").sortby("time")
    _, idx = np.unique(ds["time"].values, return_index=True)
    ds = ds.isel(time=idx)
    times = [dt.datetime.fromtimestamp(int(t.astype("datetime64[s]").astype("int64")), UTC) for t in ds["time"].values]
    pos = {t: k for k, t in enumerate(times)}
    arr = {v: ds[v].values for v in ("tp", "u10", "v10", "u100", "v100", "u850", "v850")}
    ws100 = np.hypot(arr["u100"], arr["v100"])

    def idx_for(kind, day):
        a_, b_ = window(kind, day)
        out, t = [], a_ + dt.timedelta(hours=1)
        while t <= b_:
            if t not in pos:
                raise RuntimeError(f"missing ERA5 hour {t} for {kind} {day}")
            out.append(pos[t]); t += dt.timedelta(hours=1)
        return out

    days = [dt.date(y, 1, 1) + dt.timedelta(days=k) for k in range((dt.date(y + 1, 1, 1) - dt.date(y, 1, 1)).days)]
    win = {(k, d): idx_for(k, d) for k in TYPES for d in days}
    ij = lambda c: tuple(int(x) for x in c.split("_"))
    g, f = ["kind,cell,date,R_mm,u850,v850,u10,v10"], ["kind,cell,date,ws100_mean,hours_3_25"]
    gcells = sorted(set(kinds_r) | set(kinds_w))
    for c in gcells:
        i, j = ij(c)
        for k in sorted(kinds_r.get(c, set()) | kinds_w.get(c, set())):
            for d in days:
                w = win[(k, d)]
                g.append(f"{k},{c},{d.isoformat()},{arr['tp'][w, i, j].sum() * 1000.0:.2f},{arr['u850'][w, i, j].mean():.2f},"
                         f"{arr['v850'][w, i, j].mean():.2f},{arr['u10'][w, i, j].mean():.2f},{arr['v10'][w, i, j].mean():.2f}")
    for c in farm:
        i, j = ij(c)
        for k in TYPES:
            for d in days:
                s = ws100[win[(k, d)], i, j]
                f.append(f"{k},{c},{d.isoformat()},{s.mean():.2f},{int(((s >= 3) & (s <= 25)).sum())}")
    open(os.path.join(OUT, f"gauge_days_{y}.csv.xz"), "wb").write(lzma.compress(("\n".join(g) + "\n").encode(), preset=9))
    open(os.path.join(OUT, f"farm_days_{y}.csv.xz"), "wb").write(lzma.compress(("\n".join(f) + "\n").encode(), preset=9))
    for yy in (y, y + 1):
        src = os.path.join(RAWDIR, f"downloads_{yy}.csv")
        if os.path.exists(src):
            open(os.path.join(OUT, f"downloads_{yy}.csv"), "w").write(open(src).read())
    log(f"year {y} processed: {len(gcells)} gauge cells, {len(farm)} farm cells, {len(days)} days")


def run(budget_min):
    """Fetch and process years in order until the time budget is used; the next run carries on."""
    deadline = time.time() + budget_min * 60
    client = cds_client()
    done = lambda y: os.path.exists(os.path.join(OUT, f"gauge_days_{y}.csv.xz"))
    raw = lambda y: os.path.exists(os.path.join(RAWDIR, f"{y}.nc"))
    for y in range(1991, 2027):
        need = (y <= 2025 and not done(y)) or (y - 1 >= 1991 and not done(y - 1))
        if need and not raw(y):
            if time.time() > deadline - 90 * 60:
                log("time budget used: stopping before a new year"); break
            fetch(client, y, deadline)
        if y - 1 >= 1991 and not done(y - 1) and raw(y - 1) and raw(y):
            process(y - 1)
        if y - 1 >= 1991 and done(y - 1) and raw(y - 1):
            os.unlink(os.path.join(RAWDIR, f"{y - 1}.nc"))
    log("years done: " + ",".join(str(y) for y in range(1991, 2026) if done(y)))


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 300)
