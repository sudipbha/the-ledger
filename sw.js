/* The Ledger — offline shell.
   Caches the app itself and the last pages you opened, so a dropped signal
   doesn't cost you your reading. Feeds and audio are cached separately
   (localStorage / IndexedDB) by the app. */

const SHELL = "ledger-shell-v1";
const RUNTIME = "ledger-runtime-v1";
const FILES = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-180.png"
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(SHELL)
      .then(c => Promise.allSettled(FILES.map(f => c.add(new Request(f, {cache:"reload"})))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== SHELL && k !== RUNTIME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // never touch the speech API or the CORS relays — always live
  if (/api\.openai\.com|allorigins|corsproxy|codetabs/.test(url.hostname)) return;

  // navigations: serve the app shell, fall back to network
  if (req.mode === "navigate") {
    e.respondWith(
      caches.match("./index.html").then(hit => hit || fetch(req).catch(() => caches.match("./")))
    );
    return;
  }

  // fonts, icons, same-origin assets: cache first, refresh in background
  e.respondWith(
    caches.match(req).then(hit => {
      const live = fetch(req).then(res => {
        if (res && res.ok && (url.origin === location.origin || /fonts\.(googleapis|gstatic)\.com/.test(url.hostname))) {
          caches.open(RUNTIME).then(c => c.put(req, res.clone()));
        }
        return res;
      }).catch(() => hit);
      return hit || live;
    })
  );
});
