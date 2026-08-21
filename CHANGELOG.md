# Changelog

All notable changes to The Ledger. Dates are UTC.

## 2026-08-21

### Added
- **Refresh button in the masthead and article reader.** Tap it after you
  publish a change: it unregisters the service worker, clears the offline
  caches, and reloads a cache-busted copy of the site so `content.js` and
  `index.html` updates land immediately instead of waiting for the next launch.

