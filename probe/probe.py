"""Temporary probe: which Playground pages answer on the live site (status codes only)."""
import json, urllib.request
out = {}
for path in ["/playground/", "/playground/nitrogen/", "/playground/wastewater/", "/playground/wind-rain/", "/playground/energy/"]:
    try:
        r = urllib.request.urlopen(urllib.request.Request("https://kvantix.tech" + path, headers={"User-Agent": "kvantixtech/site-audit check (github actions)"}), timeout=60)
        b = r.read().decode("utf-8", "replace")
        out[path] = {"status": r.status, "has_nitrogen_card": "/playground/nitrogen/" in b, "kvx_versions": sorted(set(__import__("re").findall(r"\?v=(\d{8}[a-z])", b)))}
    except Exception as e:
        out[path] = {"error": str(e)[:200]}
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
