"""Temporary probe: the wind time machine and the noise machine in a real browser on the live site."""
import json, hashlib, re, urllib.request, asyncio
from playwright.async_api import async_playwright
UA = "kvantixtech/site-audit check (github actions)"
NC = "?nocache=wt1"
out = {"sha": {}, "html": {}}


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60)
    return r.status, r.read()


for f, q in (("kvx-windrain.js", "v=20261004t"), ("kvx-windrain.js", "v=check6"), ("kvx-noise.js", "v=20261004n"), ("kvx-noise.js", "v=check6")):
    try:
        st, b = get("https://kvantix.tech/wp-content/uploads/kvx/" + f + "?" + q)
        out["sha"][f + " " + q] = [st, hashlib.sha256(b).hexdigest()[:12], len(b)]
    except Exception as e:
        out["sha"][f + " " + q] = str(e)[:160]

for path in ("/playground/wind-rain/", "/playground/noise-machine/", "/playground/"):
    try:
        st, b = get("https://kvantix.tech" + path + NC)
        t = b.decode("utf-8", "replace")
        out["html"][path] = {
            "status": st,
            "title": (re.findall(r"<title>(.*?)</title>", t, re.S) or [""])[0][:120],
            "og_image": (re.findall(r'property="og:image" content="([^"]+)"', t) or [None])[0],
            "loaders": sorted(set(re.findall(r"kvx-[a-z]+\.js\?v=\w+", t))),
            "has_time_machine": 'id="kvx-wt"' in t,
            "noise_links": len(re.findall(r'href="[^"]*/playground/noise-machine/', t)),
        }
    except Exception as e:
        out["html"][path] = str(e)[:200]

SCROLL = """(top) => { var e = document.getElementById('kvx-wt') || document.getElementById('kvx-noise'), p = e.parentElement;
  while (p && !(p.scrollHeight > p.clientHeight + 5 && /(auto|scroll)/.test(getComputedStyle(p).overflowY))) p = p.parentElement;
  p = p || document.scrollingElement; p.scrollTop += e.getBoundingClientRect().top - top; }"""
READ_WT = """() => { var g = id => (document.getElementById(id) || {}).textContent || null;
  return { year: g('kvx-wt-y'), date: g('kvx-wt-d'), ns: g('kvx-wt-ns'), all: g('kvx-wt-all'), n: g('kvx-wt-n'), farms: g('kvx-wt-f'),
           gauge: g('kvx-wt-gname'), upwind: g('kvx-wt-e'), upwind_line: g('kvx-wt-el'), dir: g('kvx-wt-dirv'), beat: g('kvx-wt-beat'),
           canvas: (() => { var c = document.getElementById('kvx-wt-map'); return c ? [c.width, c.height] : null; })(),
           pulse_strip: !!document.querySelector('.kvx-pulse-strip, [data-kvx-pulse-strip], .kvx-pstrip') }; }"""


def watch(page, logs):
    page.on("console", lambda m: logs.append(m.type + ": " + m.text[:200]) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: logs.append("PAGEERROR: " + str(e)[:200]))
    page.on("requestfailed", lambda r: logs.append("FAILED " + r.url[:120] + " " + str(r.failure)) if "kvantix" in r.url else None)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        # 1. wind-rain, desktop: autoplay, end state, scrub
        ctx = await b.new_context(viewport={"width": 1440, "height": 1000}, user_agent=UA + " chrome")
        page = await ctx.new_page(); logs = []; watch(page, logs)
        await page.goto("https://kvantix.tech/playground/wind-rain/" + NC, wait_until="load")
        await page.wait_for_timeout(2500)
        r = {"present": await page.locator("#kvx-wt").count()}
        if r["present"]:
            await page.locator("#kvx-wt").scroll_into_view_if_needed()
            await page.wait_for_timeout(9000)
            r["mid"] = await page.evaluate(READ_WT)
            await page.locator("#kvx-wt").screenshot(path="probe/wt_desk_mid.png")
            await page.wait_for_timeout(26000)
            r["end"] = await page.evaluate(READ_WT)
            await page.locator("#kvx-wt").screenshot(path="probe/wt_desk_end.png")
            bb = await page.locator("#kvx-wt-bars").bounding_box()
            await page.mouse.click(bb["x"] + bb["width"] * 0.62, bb["y"] + bb["height"] * 0.5)
            await page.wait_for_timeout(600)
            r["scrub"] = await page.evaluate(READ_WT)
        r["scripts"] = await page.evaluate("Array.from(document.scripts).map(s => s.src).filter(s => s.includes('/kvx/'))")
        r["logs"] = logs[:15]
        out["wind-rain desktop"] = r
        await ctx.close()

        # 2. wind-rain, phone
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, user_agent=UA + " chrome mobile")
        page = await ctx.new_page(); logs = []; watch(page, logs)
        await page.goto("https://kvantix.tech/playground/wind-rain/" + NC, wait_until="load")
        await page.wait_for_timeout(2500)
        r = {}
        if await page.locator("#kvx-wt").count():
            await page.locator("#kvx-wt").scroll_into_view_if_needed()
            await page.evaluate(SCROLL, 90)
            await page.wait_for_timeout(36000)
            await page.evaluate(SCROLL, 90)
            await page.wait_for_timeout(400)
            r["end"] = await page.evaluate(READ_WT)
            await page.screenshot(path="probe/wt_mob_end.png")
        r["logs"] = logs[:15]
        out["wind-rain phone"] = r
        await ctx.close()

        # 3. noise machine, desktop: all four steps
        ctx = await b.new_context(viewport={"width": 1440, "height": 1000}, user_agent=UA + " chrome")
        page = await ctx.new_page(); logs = []; watch(page, logs)
        resp = await page.goto("https://kvantix.tech/playground/noise-machine/" + NC + "#seed=424242&n=1000&talent=1", wait_until="load")
        await page.wait_for_timeout(2500)
        r = {"status": resp.status if resp else None, "present": await page.locator("#kvx-noise").count()}
        if r["present"]:
            m = page.locator("#kvx-noise"); await m.scroll_into_view_if_needed()
            go = page.locator("#kvx-nz-go")
            says = []
            await go.click(); await page.wait_for_function("!document.getElementById('kvx-nz-go').disabled", timeout=40000)
            says.append(await page.inner_text("#kvx-nz-say"))
            await go.click(); await page.wait_for_timeout(900); says.append(await page.inner_text("#kvx-nz-say"))
            await go.click(); await page.wait_for_timeout(2200); says.append(await page.inner_text("#kvx-nz-say"))
            await go.click(); await page.wait_for_function("!document.getElementById('kvx-nz-go').disabled", timeout=45000)
            await page.wait_for_timeout(600); says.append(await page.inner_text("#kvx-nz-say"))
            r["says"] = [s[:220] for s in says]
            r["read"] = (await page.inner_text("#kvx-nz-read"))[:300]
            await m.screenshot(path="probe/nz_desk_end.png")
        r["logs"] = logs[:15]
        out["noise desktop"] = r
        await ctx.close()

        # 4. hub: the new card
        ctx = await b.new_context(viewport={"width": 1440, "height": 1000}, user_agent=UA + " chrome")
        page = await ctx.new_page(); logs = []; watch(page, logs)
        await page.goto("https://kvantix.tech/playground/" + NC, wait_until="load")
        await page.wait_for_timeout(4000)
        card = page.locator("a[href*='/playground/noise-machine/']").first
        r = {"noise_card": await page.locator("a[href*='/playground/noise-machine/']").count()}
        if r["noise_card"]:
            await card.scroll_into_view_if_needed(); await page.wait_for_timeout(500)
            r["card_text"] = (await card.inner_text())[:200]
            await page.screenshot(path="probe/hub_noise_card.png")
        wq = page.get_by_text("Four questions anyone can follow").first
        if await wq.count():
            await wq.scroll_into_view_if_needed(); await page.wait_for_timeout(800)
            await page.screenshot(path="probe/hub_weather_section.png", full_page=False)
            r["weather_section_dom"] = await page.evaluate("""() => { var h = Array.from(document.querySelectorAll('h3,h4')).find(x => /Four questions/.test(x.textContent));
              var sec = h && h.closest('section'); if (!sec) return null;
              return Array.from(sec.querySelectorAll('*')).filter(e => e.children.length && e.getBoundingClientRect().width > 300).slice(0, 25).map(e => {
                var b = e.getBoundingClientRect(), cs = getComputedStyle(e);
                return [e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\\s+/).slice(0, 3).join('.') : ''),
                        Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height), cs.position, cs.display, cs.gridTemplateColumns || ''];
              }); }""")
        r["logs"] = logs[:15]
        out["hub"] = r
        await ctx.close()
        await b.close()

asyncio.run(main())
json.dump(out, open("probe/site.json", "w"), indent=1)
print(json.dumps(out, indent=1))
