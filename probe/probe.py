"""Temporary probe: which block versions are live before the pulse is installed, and the front page's hero structure."""
import json, re, urllib.request
UA = "kvantixtech/site-audit check (github actions)"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60)
    return r.status, r.read()
out = {}
for path in ["/", "/playground/", "/playground/weather/", "/playground/energy/", "/playground/experts/", "/playground/wastewater/",
             "/playground/nitrogen/", "/playground/wind-rain/"]:
    try:
        st, b = get("https://kvantix.tech" + path + "?nocache=pulse1")
        t = b.decode("utf-8", "replace")
        out[path] = {"status": st, "versions": sorted(set(re.findall(r"(kvx-[a-z]+\.js\?v=\d{8}[a-z])", t))),
                     "kvx_cta": t.count('<div class="kvx-cta">'), "lede": t.count('class="kvx-lede"'),
                     "site_js": sorted(set(re.findall(r"(kvantix-[a-z]+(?:-[0-9a-z-]+)?\.js[^\"' ]*)", t)))[:8],
                     "pulse": t.count("data-kvx-pulse")}
    except Exception as e:
        out[path] = {"error": str(e)[:200]}
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
