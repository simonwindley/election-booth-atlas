# The Election Booth Atlas — Victorian state and federal results by polling place

A pipeline that pulls Victorian state (VEC) and federal (AEC) election results down to
polling-place level, puts them in one schema, pins each polling place to map coordinates,
and lets you follow the vote at a physical venue across elections regardless of boundary
changes.

## What's in the box

```
raw/                      # untouched source data
  aec/2010 … aec/2025     # AEC Tally Room CSVs, filtered to Victoria (events 15508, 17496, 20499, 24310, 27966, 31496)
  aec/senate              # Senate first preferences by polling place, scraped from the Tally Room's per-booth pages (no CSV exists)
  aec/pp_history          # 2016 and 2019 polling place lists (used only for venue matching)
  vec/2022/districts.json # scrape of all 87 VEC district result pages (FP by voting centre,
                          #   2CP by voting centre, full distribution of preferences)
  vec/2022/narracan_supplementary.json
  vec/2022/files/         # VEC indicative-distribution spreadsheets (38 districts) + TPP xlsx
  vec/2022/legislative_council/  # VEC Legislative Council .xls per region (votes received by
                          #   voting centre with ATL/BTL by candidate; the STV distribution)
  vec/2018/               # 2018 scrape (from the Internet Archive's copy of the old VEC results
                          #   site) + 2018 Legislative Council .xls files
  vec/2014/, vec/2010/    # 2014 and 2010 scrapes, also from the Internet Archive (latest 2020 captures)
  vec/2006/, vec/2002/, vec/1999/   # the old results site via the Internet Archive (2010-2012 captures): districts.json from tools/fetch_history.py; html/ page cache (not committed)
  aec/2004, aec/2007      # Tally Room CSVs (events 12246, 13745), national; the loader cuts them to Victoria
  vec/osm_geocodes_raw.json  # raw OpenStreetMap lookups for VEC-only booth names
  boundaries/             # Vicmap WFS extracts and AEC shapefiles as downloaded
data/
  vic2010/ … vic2022/, vic2023n/, vicby-*/, fed2010/ … fed2025/   # normalised CSVs, one set per election
  senate/                 # senators elected for Victoria at each federal election
  venues/                 # venue table, VEC booth -> venue matches, geocodes
  boundaries/             # simplified GeoJSON: vic_la_1991/2001/2013/2022, vic_lc_2005/2013/2022, fed_2003/2010/2018/2021/2024
  catchments/             # Voronoi booth catchments per election (+ H3 res-7 hex shares, review lists)
  bundle/                 # Parquet tables + GeoJSON + manifest.json (for DuckDB-style tooling)
site/                     # the Election Booth Atlas static site: app.html, index.html, build.py, data/ (see site/README.md)
  analysis/               # outputs of src/compare.py
  elections.sqlite        # everything in one database, with analysis views
live/                     # election-night poller (vec_live.py, stdlib only) and how to run it (live/README.md)
src/
  parties.py              # canonical party codes (ALP, LIB, NAT, GRN, ...) across both sources
  load_aec.py             # AEC CSVs -> schema
  load_vec.py             # VEC scrape JSON (+ indicative xls) -> schema
  load_lc.py              # VEC Legislative Council spreadsheets -> lc_* tables
  match_venues.py         # VEC voting centre names -> AEC venues with coordinates
  filter_geocodes.py      # keep only plausible OSM geocodes (inside district footprint, sane type)
  boundaries.py           # boundary layers -> data/boundaries/*.geojson
  catchments.py           # Voronoi booth catchments + H3 shares
  export_bundle.py        # Parquet/GeoJSON bundle for the static site
  verify.py               # hard reconciliation checks (run after any load)
  build_db.py             # assemble SQLite + views
  compare.py              # first state-vs-federal comparison at matched venues
tools/                    # helpers for moving data through the browser pane
```

## Schema (same for every election)

| table | key | notes |
|---|---|---|
| `elections` | election_id | state: `vic1999`, `vic2002`, `vic2006`, `vic2010`, `vic2014`, `vic2018`, `vic2022`, `vic2023n` (Narracan supplementary) and the by-elections `vicby-warrandyte-2023`, `vicby-mulgrave-2023`, `vicby-prahran-2025`, `vicby-werribee-2025`, `vicby-nepean-2026`; federal: `fed2004`, `fed2007`, `fed2010`, `fed2013`, `fed2016`, `fed2019`, `fed2022`, `fed2025` |
| `contests` | election_id, contest_id | a district (`vic-albert-park`) or division (`fed-197`); enrolment/formal/informal for VEC |
| `candidates` | election_id, candidate_id | surname, given_name, party_name (as published), `party` (canonical), ballot_position, elected |
| `booths` | election_id, booth_id | `booth_type` is `ordinary` (election-day booth), `early` (pre-poll centre), or a declaration type (`postal`, `absent`, `provisional`, `early_declaration`, `marked_as_voted`) which is a synthetic district-level row |
| `fp_votes` | election_id, booth_id, candidate_id | first preferences; informal votes carry candidate_id `INFORMAL` |
| `tcp_votes` | election_id, booth_id, candidate_id | two-candidate-preferred by booth |
| `dop` | election_id, contest_id, count_no, candidate_id | distribution of preferences: `transfer` (negative for the excluded candidate), `progressive_total`, `excluded` flag. Count 0 = first preferences. |
| `final_pair` | election_id, contest_id, candidate_id | the district page's own "votes after distribution of preferences" table (VEC), the authoritative final two |
| `dop_indicative` | as above | VEC "indicative" distributions for the 38 districts where the winner had a majority before the count finished |
| `venues` | venue_id | one physical premises (from AEC data, 2016–2025), with lat/lon, address, suburb |
| `vec_booth_venue` | booth_id | VEC voting centre -> venue with `method` (`exact_unique`, `exact_cluster`, `exact_nearest`, `fuzzy` = review, `unmatched`) |
| `geocoded` | booth_id | approximate coordinates for VEC booths with no AEC venue (Nominatim/OSM, locality level) |
| `booth_geo` | election_id, booth_id | every booth's venue_id (a `g-` prefixed pseudo-venue for geocoded booths), lat, lon and `geo_source` |
| `sen_groups` / `sen_booths` | election_id, booth_id | Senate first preferences by polling place (election-day and pre-poll booths only), per group: above-the-line votes and the group total including below-the-line; booth ids are the House ids. `senators_elected`: the six (twelve in 2016) Victorian senators per election, in order |
| `lc_contests` / `lc_candidates` / `lc_votes` / `lc_dop` | | Legislative Council: region totals and quota; groups + candidates (with an `ATL` pseudo-candidate per group); votes by voting centre x candidate/ATL (booth ids shared with the Assembly); the STV count (ballot papers, transfer value, progressive total per count, `elected` flags) |

Views: `booth_party_fp` (votes by canonical party per booth), `booth_party_share` (share of
formal vote), `venue_party_share` (the venue time series — party share at each physical venue
at each election).

## Reconciliation (`python3 -m src.verify data/<election>`)

* First preferences by voting centre sum exactly to the district formal vote, and informal to
  informal, for every district in 2010, 2014, 2018 and 2022 (documented exceptions, each in the election's
  `verify_exceptions.json`: Ripon 2018 and Prahran 2014, where the only booth-level count the VEC published
  predates the recount; and a handful of districts in 2010 and 2014 whose archived distribution page carries
  a first-preference total a few votes different from the rechecked district total).
* Seats: 1999 ALP 42, LIB 36, NAT 7, IND 3 (Frankston East is the supplementary election); 2002 ALP 62, LIB 17, NAT 7, IND 2; 2006 ALP 55, LIB 23, NAT 9, IND 1;
  2010 ALP 43, LIB 35, NAT 10; 2014 ALP 47, LIB 30, NAT 8, GRN 2, IND 1. Booth first preferences reconcile to the district formal vote in every
  district of 1999, 2002 and 2006 except the four whose booth page the Internet Archive never captured (Geelong 1999, Evelyn and Nepean 2002,
  Ferntree Gully 2006: district totals kept as one `all_votes` row) and two 2006 distribution-page totals that differ from the recheck (`verify_exceptions.json`). Federal (Vic): 2010 ALP 22 LIB 12 NAT 2 GRN 1;
  2013 ALP 19 LIB 14 NAT 2 GRN 1 IND 1; 2016 ALP 18 LIB 14 NAT 3 GRN 1 IND 1; 2019 ALP 21 LIB 12 NAT 3 GRN 1 IND 1.
* Senate booth totals reconcile to the booth formal vote in every election 2010–2025.
* Distribution of preferences: transfers at every count sum to zero and the final progressive
  totals equal the formal vote, for all 76 (2022) and 47 (2018) districts with an official distribution.
* Legislative Council votes by voting centre sum to the region formal vote in all 16 region-years.
* Seats: 2022 ALP 56, LIB 18 (+ Narracan = 19), NAT 9, GRN 4; 2018 ALP 55, LIB 21, NAT 6, GRN 3, IND 3.
  Upper house 2022: ALP 15, Coalition 14, GRN 4, LCP 2, SFF/DLP/AJP/ONP/LDP 1 each.

## Venue matching status (VEC 2018 + 2022, 2,135 distinct election-day voting centres)

* 2022: 1,417 of 1,729 booths (82%) matched to an AEC venue by name (exact, or the same name at
  venues within 2 km of each other across federal elections 2016–2025) — real premises
  coordinates (`geo_source = 'aec_name_match'`); 209 (12%) have locality-level OpenStreetMap
  coordinates (`geocoded_approx`, treat as ±1–2 km); 103 (6%) have none yet.
* 2018: 1,451 exact, 245 approximate, 98 none, of 1,794.
* Raw OSM hits are in `raw/vec/osm_geocodes_raw.json`, rejects in `data/venues/geocode_rejected.csv`;
  43 "fuzzy" name matches are listed in `vec_booth_venue` for manual review but are not used.
* Booths whose coordinates fall outside the district they served (mostly approximate geocodes,
  some genuine out-of-district venues) are listed in `data/catchments/outside_*.csv` and get no catchment.
* To do properly: the VEC's pre-election voting centre list (with street addresses) for 2022,
  and the 2026 list when it's published, would geocode every booth exactly.

## Things to know before analysing

* **Early voting dominates.** State 2022: ordinary election-day votes 1.04M vs early 1.49M,
  postal 0.32M. Federal 2022 (VIC): ordinary 1.65M vs pre-poll 1.35M + postal 0.63M. Booth
  maps only show election-day voters unless you add an allocation step.
* AEC pre-poll centres (`booth_type = 'early'`) have coordinates and booth-level results;
  VEC early votes are only reported at district level.
* VEC 2CP by voting centre exists for 70 of 87 districts; where 3+ candidates remained the VEC
  publishes the distribution instead.
* **Narracan 2022** was deferred to a supplementary election on 28 January 2023 after the
  Nationals candidate died during the campaign; Labor and the Nationals did not contest it and
  the final two were Farnham (Liberal) v Wolfe (Independent). It is election `vic2023n` in the
  database (so `vic2022` has 87 districts); the site folds it into 2022 and flags those rows
  with `supplementary`.
* Party codes: `LIB` and `NAT` are kept separate; combine for Coalition. Federal Greens in
  Victoria appear as `GVIC` in AEC data and map to `GRN`.

## 2026 pre-election register (`data/vic2026/`)

`contests.csv` (88 districts + 8 regions with who holds the seat now), `candidates.csv` (declared candidates
with party, incumbency, upper-house ticket position, source and capture date, plus `wikipedia_url`,
`parliament_url` for sitting members — slugs verified against parliament.vic.gov.au, kept in
`parliament_slugs.json` — and `party_url`, the party's candidate page), `retiring.csv`, `withdrawals.csv`,
`meta.json` (VEC key dates, postal and early voting details, the VEC district-page pattern). Source:
Wikipedia's candidate register, captured through the browser into `raw/vec/2026/wikipedia_candidates_raw_<date>.json`;
re-run `python3 -m src.load_2026 <raw> data/vic2026 <date>` after a fresh capture. The VEC's nominations
list (9 Nov 2026) should replace it.

In the site, 2026 is an election in the list from the start (2022 boundaries and booths, hollow; the
declared candidates with their links; each seat's history and voting information) and fills in from the
live feed on election night — see `live/README.md`.

## Opinion polls (`site/data/polls_vic2026.json`)

Published polling for the 2026 election, compiled from Wikipedia's "Opinion polling for the 2026
Victorian state election" page. To refresh it:

    python3 live/polls_update.py --publish     # fetches the page, rebuilds the JSON, commits and pushes

(`live/polls_update.py` is standard-library only; it expands the page's tables into grids in
`raw/polls/wikipedia_vic2026_polls.json` and then runs `src.load_polls`, which parses them: statewide voting intention (primary, 2PP, alternative 2PP
splits, with leadership-change events), three-party preferred, Legislative Council intention,
sub-state breakdowns, MRP seat tallies, preferred premier and approval, subpopulations and the one
seat poll.) Dates are the last day of fieldwork. The Roy Morgan One Nation winnability ranking is
kept by hand in `raw/polls/roymorgan/` and merged in. The Polls tab in the site is entirely separate
from the dashboard and the live projections.

## Demographics (`site/data/demog_<boundaries>.json.gz`)

2021 Census indicators by electorate, one file per boundary set, all in the same shape
(`indicators`, `state`, `districts` keyed by contest id):

* `demog_vic_la_2022` — the 88 districts on the 2022 boundaries (used in 2022 and 2026), built from the
  ABS SA1 DataPacks for 2021, 2016 and 2011 (`raw/abs/datapacks/`, the `*_SA1_for_VIC_short-header.zip`
  files, not committed: download them from abs.gov.au/census/find-census-data/datapacks and extract the
  needed tables to `raw/abs/datapacks/csv/<year>/`). Each SA1 (a few streets,
  a few hundred people) is split across the districts and across the 2022 booth catchments by area
  (`python3 -m src.sa1_weights`, boundaries fetched with `tools/fetch_sa1.py` into `raw/boundaries/abs/`, also
  not committed),
  and every indicator is a numerator and denominator summed over the pieces (`python3 -m src.load_sa1_census`
  -> `raw/abs/sa1_census_<year>.json`), so shares are exact aggregates of the small-area counts.
  `python3 -m src.build_demog` then assembles the site file: the 2021 figures, the Parliament of Victoria
  Library's "Electorate data cards" (`raw/demographics/`) for the true district medians and a few extras,
  `chg16_*` / `chg11_*` change indicators (points for shares, per cent for medians and counts) and a
  `history` block with the 2016 and 2011 figures per district; `python3 -m src.model_issues` adds the
  modelled issue priorities. Checked against the cards: district populations agree to 0.2% on the median
  seat (worst Ripon 1.8%); shares such as renting or born in Australia agree to three decimals. Medians
  other than the cards' are population-weighted means of the SA1 medians, which run a little high.
* Modelled attitudes on both files: `python3 -m src.model_issues` (issue priorities, from the Herald Sun /
  Freshwater breakdowns, `raw/polls/issues_vic2026.json`) and `python3 -m src.model_mood` ("democratic mood",
  from the McKinnon Index 2026 unit records captured from its dashboard into `raw/mood/mckinnon_2026.json`:
  a weighted regression of each attitude on age, education, household income, birthplace, language and
  remoteness, applied to each area's census mix as a shift from Victoria's). Both are labelled modelled on
  the site; neither is a poll of the area.
* Each modelled indicator carries the window its survey speaks for (`from`/`to`), and the site shows it only for
  elections inside that window: the Freshwater issues and McKinnon 2026 (`mood_*`, July 2026 fieldwork) for 2026
  on; the McKinnon Index 2025 (`mood25_*`, `raw/mood/mckinnon_2025.json`, n=4,416 with the respondent's state; state
  code 1 is Victoria, ~1,000 respondents) for the 2025 contests only, levelled on the Victorian respondents. The 2025
  layer sits on `demog_vic_la_2022` (the 2025 by-elections) and on `demog_fed_2024` (the 2025 federal election).
* `demog_fed_2024` — the 2021 Census on the Victorian federal divisions as redrawn in 2024 (used in 2025): SA1s
  apportioned by area (`src.sa1_weights` 2021 writes an `f24` weight set; `src.load_sa1_census` aggregates it into
  `sa1_census_2021.json` under `fed_2024`; `src.build_demog` writes the file). Same ids as the district series.
* The Australian Election Study integrated time series (1967-2025, Australian Data Archive, doi:10.26193/HJ3KT1) is
  in `raw/aes/` on the Mac only: gitignored, because the ADA terms forbid passing on the unit records. Anything built
  from it is computed on the Mac and only summary coefficients leave it; published outputs must acknowledge the AES
  investigators and the ADA, state that they bear no responsibility for the analysis, and the ADA asks to be emailed
  (ada@anu.edu.au) a link to published work. The general release has no state or electorate (a restricted release
  with geography can be requested).
* `demog_booth_vic2022` — the same build for every 2022 election-day booth catchment (the area nearest the
  booth within its district), keyed by venue id so a booth at the same venue in any election can use it,
  stored column-wise (`cols` + one `v` array per venue; `hcols` + `h` for the 2016 and 2011 history of the
  headline indicators). Not who votes at the booth: early, postal and absent votes are counted elsewhere.
* The 2006 Census: the ABS no longer distributes 2006 small-area DataPacks, so the Collection District (CD) tables come from
  TableBuilder (Victoria, all 9,311 CDs, 16 tables: age, sex, Indigenous status, birthplace region, language, English
  proficiency, religion, Year 12, qualification level, occupation, labour force status, personal income, tenure, landlord type,
  dwelling structure, internet), saved in `raw/abs/tablebuilder/2006/` and flattened to `cd2006_tables.json`. The CD boundaries
  are the ABS ASGC 2006 digital boundaries (`raw/boundaries/abs/cd06/`, cat. 1259.0.30.002). `python3 -m src.cd_weights`
  apportions CDs by area to the 2022 districts and booth catchments, the 2001 districts and the 2003-2010 federal divisions;
  `python3 -m src.load_cd_census` builds the indicators (same ids as the SA1 series where the definition matches; medians are
  interpolated from the aggregated bands, so they are true medians) into `raw/abs/sa1_census_2006.json` (read by
  `src.build_demog` as a fourth year of history and `chg06_*` change indicators on the 2022 files) and `raw/abs/cd_census_2006.json`.
  `src.build_demog` also writes `demog_vic_la_2001` (the 2002, 2006 and 2010 state elections) and `demog_fed_2003` (the 2004,
  2007 and 2010 federal elections).
* `demog_vic_la_1991` — the 2001 Census for the 88 districts used at the 1999 election. The 2001 Census was coded to the
  districts then in force (drawn in 1991), so the ABS 2001 Basic Community Profile for each State Electoral Division is
  exactly one 1999 district and nothing is apportioned. `python3 tools/fetch_bcp2001.py raw/abs/bcp2001` downloads the 88
  profiles plus Victoria (`BCP_SED*.xlsx`, `BCP_2.xlsx`; gitignored, 32 MB) and `python3 -m src.load_bcp2001` writes the
  file: 64 indicators with the 2006-2021 ids where the definition matches. Place of enumeration (census night), medians
  interpolated from the profile bands in 2001 dollars, occupations on ASCO (managers, professionals, trades, labourers and
  production/transport are close to the later ANZSCO groups; clerical/sales/service are not carried), English proficiency
  for the overseas-born only, internet as personal use (no household question until 2006), plus households with no car.
  TableBuilder Basic does not carry 2001, so there is no 2001 series on today's boundaries or for booth catchments.
* `demog_vic_la_2013` — the districts as drawn in 2013 (ABS "SED 2021"), used at the 2014 and 2018
  elections: 190-odd indicators from 20 General Community Profile tables (age bands, birthplace by
  country, ancestry, language, religion by denomination, education, income bands, tenure, dwellings,
  vehicles, labour force, occupation, industry, travel to work, need for assistance, volunteering).
* `demog_fed_2021` — the 39 federal divisions as at 2021 (ABS "CED 2021"), used at the 2022 election,
  same tables.

The ABS tables come from the ABS Data API (data.api.abs.gov.au, SDMX): the browser-side capture in
`raw/abs/c21_<geo>_vic.json` keeps, for each table, the Victorian regions' cells with persons totals for
sex and age; `python3 -m src.load_abs_census SED|CED <out>` turns them into shares. Notes: state medians
in the ABS files are population-weighted means of the district medians; the 2021 Census fell in
Melbourne's lockdown, so travel-to-work figures describe that week. (The earlier SA2-based build of the
2022 file, `src.sa2_weights` + `load_abs_census SA2`, is superseded by the SA1 DataPacks.)

The site picks the file matching each election's boundary set and falls back to the nearest by seat
name (2010 and the 2001 boundaries use the 2013 file; 2019 and 2025 federal use the 2021 divisions);
`DEMOG_ALIAS` in `app.html` maps the same quantity between the Parliament and ABS ids so the
correlation-over-time chart can cross boundary sets.

## Preference flows and how-to-vote cards (`site/data/pref_flows.json`, `site/data/htv_<election>.json`)

`python3 -m src.pref_flows` reads every distribution of preferences as a set of exclusions (from-party,
parties still standing, votes to each) and fits a Luce choice model per voter-party, per election and as a
2026 blend (state 2022 weighted 2, federal 2025 and the by-elections 1, earlier elections 0.5 and 0.25). The
browser runs first preferences through the exclusions with those flows to give a two-candidate figure for any
pair (Dashboard spectrum "Modelled", the seat panels, the Preferences tab). Validation: fitted on 2018 and
2019, run on the 2022 first preferences, 75 of 76 final pairs and 74 winners right, mean 2CP error 1.8 pts
(median 1.2). Each pile keeps its composition by origin candidate and every sub-pile moves by its own origin
party's flow and follows its own origin's card; treating a pile as the excluded party's voters gives 2.5 pts.

The registered how-to-vote cards are the other half. `tools/fetch_htv.py <register> <dir>` downloads the
PDFs listed in a register capture (`raw/htv/register_2022.json` is the VEC's 2022 archive; the 2026 register
comes through `live/vec_daily.py`); `tools/parse_htv.py <election> <register> <dir> <out>` reads each
card's ordering (PDF text layer, then page OCR, then a crop of the box beside each name; `--retry` re-reads
partial cards, `--seconds N` stops after a budget so it can run in chunks). `python3 -m src.htv_follow`
compares every 2022 exclusion with the excluded candidate's card (concordance, lift over the flow model, and
a fixed-effects follow rate per party where the party's cards varied across seats);
`python3 -m src.build_htv` writes the site file: card orders per seat, follow rates, each party's typical
ordering of the others. In the browser a card moves a pile only where it differs from the usual card the
flows were fitted with: that share of the pile (the follow rate) goes to the card's next name, the rest
follows the flow. Follow rates the regression cannot identify (Labor, Liberal, National: cards that never
varied in 2022) are assumed; the Liberal 0.22 is the 2018-to-2022 Labor/Greens swap.

`python3 -m src.ballot_effects` measures ballot-order voting from the same distributions: the first-preference
bonus for the candidate drawn first (about +1.2 pts for minor parties, every election) and, at each exclusion, the
share of the pile that goes to the names printed next to the excluded candidate beyond what the fitted flows and the
card explain (about 4.4% to the next below, 3.7% to the next above, 2.5% to the top of the ballot, consistent from
2014 to 2025, larger on long ballots and for minor-party and independent piles). The ballot draw is random, so the
estimate is clean. Seat-level shares are correlated with the SA1 census profile (highest where another language is
spoken at home, lowest in secular inner-city electorates). The browser model applies the pooled terms whenever ballot
positions are known (`site/data/ballot_effects.json`).

`python3 -m src.ballot_booths` takes the position-1 bonus to booth level: each booth's first-preference deviation
from its electorate, modelled with every party's own census gradient taken out, leaves the position-1 candidate's
excess by booth catchment profile (37k booth-candidate observations, 252 electorate-elections). Age is the strongest
signal (the youngest quarter of booths give the first-drawn candidate ~0.65 pts more than the oldest), then language
and birthplace; education and income barely matter. Each venue gets a susceptibility score (predicted position-1
bonus relative to the average booth), shown in the booth panel; the browser model scales its ballot-adjacency term
by it (x0.5 to x2) at booth level and by the booth-weighted mean at electorate level (`site/data/ballot_booths.json`).

## The election-night projection (`app.html`, "Projected" on the 2026 map)

What the final result looks like given what is counted, what is still to come and how the uncounted parts are
expected to vote. Every pool of an electorate is projected separately and the pools are summed: each election-day
booth is its count once reported, otherwise its 2022 result at that venue shifted by a swing estimate (the
electorate's counted booths, the nearest counted booths within 8 km and the state, blended by how much of each is
in, plus the statewide within-electorate demographic gradient of the swing applied to the booth's own SA1 census
profile once 80+ booths are in); early, postal, absent and provisional votes are the electorate's 2022 pools shifted
by the electorate's swing, each keeping its own lean, sized by 2022 (enrolment-adjusted) or by the VEC's
early-voting statistics / postal applications when captured, and replaced by the counted pool as it arrives (fully
trusted once a third is in). The projected first preferences for this year's candidates then run through the
preference model (flows, cards, ballot order) for the projected two-candidate result. Booth level: the same for one
booth. The seat panel shows the pools, the projected first preferences and the ladder; hover text gives the share of
the expected vote counted. Uncounted pools also take the statewide differential between that vote type's swing and
the booths' swing once ten electorates have the pool a fifth counted.

The dashboard calls seats on the projection: a call needs the projected margin to clear a bar that tightens with the
share of the expected vote counted (8 pts at 15%, 6 at 30%, 4 at 60%, 2.5 at 85%; leaning at half), and is withheld
while the model on the count so far or the VEC's own pair has a different leader, or while the last candidate
excluded in the modelled count was within reach of the runner-up. The seat spectrum has a Projected mode while
counting; the VEC's indicative pair stays in the table as a column.

`tools/synth_feed.py OUT.json --swing-coal 6 --swing-grn 1.5 --reported 0.65 --pools early --tcp 0.8` writes a
synthetic election-night feed from the 2022 results (uniform swing with booth noise, a share of booths in, chosen
pools counted) in the live feed's format, for rehearsing the 2026 pages: copy it to `site/data/live/latest.json`.

## Boundaries and catchments

`data/boundaries/*.geojson` carry a `contest_id` matching the results tables, simplified to ~30 m.
`data/catchments/<election>.geojson` is a Voronoi cell per election-day booth clipped to the
district it served (`booth_id`, `contest_id`, `area_km2`); `h3_<election>.csv` spreads each booth
over H3 resolution-7 hexagons so booth results can be re-aggregated onto a fixed grid in the
front end. Catchments are a modelling choice, not a VEC product: they assume voters use the
nearest booth, which is roughly true in suburbs and less so in the country.

## Front-end bundle (`data/bundle/`)

Parquet copies of every table and view plus the GeoJSON layers and a `manifest.json`, ~14 MB.
This is what the static site loads (DuckDB-WASM for the tables, MapLibre for the layers).

## Analyses and the question registry (`analysis/questions.json`)

Every question asked of the data is listed in `analysis/questions.json`: the question, the command that answers it,
its inputs and outputs, the current headline finding, and the data events ("triggers") that should prompt a re-run,
for example `results_2026`, `nominations_2026`, `census_2026`, `federal_next`. `tools/rerun_analyses.py` reads it:

    python3 tools/rerun_analyses.py                          # list questions, status, last run
    python3 tools/rerun_analyses.py --trigger results_2026   # re-run everything new results touch, in dependency order
    python3 tools/rerun_analyses.py --id seat_loss --deps    # one question and what it depends on
    python3 tools/rerun_analyses.py --due                    # questions whose inputs changed since they last ran
    add --dry-run to see the commands, --pages to rebuild the private EBA Dark pages in analysis/dark/ (not committed)

Runs are logged in `analysis/runs.json`. Analyses so far: `src/member_effects.py` (personal vote, tenure, leaders,
transferred voters, 2026 outlook), `src/cross_level.py` (state v federal), `src/seat_loss.py` (what predicts a member
losing), `src/notional.py` (notional results on new boundaries, all seven redistributions) and `src/boundary_effects.py`
(what redistributions do to seats and members), `src/primary_swings.py` (how primaries swing seat by seat; 2026
projected from primaries through preferences), `src/returning_challengers.py` (candidates who lost and come back).
Outputs in `data/analysis/`.

## Re-running

```
python3 tools/fetch_history.py aec 2007 raw/aec/2007               # the 2004 (12246) and 2007 (13745) Tally Room CSVs (national; the loader cuts them to Victoria)
python3 tools/fetch_history.py vec 2006 raw/vec/2006               # 1999, 2002 and 2006: the old VEC results site via the Internet Archive -> districts.json
python3 -m src.load_aec 12246 2004 raw/aec/2004 data/fed2004      # likewise 13745 2007
python3 -m src.load_aec 15508 2010 raw/aec/2010 data/fed2010      # likewise 17496 2013, 20499 2016, 24310 2019
python3 -m src.load_aec 27966 2022 raw/aec/2022 data/fed2022
python3 -m src.load_aec 31496 2025 raw/aec/2025 data/fed2025
python3 -m src.load_senate 27966 2022 raw/aec/senate/senate_pp_27966.json data/fed2022   # and the other five events
python3 -m src.load_vec 2022 raw/vec/2022/districts.json data/vic2022
python3 -m src.load_vec 2018 raw/vec/2018/districts.json data/vic2018
python3 -m src.load_vec 2014 raw/vec/2014/districts.json data/vic2014   # districts.json = normalise_2018() over districts_wayback.json
python3 -m src.load_vec 2010 raw/vec/2010/districts.json data/vic2010
python3 -m src.load_vec 2006 raw/vec/2006/districts.json data/vic2006   # likewise 2002, 1999 (tools/fetch_history.py writes the normalised shape directly)
python3 -m src.load_lc 2022 raw/vec/2022/legislative_council data/vic2022
python3 -m src.load_lc 2018 raw/vec/2018/legislative_council data/vic2018
python3 tools/fetch_lc_history.py                                  # 2006, 2010, 2014 upper-house .xls via the Internet Archive
python3 -m src.load_lc 2014 raw/vec/2014/legislative_council data/vic2014
python3 -m src.load_lc_old 2010 raw/vec/2010/legislative_council data/vic2010   # likewise 2006 (region totals only; no group letters or ATL split in the 2006 files)
python3 tools/export_lc.py data site/data                          # just the site's upper-house files (export_site does the same as part of a full export)
# by-elections: raw/vec/by_<seat><year>.json -> data/vicby-<seat>-<year> (see src/load_vec.load)
python3 -m src.load_2026 raw/vec/2026/wikipedia_candidates_raw_2026-10-31.json data/vic2026 2026-10-31
python3 -m src.verify data/vic2022 && python3 -m src.verify data/vic2018
python3 -m src.match_venues data/vic2022/booths.csv,data/vic2018/booths.csv,data/vic2014/booths.csv,data/vic2010/booths.csv,data/vic2023n/booths.csv,<by-election booths…> data/venues data/fed2025/booths.csv data/fed2022/booths.csv data/fed2019/booths.csv data/fed2016/booths.csv data/fed2013/booths.csv data/fed2010/booths.csv
python3 -m src.match_old_aec data/venues data/fed2007/booths.csv data/fed2004/booths.csv   # 2004/2007 federal booths -> venues (by premises+coordinates, then polling-place id); appends 2007-only premises to venues.csv
python3 -m src.filter_geocodes raw/vec/osm_geocodes_raw.json data
python3 -m src.boundaries
python3 -m src.build_db data/elections.sqlite data
python3 -m src.catchments data/elections.sqlite            # optionally a comma-separated list of election ids to rebuild
python3 -m src.export_bundle data/elections.sqlite data/bundle
python3 -m src.compare data/elections.sqlite
```

Requires pandas, xlrd, openpyxl, shapely, pyshp, h3, pyarrow.

## Source notes

* VEC 2022 results: https://www.vec.vic.gov.au/results/state-election-results/2022-state-election-results
  (per-district HTML pages; Legislative Council .xls per region from the VEC's Azure blob store).
* VEC 2018 results: the current VEC site no longer serves them; the old results site
  (vec.vic.gov.au/Results/State2018/) is preserved by the Internet Archive and was scraped from there
  (captures from late 2019, i.e. final rechecked figures).
* VEC indicative distributions: https://www.vec.vic.gov.au/results/electoral-statistics/state-election-statistics/full-preference-distributions
* AEC Tally Room downloads: https://results.aec.gov.au/27966/Website/HouseDownloadsMenu-27966-Csv.htm and .../31496/...; the 2004 (event 12246, no coordinates in its polling-place list) and 2007 (13745) menus are still served. Polling-place ids are stable across elections, which is how the 2004 booths get their venues (`data/venues/aec_old_booth_venue.csv`, method `id_2007` when the 2007 list names the same premises, `id_only` when it cannot be checked).
* VEC 1999, 2002 and 2006 results: the old results site (`vec.vic.gov.au/Results/state2006result<District>District.html` and its FPVbyVotingCentre / TCPbyVC / distribution pages) as captured by the Internet Archive in 2010-2012; `tools/fetch_history.py`. From 1999 to 2006 the voting-centre tables list the early voting centres of other districts as rows (`… E Centre`, loaded as `booth_type = 'early'` with their own ids) and call provisional votes "Declaration Votes".
* Boundaries: Vicmap Admin state assembly/council polygons via the DataVic WFS (open-data-platform:state_assembly_1991/2001/2013/2022 (1991: the 1999 election; its "Forest Hills" is corrected to Forest Hill), state_council_1991/2001/2005/2013/2022); AEC Victorian division files: February 2010 (MapInfo, used at the 2010 election), December 2010 (2013 and 2016), July 2018 (2019), July 2021 (2022), October 2024 (2025).
* Senate by polling place: the Tally Room's `SenatePollingPlaceFirstPrefs-<event>-<pp>.htm` pages (and the 2010/2013 VTR equivalents), ~2,000 per election, parsed in the browser into `raw/aec/senate/senate_pp_<event>.json`.
