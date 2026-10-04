"""Temporary probe: hub and wind-rain pages live (versions, live hooks, script hashes)."""
import json, re, hashlib, urllib.request
UA = "kvantixtech/site-audit check (github actions)"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60)
    return r.status, r.read()
out = {}
for path in ["/playground/", "/playground/wind-rain/"]:
    try:
        st, b = get("https://kvantix.tech" + path + "?nocache=2")
        t = b.decode("utf-8", "replace")
        out[path] = {"status": st, "versions": sorted(set(re.findall(r"kvx-[a-z]+\.js\?v=(\d{8}[a-z])", t))),
                     "scripts": sorted(set(re.findall(r"(kvx-[a-z]+\.js)\?v=", t))),
                     "hub_hooks": len(re.findall(r'data-kvx-hub="', t)), "wr_hooks": len(re.findall(r'data-kvx-wr="', t)),
                     "wind_card": "/playground/wind-rain/" in t}
    except Exception as e:
        out[path] = {"error": str(e)[:200]}
for name, sha in (("kvx-hub.js", "ed366aa87f52c7bbcb4b2faec041ab4a4dd25c412a37b3566ee9dba389946eaa"), ("kvx-windrain.js", "dbb43cdc75e14b71f6f65e2bea8c27edbd4b53518860544b367c237713689db7")):
    try:
        st, b = get("https://kvantix.tech/wp-content/uploads/kvx/" + name + "?v=check2")
        out[name] = {"status": st, "bytes": len(b), "sha256_matches": hashlib.sha256(b).hexdigest() == sha}
    except Exception as e:
        out[name] = {"error": str(e)[:200]}
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
