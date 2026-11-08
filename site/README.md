# The Election Booth Atlas — static site

`index.html` is self-contained apart from two libraries from cdnjs (MapLibre GL, AlaSQL), Google Fonts,
and the basemap tiles (OpenFreeMap). It reads the files in `data/` (gzipped JSON/GeoJSON, decompressed in
the browser; `manifest.json` says which format is in use).

Run locally:  `python3 -m http.server 8000` in this folder, then open http://localhost:8000/

Visit counting: `build.py` adds a GoatCounter snippet (electionboothatlas.goatcounter.com) that loads only
when the page is served from `electionboothatlas.org` (or the old `github.io` address), and counts one hit per tab opened — nothing on localhost
or in previews, no cookies. `app.html` itself carries no tracking.

Deploy: push this folder to any static host (GitHub Pages, Netlify, Cloudflare Pages). No build step,
no server. To regenerate after the data changes:

    python3 -m src.export_site data/elections.sqlite site/data   # from the project root
    python3 site/build.py                                          # rewrites index.html from app.html

`app.html` is the page body (also what the claude.ai artifact publishes); `build.py` wraps it with the
document skeleton and sets the basemap URL. Pass "" to build.py for a version with no basemap.

## Election night

`live/vec_live.py` (see `live/README.md`) writes `site/data/live/latest.json`; the page polls it every minute,
rebuilds the 2026 rows of every table from it, outlines booths and electorates whose figures changed since
"Mark all seen", and projects electorate 2CP results from booth-by-booth swings against 2022.
