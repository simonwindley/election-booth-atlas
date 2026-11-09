#!/usr/bin/env python3
"""Fetch AFL match results for the footy question in analysis/questions.json (does the footy move the vote?).

Run from the project folder in your own Terminal:
    python3 tools/fetch_afl.py            # every season 1998-2026
    python3 tools/fetch_afl.py --test     # one season, prints a few games
Source: the Squiggle API (api.squiggle.com.au), which asks scripts to identify themselves and to go easy; requests
are spaced a second apart. Every match with its round, date, teams, scores and venue; ladders at any date (e.g.
election week) and premierships are rebuilt from the results, so only the games are needed.
Files: raw/afl/teams.json, raw/afl/games_<year>.json. Re-running skips seasons already saved (except the current one).
"""
import os, sys, json, time, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'raw', 'afl')
UA = {'User-Agent': 'Election Booth Atlas research script (electionboothatlas.org)'}
API = 'https://api.squiggle.com.au/'


def get(q):
    with urllib.request.urlopen(urllib.request.Request(f'{API}?q={q}', headers=UA), timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    test = '--test' in sys.argv
    os.makedirs(OUT, exist_ok=True)
    this_year = datetime.date.today().year
    teams = get('teams')
    json.dump(teams, open(os.path.join(OUT, 'teams.json'), 'w'), indent=1)
    print(len(teams.get('teams', [])), 'teams')
    years = [2010] if test else range(1998, this_year + 1)
    for y in years:
        dest = os.path.join(OUT, f'games_{y}.json')
        if os.path.exists(dest) and y != this_year and not test:
            continue
        time.sleep(1.2)
        try:
            g = get(f'games;year={y}')
        except Exception as e:
            print(f'{y}: failed ({e})'); continue
        games = g.get('games', [])
        json.dump(g, open(dest, 'w'))
        done = [x for x in games if x.get('complete') == 100]
        gf = [x for x in done if str(x.get('roundname', '')).lower().startswith('grand final')]
        print(f'{y}: {len(games)} games, {len(done)} complete' + (f"; grand final {gf[-1].get('winner')}" if gf else ''), flush=True)
        if test:
            for x in games[:3]:
                print('   ', {k: x.get(k) for k in ('round', 'roundname', 'date', 'hteam', 'hscore', 'ateam', 'ascore', 'winner', 'venue')})
    print('done ->', OUT)


if __name__ == '__main__':
    main()
