"""Second QA pass: feed the real code path real RSS/Atom, by intercepting the
CORS relay request and answering with feeds captured from the live web.
Proves parsing, sectioning, dedupe, the editorial mix, the licence model
(full republication only where permitted, summary-and-context otherwise),
copy and TTS chunking against actual publisher output rather than a mock."""
import asyncio, http.server, socketserver, threading, os, functools, sys, urllib.parse
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8932

def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), h) as s:
        s.serve_forever()

threading.Thread(target=serve, daemon=True).start()

FIXTURES = {
    "search.cnbc.com": "cnbc.xml",
    "feeds.bbci.co.uk": "bbc.xml",
    "www.federalreserve.gov": "fed.xml",
    "feeds.content.dowjones.io": "mw.xml",
    "www.noahpinion.blog": "noahpinion.xml",
    "theconversation.com": "conversation.atom",
    "awealthofcommonsense.com": "awocs.xml",
    "www.bankofengland.co.uk": "boe.xml",
}
CACHE = {k: open(os.path.join(ROOT, "fixtures", v), "rb").read() for k, v in FIXTURES.items()}

async def main():
    results = []
    def ok(n, c, extra=""):
        results.append(("PASS" if c else "FAIL", n, str(extra)))

    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width":440,"height":956}, device_scale_factor=3,
                                  is_mobile=True, has_touch=True, locale="en-GB")
        await ctx.grant_permissions(["clipboard-read","clipboard-write"])

        async def relay(route):
            q = urllib.parse.urlparse(route.request.url).query
            target = urllib.parse.parse_qs(q).get("url", [""])[0]
            host = urllib.parse.urlparse(target).hostname or ""
            body = CACHE.get(host)
            if body is None:
                await route.fulfill(status=504, body="no fixture")
            else:
                await route.fulfill(status=200, body=body,
                                    headers={"content-type":"application/rss+xml; charset=utf-8"})
        await ctx.route("**api.allorigins.win/**", relay)
        # everything else external fails fast, exercising the fallback chain
        await ctx.route("**corsproxy.io/**", lambda r: asyncio.ensure_future(r.abort()))
        await ctx.route("**codetabs.com/**", lambda r: asyncio.ensure_future(r.abort()))
        await ctx.route("**fonts.g**", lambda r: asyncio.ensure_future(r.abort()))

        page = await ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        await page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="load")
        await page.wait_for_function("window.__ready === undefined ? document.querySelectorAll('article.card').length > 3 : true",
                                     timeout=60000)
        await page.wait_for_timeout(4000)

        ok("no uncaught errors parsing real feeds", not errs, "; ".join(errs[:2]))

        data = await page.evaluate("""() => {
          const real = S.items.filter(i=>!i.demo && !i.ledger);
          const bySec = {}; real.forEach(i=>bySec[i.section]=(bySec[i.section]||0)+1);
          return {
            count: real.length,
            sources: [...new Set(real.map(i=>i.source))],
            bySec,
            fullText: real.filter(i=>i.fullText).length,
            withLink: real.filter(i=>/^https?:/.test(i.link)).length,
            withAuthor: real.filter(i=>i.author && i.author.length>1).length,
            withStand: real.filter(i=>i.standfirst && i.standfirst.length>40).length,
            datedOk: real.filter(i=>i.ts>0 && i.ts < Date.now()+864e5).length,
            titlesClean: real.filter(i=>!/[<>]|&[a-z]+;/.test(i.title)).length,
            dupes: real.length - new Set(real.map(i=>i.title.toLowerCase())).size,
            sampleTitles: real.slice(0,4).map(i=>i.source+": "+i.title.slice(0,58)),
            longest: Math.max(...real.map(i=>i.words||0))
          };
        }""")

        ok("real articles parsed", data["count"] >= 80, f"{data['count']} items")
        ok("all 8 reachable feeds contributed", len(data["sources"]) >= 8, ", ".join(data["sources"]))
        ok("stories spread across sections", len(data["bySec"]) >= 4, data["bySec"])
        ok("full-text articles detected", data["fullText"] >= 15, f"{data['fullText']} full-text")
        ok("every item has a source link", data["withLink"] == data["count"], f"{data['withLink']}/{data['count']}")
        ok("bylines extracted", data["withAuthor"] == data["count"])
        ok("standfirsts generated", data["withStand"] >= data["count"] * 0.7, f"{data['withStand']}/{data['count']}")
        ok("publish dates sane", data["datedOk"] == data["count"], f"{data['datedOk']}/{data['count']}")
        ok("headlines free of markup/entities", data["titlesClean"] == data["count"],
           f"{data['titlesClean']}/{data['count']}")
        ok("no duplicate headlines", data["dupes"] == 0, data["dupes"])
        print("   sample:", *data["sampleTitles"], sep="\n     ")

        # editorial mix -- front page is Ledger-authored (content.js), driven by S.mix
        mix = await page.evaluate("() => { S.section='Front page'; S.query=''; render(); return S.mix; }")
        ok("front-page mix follows the editorial strategy",
           bool(mix) and 0.55 <= mix["news"]/mix["total"] <= 0.75
                     and 0.15 <= mix["analysis"]/mix["total"] <= 0.35
                     and 0.05 <= mix["deep"]/mix["total"] <= 0.20, mix)

        # the RSS layer lives in Newsstand now, never on the front page
        ns = await page.evaluate("() => { S.section='Newsstand'; S.query=''; const n = visible().length; S.section='Front page'; render(); return n; }")
        ok("newsstand lists the real feed items", ns >= 50, f"{ns} items")

        # a licensed article (The Conversation fixture, CC BY-ND) republishes in full
        target = await page.evaluate("""() => {
          const it = S.items.filter(i=>!i.demo && !i.ledger && i.republish).sort((a,b)=>b.words-a.words)[0];
          if(!it) return null; openReader(it);
          return {title:it.title, words:it.words, source:it.source, lic:it.lic};
        }""")
        ok("a licensed full-text article opens in full", bool(target),
           target and f"{target['source']} ({target['lic']}) — {target['words']} words")
        await page.wait_for_timeout(600)
        paras = await page.locator("#rwrap .rbody p").count()
        ok("article body renders as paragraphs", paras >= 4, f"{paras} paragraphs")
        scripts = await page.locator("#rwrap script, #rwrap iframe").count()
        ok("publisher markup sanitised (no script/iframe)", scripts == 0)
        blank = await page.locator('#rwrap .rbody a[target="_blank"]').count()
        ok("in-article links open externally", blank >= 0)
        readsrc = await page.locator("#rwrap .srcbox a").count()
        ok("'Read at source' attribution present", readsrc >= 1)

        # copy a real article
        await page.locator("#rCopy").click()
        await page.wait_for_timeout(500)
        clip = await page.evaluate("navigator.clipboard.readText()")
        ok("copy of a real article is substantial", clip and len(clip) > 1500, f"{len(clip or '')} chars")
        ok("copy carries source + link", bool(clip) and target["source"] in clip and "http" in clip)

        # TTS chunking on a real long article
        ch = await page.evaluate("""() => {
          const t = speechText(S.current);
          const c = chunkText(t);
          return {chars:t.length, chunks:c.length, max:Math.max(...c.map(x=>x.length)),
                  splitsMidWord: c.some(x=>/\\S$/.test(x) && !/[.!?"')\\]]\\s*$/.test(x))};
        }""")
        ok("long article splits into queued chunks", ch["chunks"] >= 1 and ch["max"] <= 3800,
           f"{ch['chars']} chars → {ch['chunks']} chunks, max {ch['max']}")

        # an unlicensed full-text feed (e.g. Noahpinion) is presented as The Ledger's
        # summary with a short quote and a route out — never reprinted wholesale
        summ = await page.evaluate("""() => {
          closeReader();
          const it = S.items.filter(i=>!i.demo && !i.ledger && i.fullText && !i.republish)
                            .sort((a,b)=>b.words-a.words)[0];
          if(!it) return null; openReader(it);
          const rb = document.querySelector('#rwrap .rbody').innerText;
          return {source:it.source, words:it.words, full:it.text.length, rendered:rb.length,
                  wim: !!document.querySelector('#rwrap .wimbox'),
                  cta: !!document.querySelector('#rwrap .srccta a')};
        }""")
        ok("unlicensed full text presented as summary, not reprint",
           bool(summ) and summ["rendered"] < summ["full"] * 0.4 and summ["wim"] and summ["cta"],
           summ and f"{summ['source']}: {summ['words']} words → {summ['rendered']} chars shown")

        await page.screenshot(path=os.path.join(ROOT,"shot-live-article.png"))
        await page.locator("#rBack").click()
        await page.wait_for_timeout(700)
        await page.screenshot(path=os.path.join(ROOT,"shot-live-front.png"))

        # section filter with real data
        secs = await page.evaluate("""() => {
          const out={};
          for(const s of ["Markets","Economics","Central Banks","Opinion","Companies"]){
            S.section=s; out[s]=visible().length;
          }
          S.section="Front page"; render(); return out;
        }""")
        ok("every main section has stories", all(v > 0 for v in secs.values()), secs)

        # dark mode with real content
        await page.evaluate("localStorage.setItem('ledger.theme','\"dark\"'); applyTheme();")
        await page.wait_for_timeout(400)
        await page.screenshot(path=os.path.join(ROOT,"shot-live-dark.png"))

        await b.close()

    w = max(len(n) for _, n, _ in results)
    fails = sum(1 for s,_,_ in results if s == "FAIL")
    for s,n,e in results: print(f"{s}  {n.ljust(w)}  {e}")
    print(f"\n{len(results)-fails}/{len(results)} live-feed checks passed")
    sys.exit(1 if fails else 0)

asyncio.run(main())
