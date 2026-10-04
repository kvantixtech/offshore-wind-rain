"""Temporary probe: is the pulse installed (script uploaded, blocks, front page)?"""
import json, re, hashlib, urllib.request
UA = "kvantixtech/site-audit check (github actions)"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60)
    return r.status, r.read()
out = {}
for path in ["/", "/playground/", "/playground/weather/", "/playground/energy/", "/playground/experts/", "/playground/wastewater/",
             "/playground/nitrogen/", "/playground/wind-rain/"]:
    try:
        st, b = get("https://kvantix.tech" + path + "?nocache=pulse2")
        t = b.decode("utf-8", "replace")
        out[path] = {"status": st, "versions": sorted(set(re.findall(r"(kvx-[a-z]+\.js\?v=\d{8}[a-z])", t))),
                     "pulse_attrs": sorted(set(re.findall(r'data-kvx-pulse-[a-z]*', t))), "vital_class": t.count("kvx-pulse-vital"),
                     "pulse_loader": re.findall(r"kvx-pulse\.js\?v=\d{8}[a-z]", t)}
    except Exception as e:
        out[path] = {"error": str(e)[:200]}
for q in ("v=20261004p", "v=check3"):
    try:
        st, b = get("https://kvantix.tech/wp-content/uploads/kvx/kvx-pulse.js?" + q)
        out["kvx-pulse.js " + q] = {"status": st, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
    except Exception as e:
        out["kvx-pulse.js " + q] = {"error": str(e)[:200]}
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
