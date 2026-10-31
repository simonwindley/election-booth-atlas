# Election-night live feed

`vec_live.py` polls the VEC's results pages and writes a compact feed that the Booth Atlas reads.
Standard library only, so it runs on a stock Mac `python3` with no installs.

## Before the night (rehearsal, any time)

The VEC's 2022 pages have exactly the layout the 2026 pages will have, so you can rehearse with them.
From the project folder on the Mac:

    python3 live/vec_live.py --election-id vic2026 \
        --base https://www.vec.vic.gov.au/results/state-election-results/2022-state-election-results \
        --districts richmond,dandenong,melbourne --once

    cd site && python3 -m http.server 8000      # then open http://localhost:8000/ and pick "Victorian state election 2026"

The 2026 layer fills with the 2022 figures for those districts (labelled as 2026 — it is a rehearsal), the
changed booths get the bold outline, and the electorate view shows the projection. When you are done:

    rm -rf site/data/live        # so the 2026 layer goes back to the pre-election preview

## On the night (Saturday 28 November, counting starts 6 pm)

    python3 live/vec_live.py --base auto --loop 60

`--base auto` finds the 2026 results page from the VEC's results hub (and falls back to the expected URL
`.../2026-state-election-results`). If the VEC publishes under a different slug, pass it with `--base`.
A full cycle is 88 district pages plus their booth pages, about 5–7 minutes at the polite 0.8 s spacing the
VEC's rate limiting needs (it answers HTTP 999 when hurried; the script backs off and retries). `--loop 60`
waits a minute between cycles. Leave it running in a Terminal window; Ctrl-C stops it.

Serve the site from the same folder (`cd site && python3 -m http.server 8000`) and open
http://localhost:8000/. The page re-reads the feed every minute and shows "Live · 7:42 pm" in the box under
the election list. Opening `index.html` directly from Finder will not work — browsers block data loading
from `file://` pages — it has to be the little web server.

## Before the night: the daily capture

    python3 live/vec_daily.py              # once a day from 4 November; add --publish for the GitHub Pages site

captures what the VEC has published so far into `site/data/live/daily.json` (and a dated copy in
`site/data/live/daily/`): electors per district from the roll statistics spreadsheet (the close-of-roll
figures appear after 3 Nov), the official candidates once nominations are declared (9 Nov; they replace the
Wikipedia register in the 2026 seat panel), every registered how-to-vote card with its PDF (10–20 Nov), and
any early-voting / postal-vote statistics pages it can find from the election page (kept raw, and turned into
a per-district daily series where a table has a District column). The 2026 seat panel shows all of this under
"Before election day". Pages that do not exist yet are skipped; if the VEC puts a statistics page somewhere
the script does not look, add its path to `live/daily_sources.json`.

## What the feed contains

    site/data/live/latest.json      everything now: per district the summary, candidates with first
                                    preferences, final pair / 2CP totals, distribution, and per booth the
                                    first preferences and 2CP, each with `first_seen` / `updated_at` stamps
    site/data/live/changes.json     rolling log of what changed when (newest first)
    site/data/live/status.json      last cycle's timings, fetch count and any failed URLs
    site/data/live/snapshots/       one gzipped copy of latest.json per cycle, to replay the night later

Booth ids are the same as the 2022 ones (`vic-richmond-abbotsford`), so booths line up with their history
automatically; new booths the VEC adds for 2026 appear without coordinates until geocoded.

## What the site does with it

* Dashboard (the first tab): the statewide count — primary vote by party against 2022 in the districts
  counting so far, seats called / leaning / in doubt with the majority line, the seat spectrum (one box per
  seat from the strongest Labor seat to the strongest Coalition seat, by primary leader or 2CP), and every seat with its
  leader, margin, swing and how much is counted, filterable to the seats changing hands. Re-renders on
  every feed change. A seat is "called" by the page's own rule (projected or counted 2CP lead of 8 pts
  with 15% of booths in, 5 pts with 30%, 3 pts with 60%), "declared" when the VEC publishes the
  distribution or names the member.

* Booths: hollow until they report; coloured by whichever metric is chosen; a bold outline on any booth
  whose figures changed since you last pressed "Mark all seen" (the list in the live box is the same thing,
  newest first, click to jump).
* Electorates, "Winner after preferences": while the count is partial the 2CP is projected — the 2022
  result in that district plus the vote-weighted swing measured at the booths that have reported, booth
  by booth against the same booth in 2022, where the final two are the same party pairing as 2022.
  Otherwise the raw count so far; once the VEC publishes the distribution, the official figure.
* Pre-poll, postal and absent votes are district-level rows and show in the district panel's "counted"
  line and in the electorate totals, never on the booth map.

## Options

    --districts a,b,c    limit to some districts (slugs as in the VEC URLs)
    --delay 0.8          seconds between page fetches
    --no-snapshots       skip the per-cycle snapshot files
    --fixtures f.json    offline test against saved pages ({url path: html})
    --out DIR            write somewhere other than site/data/live
