#!/bin/bash
# Fetch the national AEC results files used for the One Nation work (preference flows, House v Senate, by-elections).
# Run from the project folder in your own Terminal (your Mac can reach the AEC; the Claude workspaces cannot):
#     tools/fetch_national.sh
# Files land in raw/national/aec/<event>/ . Re-running skips files already downloaded.
set -u
cd "$(dirname "$0")/.."
BASE=https://results.aec.gov.au
get() {   # get <event> <path under Website/> 
  local e=$1 p=$2 out="raw/national/aec/$1/$(basename "$2")"
  mkdir -p "raw/national/aec/$e"
  if [ -s "$out" ]; then echo "  have $out"; return; fi
  if curl -fsSL --retry 3 --retry-delay 2 -o "$out.part" "$BASE/$e/Website/$p"; then mv "$out.part" "$out"; echo "  got  $out ($(wc -c < "$out" | tr -d ' ') bytes)"
  else rm -f "$out.part"; echo "  MISSING $e/$p"; fi
}
# federal elections: 2025, 2022, 2019, 2016, and 2013, 2010, 2007, 2004 (the earliest the AEC's tally files go back;
# 1998 and 2001 state totals are in raw/national/tpp_by_state_1998_2001.json)
for e in 31496 27966 24310 20499 17496 15508 13745 12246; do
  echo "event $e"
  for f in HouseCandidatesDownload HouseFirstPrefsByCandidateByVoteTypeDownload HouseTcpByCandidateByPollingPlaceDownload \
           HouseTppByPollingPlaceDownload HouseDopByDivisionDownload HouseTcpFlowByDivisionDownload GeneralPollingPlacesDownload \
           HouseTppByDivisionDownload HouseNonClassicDivisionsDownload SenateFirstPrefsByDivisionByVoteTypeDownload \
           SenateCandidatesDownload SenateFirstPrefsByStateByGroupByVoteTypeDownload; do
    get $e "Downloads/$f-$e.csv"
  done
  for s in NSW VIC QLD WA SA TAS ACT NT; do get $e "Downloads/HouseStateFirstPrefsByPollingPlaceDownload-$e-$s.csv"; done
done
# federal by-elections since 2020 (event state): Farrer 2026, Cook 2024, Dunkley 2024, Fadden 2023, Aston 2023, Groom 2020, Eden-Monaro 2020
for es in 31633:NSW 29807:NSW 29778:VIC 29422:QLD 28791:VIC 25881:QLD 25820:NSW; do
  e=${es%:*}; s=${es#*:}; echo "by-election $e ($s)"
  get $e "Downloads/HouseCandidatesDownload-$e.csv"
  get $e "Downloads/HouseStateFirstPrefsByPollingPlaceDownload-$e-$s.csv"
  get $e "Downloads/HouseTcpByCandidateByPollingPlaceDownload-$e.csv"
  get $e "External/HouseDopByPPDownload-$e-$s.zip"
done
echo "done: $(find raw/national/aec -type f | wc -l | tr -d ' ') files, $(du -sh raw/national/aec | cut -f1)"
