#!/usr/bin/env python3
"""Fetch state election results where One Nation has stood, for the One Nation work and the national expansion.

Run from the project folder in your own Terminal (your Mac reaches these sites; the Claude workspaces cannot):
    python3 tools/fetch_states.py            # everything
    python3 tools/fetch_states.py qld sa     # just some states
Files land in raw/national/<state>/... ; re-running skips files already there.

  QLD  ECQ: 2024 and 2020 general elections and state by-elections as the ECQ XML archive (results by booth and the
       full distribution of preferences); 2017 and 2015 as the results website's district and booth pages (HTML,
       the booth pages include the distribution of preferences)
  WA   WAEC results API: 2025, 2021, 2017; per district, results (first preferences by polling place and the full
       distribution) and candidates (JSON)
  NSW  NSWEC past results: 2023 and 2019 Legislative Assembly; per district, first preferences and the distribution
       of preferences (HTML)
  SA   ECSA results API: 2026 and 2022 general elections and by-elections; static (districts, candidates, polling
       places) and final results (first preferences by polling place, two-candidate, full distribution) (JSON)
"""
import os, re, sys, json, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'raw', 'national')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh) election-booth-atlas research fetch', 'Accept': '*/*'}
stats = {'got': 0, 'have': 0, 'missing': 0}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def save(url, path, quiet_404=False):
    path = os.path.join(OUT, path)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        stats['have'] += 1; return open(path, 'rb').read()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(3):
        try:
            b = fetch(url)
            open(path, 'wb').write(b); stats['got'] += 1
            print(f'  got  {os.path.relpath(path, ROOT)} ({len(b):,} bytes)'); time.sleep(0.25); return b
        except urllib.error.HTTPError as e:
            if e.code == 404:
                if not quiet_404:
                    print(f'  404  {url}'); stats['missing'] += 1
                return None
            time.sleep(2)
        except Exception as e:
            time.sleep(2)
    print(f'  MISSING {url}'); stats['missing'] += 1
    return None


def qld():
    print('QLD')
    data = json.loads(fetch('https://resultsdata.elections.qld.gov.au/elections.json'))['elections']
    for e in data:
        name = e.get('electionName') or ''
        if re.search(r'state', name, re.I) and e.get('archiveXML'):
            u = e['archiveXML']
            save(u, f'qld/xml/{os.path.basename(u)}')
    json.dump(data, open(os.path.join(OUT, 'qld', 'elections.json'), 'w'), indent=1)
    for year in (2017, 2015):
        base = f'https://results.ecq.qld.gov.au/elections/state/State{year}/results/'
        save(base + 'summary.html', f'qld/html/{year}/summary.html')
        misses = 0
        for i in range(1, 120):
            a = save(base + f'district{i}.html', f'qld/html/{year}/district{i}.html', quiet_404=True)
            b = save(base + f'booth{i}.html', f'qld/html/{year}/booth{i}.html', quiet_404=True)
            misses = misses + 1 if a is None and b is None else 0
            if misses >= 3:
                break


def wa():
    print('WA')
    api = 'https://eis.waec.wa.gov.au/api/sgElections/'
    for e in ('sg2025', 'sg2021', 'sg2017'):
        top = save(api + e, f'wa/{e}/election.json')
        if not top:
            continue
        for el in json.loads(top).get('electorates', []):
            if (el.get('ElelctorateType') or el.get('ElectorateType')) != 'District':
                continue
            code = el['ElectorateCode']
            save(api + f'{e}/{code}/results', f'wa/{e}/{code}_results.json')
            save(api + f'{e}/{code}/candidates', f'wa/{e}/{code}_candidates.json')


def nsw():
    print('NSW')
    base = 'https://pastvtr.elections.nsw.gov.au'
    for e in ('SG2301', 'SG1901'):
        idx = save(f'{base}/{e}/LA/results', f'nsw/{e}/index.html')
        if not idx:
            continue
        slugs = sorted(set(re.findall(rf'/{e}/LA/([a-z0-9\-]+)/dop/dop', idx.decode('utf-8', 'replace'), re.I)))
        for s in slugs:
            save(f'{base}/{e}/LA/{s}/dop/dop', f'nsw/{e}/{s}_dop.html')
            save(f'{base}/{e}/LA/{s}/cc/fp_summary', f'nsw/{e}/{s}_fp.html')


def sa():
    print('SA')
    api = 'https://apim-ecsa-production.azure-api.net/results-display/'
    dates = save(api + 'ElectionDates', 'sa/election_dates.json')
    events = [(x['electionDate'], x['electionType']) for x in json.loads(dates)['elections']] if dates else [('2026-03-21', 'State General Election'), ('2022-03-19', 'State General Election')]
    for d, t in events:
        if not re.search(r'State', t):
            continue
        save(api + f'HAStatic/{d}', f'sa/{d}/HAStatic.json')
        save(api + f'HAChange/{d}/0', f'sa/{d}/HAChange.json')


if __name__ == '__main__':
    want = [a.lower() for a in sys.argv[1:]] or ['qld', 'wa', 'nsw', 'sa']
    for w in want:
        try:
            {'qld': qld, 'wa': wa, 'nsw': nsw, 'sa': sa}[w]()
        except Exception as ex:
            print(f'{w}: stopped with {ex!r}; run again to resume')
    print(f"done: {stats['got']} new, {stats['have']} already here, {stats['missing']} missing")
