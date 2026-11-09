#!/usr/bin/env python3
"""Fetch the census inputs for every state and territory (Victoria is already in place), so polling places across
Australia get census profiles built the Victorian way (national_census_booths in analysis/questions.json).

Run from the project folder in your own Terminal:
    python3 tools/fetch_census_national.py              # everything (about 1.3 GB of DataPacks + ~300 MB of boundaries)
    python3 tools/fetch_census_national.py datapacks    # just the DataPacks
    python3 tools/fetch_census_national.py sa1 QLD WA   # just SA1 boundaries for some states
Re-running skips files already downloaded, so it can be stopped and restarted.

  datapacks  ABS Census DataPacks at SA1 level, per state: 2021 and 2016 General Community Profile, 2011 Basic
             Community Profile (short headers) -> raw/abs/datapacks/<year>_<GCP|BCP>_SA1_for_<STATE>_short-header.zip
  sa1        ABS SA1 boundaries (2021, 2016, 2011 editions, generalised layer, WGS84) from the ABS ArcGIS services,
             per state -> raw/boundaries/abs/sa1_<year>_<state>.geojson (the Victorian files keep their names)
"""
import sys, os, json, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATES = {'NSW': '1', 'QLD': '3', 'SA': '4', 'WA': '5', 'TAS': '6', 'NT': '7', 'ACT': '8'}
PACKS = {'2021': 'GCP', '2016': 'GCP', '2011': 'BCP'}
EDITIONS = {
    '2021': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA1/MapServer/1', "state_code_2021='{c}'", {'sa1_code_2021': 'sa1', 'sa2_code_2021': 'sa2'}),
    '2016': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2016/SA1/MapServer/1', "state_code_2016='{c}'", {'sa1_maincode_2016': 'sa1', 'sa2_maincode_2016': 'sa2'}),
    '2011': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2011/SA1/MapServer/1', "state_code='{c}'", {'sa1_main': 'sa1'}),
}
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh) ElectionBoothAtlas/1.0 (census DataPacks and SA1 boundaries)'}
PAGE = 2000


def get(url, tries=4, timeout=600):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f'   retry after error: {e}', flush=True)
            time.sleep(5 * (i + 1))


def datapacks(states):
    d = os.path.join(ROOT, 'raw', 'abs', 'datapacks'); os.makedirs(d, exist_ok=True)
    for year, prof in PACKS.items():
        for st in states:
            name = f'{year}_{prof}_SA1_for_{st}_short-header.zip'
            p = os.path.join(d, name)
            if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
                print(f'  have {name}'); continue
            print(f'  {name} ...', flush=True)
            blob = get(f'https://www.abs.gov.au/census/find-census-data/datapacks/download/{name}')
            if blob[:2] != b'PK':
                print(f'   not a zip ({blob[:120]!r}); skipped'); continue
            open(p, 'wb').write(blob)
            print(f'   {len(blob) // 1_000_000} MB', flush=True)


def sa1(states):
    for year, (base, where_t, fields) in EDITIONS.items():
        for st in states:
            out = os.path.join(ROOT, 'raw', 'boundaries', 'abs', f'sa1_{year}_{st.lower()}.geojson')
            if os.path.exists(out):
                print(f'  have {os.path.basename(out)}'); continue
            where = where_t.format(c=STATES[st])
            total = json.loads(get(base + '/query?' + urllib.parse.urlencode({'where': where, 'returnCountOnly': 'true', 'f': 'json'})))['count']
            print(f'  {year} {st}: {total} SA1s', flush=True)
            feats = []
            for off in range(0, total, PAGE):
                q = {'where': where, 'outFields': ','.join(fields), 'outSR': 4326, 'geometryPrecision': 5, 'resultOffset': off, 'resultRecordCount': PAGE, 'f': 'geojson'}
                fc = json.loads(get(base + '/query?' + urllib.parse.urlencode(q)))
                if 'features' not in fc:
                    raise SystemExit(f'unexpected reply at offset {off}: {str(fc)[:300]}')
                for f in fc['features']:
                    p = f.get('properties') or {}
                    f['properties'] = {v: str(p.get(k)) for k, v in fields.items()}
                    feats.append(f)
                print(f'   {len(feats)}/{total}', flush=True)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'w') as fh:
                json.dump({'type': 'FeatureCollection', 'source': f'ABS ASGS {year} SA1, generalised layer via geo.abs.gov.au, retrieved {time.strftime("%Y-%m-%d")}', 'features': feats}, fh, separators=(',', ':'))
            print(f'   -> {os.path.basename(out)} ({os.path.getsize(out) // 1_000_000} MB)', flush=True)


def main():
    args = sys.argv[1:]
    what = [a for a in args if a in ('datapacks', 'sa1')] or ['datapacks', 'sa1']
    states = [a.upper() for a in args if a.upper() in STATES] or list(STATES)
    if 'sa1' in what:
        print('SA1 boundaries'); sa1(states)
    if 'datapacks' in what:
        print('DataPacks'); datapacks(states)
    print('done')


if __name__ == '__main__':
    main()
