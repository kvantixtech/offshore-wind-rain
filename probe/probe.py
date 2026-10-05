"""Temporary probe: /playground/energy/ as a visitor sees it (desktop and phone), live fields, scripts and console errors."""
import json, re, os, glob, asyncio, urllib.request
from playwright.async_api import async_playwright
UA = "kvantixtech/site-audit check (github actions)"
URL = "https://kvantix.tech/playground/energy/?nocache=en5"
out = {}
for f in glob.glob("probe/*.png") + glob.glob("probe/*.jpg"):
    os.remove(f)
t = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
def meta(attr, name):
    a = re.findall(r'<meta[^>]+%s="%s"[^>]*content="([^"]*)"' % (attr, re.escape(name)), t)
    return (a or [None])[0]
out["html"] = {"title": (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0].strip(), "description": meta("name", "description"),
    "og:image": meta("property", "og:image"), "loaders": sorted(set(re.findall(r"kvx-[a-z]+\.js\?v=\w+", t))),
    "h2": [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", t, re.S)],
    "h3": [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h3[^>]*>(.*?)</h3>", t, re.S)],
    "has_next_section": "kvx-en-next" in t, "has_pulse_host": "kvx-pulse-host" in t}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        for name, vp, dsf in (("desk", {"width": 1440, "height": 900}, 1), ("phone", {"width": 390, "height": 844}, 2)):
            ctx = await b.new_context(viewport=vp, device_scale_factor=dsf, user_agent=UA + " Mozilla/5.0")
            pg = await ctx.new_page(); errs = []
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append("pageerror " + str(e)))
            await pg.goto(URL, wait_until="networkidle", timeout=60000)
            await pg.wait_for_timeout(6000)
            live = await pg.evaluate("""() => { const o = {}; document.querySelectorAll('[data-kvx-en]').forEach(e => { o[e.dataset.kvxEn] = (e.textContent||'').trim().slice(0,80); }); return o; }""")
            pulse = await pg.evaluate("""() => Array.from(document.querySelectorAll('.kvx-pulse-host, [data-kvx-pulse]')).map(e => (e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,200))""")
            dims = await pg.evaluate("() => ({h: document.documentElement.scrollHeight, wide: document.documentElement.scrollWidth > window.innerWidth + 1})")
            await pg.screenshot(path=f"probe/en_{name}.jpg", full_page=True, type="jpeg", quality=70)
            out[name] = {"errors": errs[:10], "live": live, "pulse": pulse, "dims": dims}
            await ctx.close()
        await b.close()
asyncio.run(main())
json.dump(out, open("probe/site.json", "w"), indent=1, ensure_ascii=False)
