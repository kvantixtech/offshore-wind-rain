#!/usr/bin/env python3
"""Writes data/status.json: where the test stands, for the live page (kvantix.tech/playground/wind-rain/).

Computed only from what is committed: which output files exist, their counts, and the git log.
It never contains a rain-gauge value or a result number; the result goes on the page by hand,
after it has been checked. Every workflow runs this after committing its data.
"""
import csv, datetime as dt, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout.strip()


def last(path):
    """(short sha, date) of the last commit touching path, or ("", "")."""
    out = git("log", "-1", "--format=%h %cs", "--", path)
    return tuple(out.split()) if out else ("", "")


def day(iso):
    if not iso:
        return ""
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def main():
    steps, numbers = [], {}
    # 1. method
    steps.append({"key": "method", "when": "2 Oct", "commit": "0410705", "status": "done",
                  "step": "Method, rules, the four readings and the placebos, before any data. Reviewed independently first"})
    # 2. turbines and farms
    if os.path.exists(D("turbines.csv")):
        t = list(csv.DictReader(open(D("turbines.csv"), encoding="utf-8")))
        farms = {r["farm"] for r in t}
        sha, date = last("data/turbines.csv")
        numbers.update({"turbine_points": len(t), "farms": len(farms)})
        steps.append({"key": "farms", "when": day(date), "commit": sha, "status": "done",
                      "step": f"Every offshore turbine with its own dates: {len(t):,} turbine points in {len(farms)} farms. "
                              "German total matches the national statistic within 0.1 %"})
    else:
        steps.append({"key": "farms", "when": "next", "commit": "", "status": "waiting", "step": "Every offshore turbine with its own dates"})
    # 3. gauges
    if os.path.exists(D("gauges", "valid_series.csv")):
        valid = [l for l in open(D("gauges", "valid_series.csv")) if l[:3] in ("DMI", "DWD")]
        sha, date = last("data/gauges/series.csv")
        numbers.update({"gauge_series": len(valid), "gauge_series_dmi": sum(1 for v in valid if v.startswith("DMI")),
                        "gauge_series_dwd": sum(1 for v in valid if v.startswith("DWD"))})
        steps.append({"key": "gauges", "when": day(date), "commit": sha, "status": "done",
                      "step": f"Gauge list from metadata, and only a count of days with a value: {len(valid):,} usable series"})
    # 4. day windows (fixed in CHANGELOG)
    steps.append({"key": "windows", "when": "3 Oct", "commit": "eda5c57", "status": "done",
                  "step": "The day each network's daily value covers, fixed from metadata before any value is read"})
    # 5. ERA5
    years = sorted(int(f[11:15]) for f in os.listdir(D("era5")) if f.startswith("gauge_days_") and f.endswith(".csv.xz")) if os.path.isdir(D("era5")) else []
    sha, date = last("data/era5")
    n = len(years)
    steps.append({"key": "era5", "when": day(date) if n == 35 else "now", "commit": sha if n else "", "status": "done" if n == 35 else f"{n} of 35 years in",
                  "step": "Weather model (ERA5), hour by hour, summed over each gauge network's day"})
    # 6.–8. later steps: done when their output exists
    for key, path, text in (("exposure", "data/exposure/summary.json", "Upwind capacity for every gauge and day, and the 10 % bound"),
                            ("power", "data/power/power.json", "Power check on 1991–2001, before the farms: the smallest effect the data can detect"),
                            ("result", "results/results.json", "The test itself, placebos and robustness checks, then the reading")):
        if os.path.exists(os.path.join(ROOT, path)):
            s, d = last(path)
            steps.append({"key": key, "when": day(d), "commit": s, "status": "done", "step": text})
        else:
            steps.append({"key": key, "when": "next", "commit": "", "status": "waiting", "step": text})
    # the step running now: the first one not done
    for s in steps:
        if s["status"] != "done":
            if s["when"] == "next":
                s["when"] = "now"
            break
    out = {"updated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rain_values_read": os.path.exists(os.path.join(ROOT, "data/power/power.json")),
           "numbers": numbers, "era5": {"years_done": n, "years_total": 35, "years": years}, "steps": steps}
    try:   # keep the old timestamp when nothing else changed, so an idle run makes no commit
        prev = json.load(open(D("status.json"), encoding="utf-8"))
        if {k: v for k, v in prev.items() if k != "updated_utc"} == {k: v for k, v in out.items() if k != "updated_utc"}:
            out["updated_utc"] = prev["updated_utc"]
    except (OSError, ValueError, KeyError):
        pass
    json.dump(out, open(D("status.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    open(D("status.json"), "a").write("\n")
    print(f"status: {sum(1 for s in steps if s['status'] == 'done')} steps done, ERA5 {n}/35")


if __name__ == "__main__":
    main()
