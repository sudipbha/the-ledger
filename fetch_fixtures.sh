#!/usr/bin/env bash
# Capture the eight feeds used by qa_live.py.
# Publisher content isn't committed to this repo — run this once before the live suite.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p fixtures

fetch() { curl -sfL --max-time 25 -A "Mozilla/5.0" -o "fixtures/$1" "$2" && echo "  $1"; }

echo "fetching feed fixtures…"
fetch cnbc.xml          "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"
fetch bbc.xml           "https://feeds.bbci.co.uk/news/business/rss.xml"
fetch fed.xml           "https://www.federalreserve.gov/feeds/press_all.xml"
fetch mw.xml            "https://feeds.content.dowjones.io/public/rss/mw_topstories"
fetch noahpinion.xml    "https://www.noahpinion.blog/feed"
fetch conversation.atom "https://theconversation.com/us/business/articles.atom"
fetch awocs.xml         "https://awealthofcommonsense.com/feed/"
fetch boe.xml           "https://www.bankofengland.co.uk/rss/news"
echo "done — now run: python3 qa_live.py"
