"""Temporary probe: the whole hub (/playground/) as a visitor sees it, desktop and phone, plus its links and meta tags."""
import json, re, os, glob, urllib.request, urllib.error, asyncio
from playwright.async_api import async_playwright
UA = "kvantixtech/site-audit check (github actions)"
NC = "?nocache=hub4"
HUB = "https://kvantix.tech/playground/"
out = {}
for f in glob.glob("probe/*.png") + glob.glob("probe/*.jpg"):
    os.remove(f)


def get(url, timeout=40):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)
    return r.status, r.read()


st, b = get(HUB + NC)
t = b.decode("utf-8", "replace")


def meta(attr, name):
    a = re.findall(r'<meta[^>]+%s="%s"[^>]*content="([^"]*)"' % (attr, re.escape(name)), t)
    b_ = re.findall(r'<meta[^>]+content="([^"]*)"[^>]*%s="%s"' % (attr, re.escape(name)), t)
    return (a or b_ or [None])[0]


out["html"] = {
    "status": st,
    "title": (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0].strip(),
    "description": meta("name", "description"),
    "og:title": meta("property", "og:title"),
    "og:description": meta("property", "og:description"),
    "og:image": meta("property", "og:image"),
    "twitter:title": meta("name", "twitter:title"),
    "canonical": (re.findall(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', t) or [None])[0],
    "wx_fix_installed": "kvx-pg-wx-left" in t,
    "old_wx_wrapper": 'kvx-pg-wx-live" style="max-width:640px' in t,
    "loaders": sorted(set(re.findall(r"kvx-[a-z]+\.js\?v=\w+", t))),
    "h2": [re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<h2[^>]*>(.*?)</h2>", t, re.S)],
}
if out["html"]["og:image"]:
    try:
        _, img = get(out["html"]["og:image"])
        open("probe/og_playground.jpg", "wb").write(img)
        out["html"]["og_bytes"] = len(img)
    except Exception as e:
        out["html"]["og_err"] = str(e)[:200]

# every link on the hub that points at our own pages or repos
links = sorted(set(u for u in re.findall(r'href="(https://[^"#]+)', t)
                   if u.startswith(("https://kvantix.tech", "https://github.com/kvantixtech", "https://portal.kvantix.tech"))))
out["links"] = {}
for u in links[:60]:
    try:
        s_, _ = get(u, timeout=25)
        out["links"][u] = s_
    except urllib.error.HTTPError as e:
        out["links"][u] = e.code
    except Exception as e:
        out["links"][u] = str(e)[:80]

FIND = """() => { window.__kvxS = () => {
  const c = [document.getElementById('kvx-root'), ...document.querySelectorAll('body *')].filter(Boolean);
  for (const e of c) { const cs = getComputedStyle(e); if (e.scrollHeight > e.clientHeight + 50 && /(auto|scroll)/.test(cs.overflowY)) return e; }
  return document.scrollingElement; }; const s = window.__kvxS();
  return { scroller: s.id || s.tagName, height: s.scrollHeight, client: s.clientHeight, hscroll: s.scrollWidth > s.clientWidth + 1,
           wideBody: document.documentElement.scrollWidth > window.innerWidth + 1 }; }"""
CHECKS = """() => { const s = window.__kvxS(), off = s.scrollTop;
  const sel = '.kvx-card, .kvx-exhibit, .kvx-trap, .kvx-case, .kvx-verdict, .kvx-pulse-host, .kvx-timeline, .kvx-sh';
  const els = Array.from(document.querySelectorAll(sel)).filter(e => e.offsetParent !== null);
  const R = els.map(e => { const r = e.getBoundingClientRect(); return { e, x: r.left, y: r.top + off, w: r.width, h: r.height }; });
  const name = e => e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\\s+/).slice(0, 2).join('.') + ' "' + (e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 40) + '"';
  const overlaps = [];
  for (let i = 0; i < R.length; i++) for (let j = i + 1; j < R.length; j++) {
    const a = R[i], b = R[j];
    if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
    const ix = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), iy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ix > 4 && iy > 4) overlaps.push([name(a.e), name(b.e), Math.round(ix), Math.round(iy), Math.round(Math.max(a.y, b.y))]);
  }
  const W = window.innerWidth;
  const wide = Array.from(document.querySelectorAll('#kvx-root *')).filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > W + 1 || r.left < -1) && getComputedStyle(e).position !== 'fixed'; })
     .slice(0, 12).map(e => name(e) + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right));
  const badImg = Array.from(document.images).filter(i => i.complete && i.naturalWidth === 0).map(i => i.src).slice(0, 10);
  const g = s2 => (document.querySelector(s2) || {}).textContent || null;
  return { overlaps: overlaps.slice(0, 20), outside_viewport: wide, broken_images: badImg,
           vital: g('a.kvx-pulse-vital'), hud: (g('.kvx-pulse-hud') || '').slice(0, 160), feed: (g('[data-kvx-pulse-feed]') || '').trim().slice(0, 200),
           wx_state: g('[data-kvx-ws="state"]'), wx_day: g('[data-kvx-ws="day"]'), wx_runs: g('[data-kvx-ws="runs"]'), wx_chain: g('[data-kvx-ws="chain"]'),
           hub_live: Array.from(document.querySelectorAll('[data-kvx-hub]')).map(e => e.getAttribute('data-kvx-hub') + ': ' + e.textContent.trim()).slice(0, 12) }; }"""


def watch(page, logs):
    page.on("console", lambda m: logs.append(m.type + ": " + m.text[:200]) if m.type == "error" else None)
    page.on("pageerror", lambda e: logs.append("PAGEERROR: " + str(e)[:200]))
    page.on("requestfailed", lambda r: logs.append("FAILED " + r.url[:120] + " " + str(r.failure)) if "kvantix" in r.url or "github" in r.url else None)
    page.on("response", lambda r: logs.append(f"HTTP {r.status} {r.url[:120]}") if r.status >= 400 else None)


async def tour(b, tag, vw, vh, dpr, mobile):
    ctx = await b.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=dpr, is_mobile=mobile, has_touch=mobile,
                              user_agent=UA + (" chrome mobile" if mobile else " chrome"))
    page = await ctx.new_page(); logs = []; watch(page, logs)
    await page.goto(HUB + NC, wait_until="load")
    await page.wait_for_timeout(13000)              # the organism replays the last 24 hours first
    r = {"page": await page.evaluate(FIND)}
    r["checks"] = await page.evaluate(CHECKS)
    n, pos = 0, 0
    while n < 45:
        await page.evaluate("(y) => { window.__kvxS().scrollTop = y; }", pos)
        await page.wait_for_timeout(650)
        await page.screenshot(path=f"probe/hub_{tag}_{n:02d}.jpg", type="jpeg", quality=72)
        top, H, C = await page.evaluate("() => { const s = window.__kvxS(); return [s.scrollTop, s.scrollHeight, s.clientHeight]; }")
        if top + C >= H - 2:
            break
        pos = top + C - 110; n += 1
    r["shots"] = n + 1
    r["logs"] = logs[:20]
    out["tour " + tag] = r
    await ctx.close()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        await tour(b, "desk", 1440, 1000, 1, False)
        await tour(b, "mob", 390, 844, 2, True)
        await b.close()

asyncio.run(main())
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1)[:6000])
