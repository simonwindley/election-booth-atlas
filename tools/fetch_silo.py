#!/usr/bin/env python3
"""Fetch daily weather for every Victorian Bureau of Meteorology station from SILO (Queensland Government's archive of
BOM station data, with gaps filled by interpolation), for the weather question in analysis/questions.json.
The BOM's own Climate Data Online refuses scripted downloads (403); SILO's API is meant for exactly this.

Run from the project folder in your own Terminal:
    python3 tools/fetch_silo.py --test          # one station (Melbourne), prints the first rows
    python3 tools/fetch_silo.py                 # every Victorian rain station open since 1998
SILO asks for an email address as the API username (password 'apirequest' is the documented constant). The script
asks for it, or reads SILO_EMAIL from the environment; it is not saved anywhere.

Per station, 1 Jan 1998 - today: daily rainfall, maximum and minimum temperature, each with SILO's source code
(observed or interpolated). Station list: raw/weather/bom/alphaVIC_136.txt (the BOM list, fetched if missing).
Files: raw/weather/silo/<station>.csv, raw/weather/silo/failed.txt. Re-running skips stations already there.
"""
import os, re, sys, time, datetime, getpass, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'raw', 'weather', 'silo')
LIST = os.path.join(ROOT, 'raw', 'weather', 'bom', 'alphaVIC_136.txt')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh) election-booth-atlas research fetch'}
API = 'https://www.longpaddock.qld.gov.au/cgi-bin/silo/PatchedPointDataset.php'
SINCE = 1998


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def stations():
    if not os.path.exists(LIST):
        os.makedirs(os.path.dirname(LIST), exist_ok=True)
        open(LIST, 'wb').write(get('http://www.bom.gov.au/climate/data/lists_by_element/alphaVIC_136.txt'))
    out = []
    for line in open(LIST, encoding='latin-1'):
        m = re.match(r'^\s*(\d{4,6})\s+(.+?)\s+(-\d+\.\d+)\s+(\d+\.\d+)\s+(\w{3}) (\d{4})\s+(\w{3})? ?(\d{4})?', line)
        if m and (int(m.group(8)) if m.group(8) else 9999) >= SINCE:
            out.append((m.group(1).zfill(6), m.group(2).strip()))
    return out


def main():
    test = '--test' in sys.argv
    email = os.environ.get('SILO_EMAIL') or input('Email address for the SILO API username: ').strip()
    os.makedirs(OUT, exist_ok=True)
    st = stations()
    if test:
        st = [s for s in st if s[0] == '086071'] or st[:1]
    print(f'{len(st)} Victorian rain stations open since {SINCE}', flush=True)
    finish = datetime.date.today().strftime('%Y%m%d')
    tally, failed = {}, []
    for i, (stn, name) in enumerate(st, 1):
        dest = os.path.join(OUT, f'{stn}.csv')
        if os.path.exists(dest):
            tally['have'] = tally.get('have', 0) + 1
            continue
        q = urllib.parse.urlencode({'start': f'{SINCE}0101', 'finish': finish, 'station': stn, 'format': 'csv', 'comment': 'RXN',
                                    'username': email, 'password': 'apirequest'})
        try:
            txt = get(f'{API}?{q}').decode('latin-1')
            ok = txt.lstrip().lower().startswith('station') and txt.count('\n') > 100
            r = 'got' if ok else 'unexpected reply'
            if ok:
                open(dest, 'w').write(txt)
            elif test or i <= 3:
                print('   reply began:', txt[:300].replace('\n', ' | '))
        except Exception as e:
            r = f'error {e}'
        tally[r.split(':')[0]] = tally.get(r.split(':')[0], 0) + 1
        if r != 'got':
            failed.append(f'{stn}\t{name}\t{r}')
        if test:
            print(f'{stn} {name}: {r}')
            if r == 'got':
                print(''.join(open(dest).readlines()[:4]))
        elif i % 25 == 0 or r != 'got':
            print(f'  {i}/{len(st)} {stn} {name}: {r}', flush=True)
        if 'error HTTP Error 403' in r or 'error HTTP Error 401' in r:
            print('  SILO refused the request: stopping; paste this to Claude'); break
        time.sleep(0.6)
    open(os.path.join(OUT, 'failed.txt'), 'w').write('\n'.join(failed) + '\n')
    print('done:', tally)


if __name__ == '__main__':
    main()
