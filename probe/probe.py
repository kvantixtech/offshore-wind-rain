"""Temporary probe: the wind-rain page on the live site (status, versions, script hash, meta tags)."""
import json, re, hashlib, urllib.request
UA = "kvantixtech/site-audit check (github actions)"
def get(u):
    r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=60)
    return r.status, r.read()
out = {}
for path in ["/playground/wind-rain/", "/playground/"]:
    try:
        st, b = get("https://kvantix.tech" + path + "?nocache=1")
        t = b.decode("utf-8", "replace")
        out[path] = {"status": st, "versions": sorted(set(re.findall(r"\?v=(\d{8}[a-z])", t))),
                     "wind_card": "/playground/wind-rain/" in t, "title": (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0][:160],
                     "og": re.findall(r'<meta (?:property|name)="(og:title|og:description|og:image|twitter:image|description)" content="([^"]*)"', t),
                     "trackers": sorted(set(re.findall(r"(googletagmanager|google-analytics|umami|facebook\.net|hotjar)", t))),
                     "has_cards": 'id="kvx-wr-cards"' in t, "privacy_link": "/privacy/" in t}
    except Exception as e:
        out[path] = {"error": str(e)[:200]}
try:
    st, b = get("https://kvantix.tech/wp-content/uploads/kvx/kvx-windrain.js?v=20261004a")
    out["js"] = {"status": st, "bytes": len(b), "sha256_matches": hashlib.sha256(b).hexdigest() == "68801e930ae1f71d4e03ed0c946b4015d8225e333c8e5e9291ed7cd0d82633ec"}
except Exception as e:
    out["js"] = {"error": str(e)[:200]}
try:
    st, b = get("https://api.github.com/repos/kvantixtech/offshore-wind-rain/contents/data/era5?ref=main")
    out["github_api"] = {"status": st, "files": len(json.loads(b))}
except Exception as e:
    out["github_api"] = {"error": str(e)[:200]}
json.dump(out, open("probe/site.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(out, indent=1, ensure_ascii=False))
