"""Temporary probe: the pulse in a real browser on the live site (front page and hub)."""
import json, hashlib, re, urllib.request, asyncio
from playwright.async_api import async_playwright
UA = "kvantixtech/site-audit check (github actions)"
out = {}
for q in ("v=20261004q", "v=20261004p", "v=check5"):
    b = urllib.request.urlopen(urllib.request.Request("https://kvantix.tech/wp-content/uploads/kvx/kvx-pulse.js?" + q, headers={"User-Agent": UA}), timeout=60).read()
    out["kvx-pulse.js " + q] = hashlib.sha256(b).hexdigest()[:12]
t = urllib.request.urlopen(urllib.request.Request("https://kvantix.tech/?nocache=pulse4", headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
out["front loaders"] = re.findall(r"kvx-pulse\.js\?v=\d{8}[a-z]", t)
out["front csp"] = None

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        for path, wait in (("/", 6000), ("/playground/", 14000)):
            page = await (await b.new_context(viewport={"width": 1440, "height": 1000}, user_agent=UA + " chrome")).new_page()
            logs = []
            page.on("console", lambda m: logs.append(m.type + ": " + m.text[:200]))
            page.on("pageerror", lambda e: logs.append("PAGEERROR: " + str(e)[:200]))
            reqs = []
            page.on("requestfinished", lambda r: reqs.append(r.url) if "pulse" in r.url else None)
            page.on("requestfailed", lambda r: logs.append("FAILED " + r.url[:120] + " " + str(r.failure)))
            resp = await page.goto("https://kvantix.tech" + path + "?nocache=pulse4", wait_until="load")
            await page.wait_for_timeout(wait)
            info = await page.evaluate("""() => ({
              vital: Array.from(document.querySelectorAll('a.kvx-pulse-vital')).map(a => (a.hidden ? 'HIDDEN ' : 'shown ') + a.textContent.trim()),
              css: !!document.getElementById('kvx-pulse-css'),
              pulseScripts: Array.from(document.scripts).map(s => s.src).filter(s => s.includes('pulse')),
              orgHud: (document.querySelector('.kvx-pulse-hud') || {}).textContent || null,
              feed: ((document.querySelector('[data-kvx-pulse-feed]') || {}).textContent || '').slice(0, 160)
            })""")
            out[path] = {"csp": resp.headers.get("content-security-policy"), "csp_ro": (resp.headers.get("content-security-policy-report-only") or "")[:300],
                         "info": info, "pulse_requests": reqs[:6], "logs": [l for l in logs if "pulse" in l.lower() or "PAGEERROR" in l or "FAILED" in l or "Content Security" in l][:12]}
            await page.screenshot(path="probe/live" + path.replace("/", "_") + ".png")
        await b.close()
asyncio.run(main())
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
