# The Ledger

A quiet reader for high-quality, free-to-read financial journalism, built to look and feel like a broadsheet business paper on an iPhone 17 Pro Max. No adverts, no trackers, no paywall circumvention. Every article keeps its byline, its publication and a link home.

## What it does

The front page is arranged like a newspaper: one lead story, secondary stories underneath, and a *Long reads* rail beside it on wider screens. Section tabs across the top cover Markets, Companies, Economics, Central Banks, Opinion, Tech & Finance and Personal Finance, plus your saved articles. Search, bookmarking, mark-as-read, pull-to-refresh and a reading-progress bar are all there, and there is a full dark reading mode.

Every article has two buttons that matter. **Listen** reads the piece aloud — with your own OpenAI API key it uses OpenAI's speech models and sounds close to a human presenter, and without a key it falls back to the voice built into your phone, so the button always works. **Copy** puts the whole article on your clipboard as clean plain text: headline, publication, author, date, original link, then the body.

## Getting it onto your iPhone

The app is a folder of static files. It needs to be served over HTTPS for the service worker, Add-to-Home-Screen and clipboard access to work, so opening `index.html` straight off the filesystem will only give you a partial experience.

The quickest route is **Netlify Drop**: go to `app.netlify.com/drop` on your laptop and drag this whole folder onto the page. You get an HTTPS URL in a few seconds, with no account needed to start. Open that URL in Safari on your phone, tap the share icon, then *Add to Home Screen*.

For **GitHub Pages**, commit these files to a repository, then in Settings → Pages set the source to your branch and root folder. Your URL will be `https://<user>.github.io/<repo>/`. **Cloudflare Pages** and **Vercel** both work the same way — point them at the folder, no build command, no output directory.

Once installed to the home screen the app runs full-screen with the salmon status bar, and the service worker keeps the shell and your last-read articles available when you lose signal.

## Adding your OpenAI key

Open Settings (the gear in the masthead), paste a key that starts with `sk-`, choose a model and a voice, and save. The key is written to this browser's `localStorage` and is sent to exactly one place: `https://api.openai.com/v1/audio/speech`. It is never transmitted anywhere else, there is no server in this app to send it to, and you can clear it by emptying the field and saving again.

`gpt-4o-mini-tts` is the default and the best value; `tts-1-hd` is the higher-fidelity older model. Long articles are split into sentence-aware chunks of roughly 3,800 characters, queued so playback is seamless, and each generated chunk is cached in IndexedDB — so re-listening to an article costs nothing. *Clear audio cache* in Settings empties that store.

Lock-screen and background playback use the Media Session API, so the title, skip-back-15 and skip-forward-15 controls appear on your lock screen and in AirPods gestures.

## Changing the sources

Open `index.html` and find the `SOURCES` array near the top of the script. Each entry looks like this:

```js
{n:"Calculated Risk", u:"https://calculatedrisk.substack.com/feed", s:"Economics", h:true, q:1.25}
```

`n` is the display name, `u` is the RSS or Atom URL, `s` is the fallback section when the text gives no clearer signal, `h:true` marks a heavy full-text feed (fetched in a second wave so the front page paints fast), and `q` is a quality weight used when choosing the lead story — analysts and central banks sit above 1.0, wire filler below. Delete a line to remove a source; add a line to add one. Nothing else needs to change.

Every feed shipped here was checked by hand: public, free, no login and no paywall. The Financial Times, WSJ, Bloomberg and The Economist are deliberately absent. Settings shows a live list of which feeds answered on the last refresh and how many items each returned.

## How it handles article text

Browsers cannot read cross-origin RSS directly, so feeds are fetched through public CORS relays with a fallback chain (`api.allorigins.win`, then `corsproxy.io`, then `api.codetabs.com`). If all of them fail, the app shows whatever is already cached on your device rather than an empty screen.

Where a publisher's own feed carries the full text — most of the independent analysts do — the whole article is rendered, sanitised of scripts, iframes and inline handlers, with attribution and a link to the original. Where the feed carries only a summary, the summary is shown with a prominent *Read at source* link. The app never scrapes past a paywall and never fetches anything a feed did not publish.

A note on the *Long reads* rail: it is ranked by depth and source quality, not by readership, because a static client has no way to know what other people are reading. It is labelled honestly rather than called "most read".

## Files

`index.html` is the entire application — markup, styles and logic in one file. `sw.js` is the offline shell. `manifest.webmanifest` plus the PNG icons make it installable. `qa.py` and `qa_live.py` are the test suites, and `fetch_fixtures.sh` captures the feeds the live suite reads.

Only the first four files plus the icons need to be deployed. The tests and this README can stay behind.

## Tests

Both suites drive headless Chromium at a 440 × 956 viewport with touch and mobile emulation.

```
pip install playwright && playwright install chromium

python3 qa.py            # 27 checks: layout, touch targets, copy, listen fallback,
                         # dark mode, settings persistence, manifest, service worker
./fetch_fixtures.sh      # capture eight real feeds (not committed — see .gitignore)
python3 qa_live.py       # 20 checks: sectioning, dedupe, bylines, sanitisation,
                         # copy fidelity, TTS chunking against real publisher output
```

The live suite intercepts the relay request and answers with the captured feeds, so it exercises the real fetch-and-parse path without depending on the network being up. Publisher feed content is deliberately not committed to this repository.

## Known limits

Clipboard writes and the service worker need HTTPS or `localhost`. Background audio on iOS keeps playing while the screen is locked once playback has started, but Safari will not start playback without a tap. The device-voice fallback has no seek bar — the skip buttons move between chunks instead. Feed relays are free public services and occasionally rate-limit; the app degrades to cached content when that happens rather than failing.
