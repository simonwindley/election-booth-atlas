#!/usr/bin/env python3
"""Fetch Bureau of Meteorology daily station data for Victoria (the weather question in analysis/questions.json).

Run from the project folder in your own Terminal (your Mac reaches the BOM; the Claude workspaces cannot):
    python3 tools/fetch_bom.py                 # rain and maximum temperature, all qualifying Victorian stations
    python3 tools/fetch_bom.py 136             # just rainfall
    python3 tools/fetch_bom.py --test          # one station of each, to check the BOM lets us in
Re-running skips stations already downloaded, so it can be stopped and restarted.

What it gets (Climate Data Online, daily, each station's whole record as one zip of CSV):
  136  daily rainfall (mm, 24 hours to 9 am)        - every Victorian rain station open at some point since 1998
  122  daily maximum temperature (deg C)            - every Victorian temperature station open since 1998
  123  daily minimum temperature (deg C)            - same stations as 122
Station lists (with latitude and longitude, used to give every booth its nearest station) come from the BOM's
'lists by element' pages and are saved alongside.

Files: raw/weather/bom/alphaVIC_<code>.txt, raw/weather/bom/<code>/<station>.zip, raw/weather/bom/failed.txt
The site expects a browser-like client and is rate-sensitive, so requests are spaced out (about an hour in all).
"""
import os, re, sys, time, random, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'raw', 'weather', 'bom')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Referer': 'http://www.bom.gov.au/climate/data/'}
SINCE = 1998
CODES = {'136': 'rainfall', '122': 'max temperature', '123': 'min temperature'}
LIST_CODE = {'136': '136', '122': '122', '123': '122'}


def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or k == tries - 1:
                raise
        except Exception:
            if k == tries - 1:
                raise
        time.sleep(5 * (k + 1))


def stations(code):
    path = os.path.join(OUT, f'alphaVIC_{code}.txt')
    if not os.path.exists(path):
        open(path, 'wb').write(get(f'http://www.bom.gov.au/climate/data/lists_by_element/alphaVIC_{code}.txt'))
    out = []
    for line in open(path, encoding='latin-1'):
        m = re.match(r'^\s*(\d{4,6})\s+(.+?)\s+(-\d+\.\d+)\s+(\d+\.\d+)\s+(\w{3}) (\d{4})\s+(\w{3})? ?(\d{4})?', line)
        if not m:
            continue
        stn, name, lat, lon, _, start, _, end = m.groups()
        end = int(end) if end else 9999
        if end >= SINCE:
            out.append((stn.zfill(6), name.strip(), float(lat), float(lon), int(start), end))
    return out


def p_c(stn, code):
    txt = get(f'http://www.bom.gov.au/jsp/ncc/cdio/wData/wdata?p_stn_num={stn}&p_display_type=availableYears&p_nccObsCode={code}').decode('latin-1')
    m = re.search(r'(-?\d{6,})', txt.split(':')[-1]) or re.search(r'(-\d{6,})', txt)
    return m.group(1) if m else None


def fetch_station(stn, code):
    dest = os.path.join(OUT, code, f'{stn}.zip')
    if os.path.exists(dest):
        return 'have'
    pc = p_c(stn, code)
    if not pc:
        return 'no data'
    time.sleep(0.8 + random.random())
    blob = get(f'http://www.bom.gov.au/jsp/ncc/cdio/weatherData/av?p_display_type=dailyZippedDataFile&p_stn_num={stn}&p_c={pc}&p_nccObsCode={code}&p_startYear=')
    if blob[:2] != b'PK':
        return 'not a zip'
    open(dest, 'wb').write(blob)
    return 'got'


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    test = '--test' in sys.argv
    codes = args or list(CODES)
    os.makedirs(OUT, exist_ok=True)
    tally, failed = {}, []
    for code in codes:
        os.makedirs(os.path.join(OUT, code), exist_ok=True)
        st = stations(LIST_CODE[code])
        if test:
            st = [s for s in st if s[0] == '086071'] or st[:1]       # Melbourne (Olympic Park) if listed
        print(f'{code} {CODES[code]}: {len(st)} stations open since {SINCE}', flush=True)
        for i, (stn, name, *_rest) in enumerate(st, 1):
            try:
                r = fetch_station(stn, code)
            except Exception as e:
                r = f'error {e}'
            tally[r if not r.startswith('error') else 'error'] = tally.get(r if not r.startswith('error') else 'error', 0) + 1
            if r not in ('got', 'have'):
                failed.append(f'{code}\t{stn}\t{name}\t{r}')
            if test or i % 25 == 0 or r.startswith('error'):
                print(f'  {i}/{len(st)} {stn} {name}: {r}', flush=True)
            if r == 'got':
                time.sleep(1.0 + random.random())
            if r.startswith('error 403'):
                print('  the BOM refused the request (403): stopping; try again later or tell Claude', flush=True)
                break
    open(os.path.join(OUT, 'failed.txt'), 'w').write('\n'.join(failed) + '\n')
    print('done:', tally, f'(failures listed in raw/weather/bom/failed.txt)')


if __name__ == '__main__':
    main()
