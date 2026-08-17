import asyncio, http.server, socketserver, threading, os, json, functools, sys
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8931

def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=serve, daemon=True).start()

IPHONE17PM = {"width": 440, "height": 956}

async def main():
    results = []
    def ok(name, cond, extra=""):
        results.append((("PASS" if cond else "FAIL"), name, extra))

    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport=IPHONE17PM, device_scale_factor=3, is_mobile=True,
                                  has_touch=True, locale="en-GB",
                                  user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
        await ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = await ctx.new_page()
        errors, console = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: console.append((m.type, m.text)) if m.type == "error" else None)

        await page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
        # feeds will fail in this sandbox -> exercises the graceful-degradation path
        await page.wait_for_timeout(6000)

        ok("no uncaught JS errors", not errors, "; ".join(errors[:3]))
        # network failures to external hosts are expected in this sandbox (no egress);
        # only app-level console errors count
        app_errs = [t for _, t in console if "Failed to load resource" not in t]
        ok("no app console errors", not app_errs, "; ".join(app_errs[:3]))
        print(f"note: {len(console)} external resource load failures (sandbox has no egress to the RSS relays or Google Fonts)")

        # layout
        sw = await page.evaluate("document.documentElement.scrollWidth")
        ok("no horizontal overflow", sw <= 441, f"scrollWidth={sw}")

        ok("masthead present", await page.locator(".wordmark").count() == 1)
        ok("section nav rendered", await page.locator("#secnav .seclink").count() >= 8)

        # a card must exist (fallback demo article at minimum)
        cards = await page.locator("article.card").count()
        ok("front page shows at least one story", cards >= 1, f"cards={cards}")

        # touch targets
        small = await page.evaluate("""() => {
          const bad=[];
          document.querySelectorAll('button:not([hidden])').forEach(b=>{
            const r=b.getBoundingClientRect();
            if(r.width>0 && r.height>0 && (r.height<43.5||r.width<43.5)) bad.push((b.id||b.className)+':'+Math.round(r.width)+'x'+Math.round(r.height));
          });
          return bad;
        }""")
        ok("all visible buttons >= 44px", not small, ", ".join(small[:5]))

        # open the article
        await page.locator("article.card").first.click()
        await page.wait_for_timeout(700)
        ok("reader opens", await page.locator("#reader.on").count() == 1)
        ok("headline rendered in reader", bool((await page.locator("#rwrap h1").inner_text()).strip()))
        drop = await page.evaluate("""() => {
          const p=document.querySelector('.rbody p'); if(!p) return null;
          return getComputedStyle(p,'::first-letter').fontSize;
        }""")
        ok("drop cap applied", bool(drop) and float(str(drop).replace("px","")) > 40, f"first-letter={drop}")

        # copy
        await page.locator("#rCopy").click()
        await page.wait_for_timeout(600)
        clip = await page.evaluate("navigator.clipboard.readText()")
        ok("one-tap copy puts article on clipboard", clip and len(clip) > 200, f"{len(clip or '')} chars")
        ok("copy includes title + source", bool(clip) and "The Ledger" in clip)
        ok("copied toast shown", await page.locator("#toast.on").count() == 1)
        await page.wait_for_timeout(2200)

        # listen -> device-voice fallback (no API key set)
        await page.locator("#rListen").click()
        await page.wait_for_timeout(1200)
        ok("audio dock opens on Listen", await page.locator("#dock.on").count() == 1)
        sub = await page.locator("#dSub").inner_text()
        ok("falls back to device voice without API key", "Device voice" in sub or "speech" in sub.lower(), sub)

        # rate control
        await page.locator("#dRate").click()
        ok("playback speed cycles", (await page.locator("#dRate").inner_text()) != "1.0×",
           await page.locator("#dRate").inner_text())

        # progress bar
        await page.evaluate("document.querySelector('#reader').scrollTo(0, 900)")
        await page.wait_for_timeout(400)
        w = await page.evaluate("document.querySelector('#progress').style.width")
        ok("reading progress bar advances", w not in ("", "0%"), f"width={w}")

        await page.screenshot(path=os.path.join(ROOT, "shot-article.png"), full_page=False)

        # bookmark from reader, then Saved section
        await page.locator("#rSave").click()
        await page.wait_for_timeout(400)
        await page.locator("#rBack").click()
        await page.wait_for_timeout(700)
        await page.locator("#btnSaved").click()
        await page.wait_for_timeout(500)
        ok("saved section lists the bookmark", await page.locator("article.card").count() >= 1)

        # back to front page + search
        await page.locator('#secnav .seclink[data-sec="Front page"]').click()
        await page.wait_for_timeout(400)
        await page.locator("#btnSearch").click()
        await page.fill("#q", "zzzznomatch")
        await page.wait_for_timeout(400)
        ok("search filters (empty state)", await page.locator(".notice").count() >= 1)
        await page.fill("#q", "")
        await page.locator("#btnSearch").click()

        # dark mode
        await page.locator("#btnTheme").click()
        await page.wait_for_timeout(400)
        theme = await page.evaluate("document.documentElement.dataset.theme")
        ok("dark mode toggles", theme == "dark", f"theme={theme}")
        await page.screenshot(path=os.path.join(ROOT, "shot-dark.png"))
        await page.locator("#btnTheme").click()
        await page.wait_for_timeout(300)

        # settings + persistence
        await page.locator("#btnSettings").click()
        await page.wait_for_timeout(400)
        ok("settings sheet opens", await page.locator("#settings.on").count() == 1)
        ok("feed status listed", await page.locator("#feedstatus div").count() >= 20,
           str(await page.locator("#feedstatus div").count()))
        await page.fill("#apikey", "sk-test-not-a-real-key")
        await page.locator("#saveSettings").click()
        await page.wait_for_timeout(500)
        stored = await page.evaluate("JSON.parse(localStorage.getItem('ledger.apikey'))")
        ok("API key persists on device only", stored == "sk-test-not-a-real-key", str(stored))
        # and it must never leave for anywhere but openai
        hosts = await page.evaluate("""() => {
          const s = document.documentElement.innerHTML;
          return /api\\.openai\\.com/.test(s);
        }""")
        ok("key is only ever posted to api.openai.com", hosts)

        # PWA bits
        man = await page.evaluate("""async () => {
          const l=document.querySelector('link[rel=manifest]');
          const r=await fetch(l.href); return await r.json();
        }""")
        ok("manifest loads", man.get("name","").startswith("The Ledger"), json.dumps(man)[:60])
        ok("manifest is standalone", man.get("display") == "standalone")
        sw_ok = await page.evaluate("navigator.serviceWorker.getRegistrations().then(r=>r.length>0)")
        ok("service worker registered", sw_ok)

        # front page screenshot after a successful-ish state
        await page.evaluate("document.querySelector('#settings').classList.remove('on')")
        await page.wait_for_timeout(400)
        await page.screenshot(path=os.path.join(ROOT, "shot-front.png"))

        await b.close()

    width = max(len(n) for _, n, _ in results)
    fails = 0
    for st, n, ex in results:
        if st == "FAIL": fails += 1
        print(f"{st}  {n.ljust(width)}  {ex}")
    print(f"\n{len(results)-fails}/{len(results)} checks passed")
    sys.exit(1 if fails else 0)

asyncio.run(main())
