# Election Analyser — Victorian state and federal results by polling place

A pipeline that pulls Victorian state (VEC) and federal (AEC) election results down to
polling-place level, puts them in one schema, pins each polling place to map coordinates,
and lets you follow the vote at a physical venue across elections regardless of boundary
changes.

## What's in the box

```
raw/                      # untouched source data
  aec/2022, aec/2025      # AEC Tally Room CSVs, filtered to Victoria (event 27966, 31496)
  aec/pp_history          # 2016 and 2019 polling place lists (used only for venue matching)
  vec/2022/districts.json # scrape of all 87 VEC district result pages (FP by voting centre,
                          #   2CP by voting centre, full distribution of preferences)
  vec/2022/narracan_supplementary.json
  vec/2022/files/         # VEC indicative-distribution spreadsheets (38 districts) + TPP xlsx
  vec/2022/legislative_council/  # VEC Legislative Council .xls per region (votes received by
                          #   voting centre with ATL/BTL by candidate; the STV distribution)
  vec/2018/               # 2018 scrape (from the Internet Archive's copy of the old VEC results
                          #   site) + 2018 Legislative Council .xls files
  vec/osm_geocodes_raw.json  # raw OpenStreetMap lookups for VEC-only booth names
  boundaries/             # Vicmap WFS extracts and AEC shapefiles as downloaded
data/
  vic2018/, vic2022/, vic2023n/, fed2022/, fed2025/   # normalised CSVs, one set per election
  venues/                 # venue table, VEC booth -> venue matches, geocodes
  boundaries/             # simplified GeoJSON: vic_la_2013/2022, vic_lc_2013/2022, fed_2021/2024
  catchments/             # Voronoi booth catchments per election (+ H3 res-7 hex shares, review lists)
  bundle/                 # Parquet tables + GeoJSON + manifest.json (for DuckDB-style tooling)
site/                     # the Booth Atlas static site: app.html, index.html, build.py, data/ (see site/README.md)
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
| `elections` | election_id | `vic2018`, `vic2022`, `vic2023n` (Narracan supplementary), `fed2022`, `fed2025`, and the by-elections `vicby-warrandyte-2023`, `vicby-mulgrave-2023`, `vicby-prahran-2025`, `vicby-werribee-2025`, `vicby-nepean-2026` |
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
| `lc_contests` / `lc_candidates` / `lc_votes` / `lc_dop` | | Legislative Council: region totals and quota; groups + candidates (with an `ATL` pseudo-candidate per group); votes by voting centre x candidate/ATL (booth ids shared with the Assembly); the STV count (ballot papers, transfer value, progressive total per count, `elected` flags) |

Views: `booth_party_fp` (votes by canonical party per booth), `booth_party_share` (share of
formal vote), `venue_party_share` (the venue time series — party share at each physical venue
at each election).

## Reconciliation (`python3 -m src.verify data/<election>`)

* First preferences by voting centre sum exactly to the district formal vote, and informal to
  informal, for every district in 2018 and 2022 (one documented exception: Ripon 2018, where the
  only booth-level count the VEC published predates the recount by 24 votes).
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

## Re-running

```
python3 -m src.load_aec 27966 2022 raw/aec/2022 data/fed2022
python3 -m src.load_aec 31496 2025 raw/aec/2025 data/fed2025
python3 -m src.load_vec 2022 raw/vec/2022/districts.json data/vic2022
python3 -m src.load_vec 2018 raw/vec/2018/districts.json data/vic2018
python3 -m src.load_lc 2022 raw/vec/2022/legislative_council data/vic2022
python3 -m src.load_lc 2018 raw/vec/2018/legislative_council data/vic2018
# by-elections: raw/vec/by_<seat><year>.json -> data/vicby-<seat>-<year> (see src/load_vec.load)
python3 -m src.load_2026 raw/vec/2026/wikipedia_candidates_raw_2026-10-31.json data/vic2026 2026-10-31
python3 -m src.verify data/vic2022 && python3 -m src.verify data/vic2018
python3 -m src.match_venues data/vic2022/booths.csv,data/vic2018/booths.csv,data/vic2023n/booths.csv data/venues data/fed2022/booths.csv data/fed2025/booths.csv raw/aec/pp_history/booths_fed2016_2019.csv
python3 -m src.filter_geocodes raw/vec/osm_geocodes_raw.json data
python3 -m src.boundaries
python3 -m src.build_db data/elections.sqlite data
python3 -m src.catchments data/elections.sqlite
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
* AEC Tally Room downloads: https://results.aec.gov.au/27966/Website/HouseDownloadsMenu-27966-Csv.htm and .../31496/...
* Boundaries: Vicmap Admin state assembly/council polygons via the DataVic WFS (open-data-platform:state_assembly_2013/2022, state_council_2013/2022); AEC Victorian division shapefiles (July 2021, October 2024).
