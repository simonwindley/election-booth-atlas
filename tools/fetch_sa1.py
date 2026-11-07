"""Fetch the Victorian SA1 boundaries for the 2021, 2016 and 2011 ASGS editions from the ABS ArcGIS services
(generalised layer, WGS84, 5-decimal coordinates), paging through the query API 2000 features at a time.

Needs internet access: run it on a machine that has it.
    python3 tools/fetch_sa1.py            # all three editions
    python3 tools/fetch_sa1.py 2021       # one edition
Writes raw/boundaries/abs/sa1_<year>_vic.geojson (properties: sa1, sa2 where the edition has it).
"""
import sys, os, json, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDITIONS = {
    '2021': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA1/MapServer/1', "state_code_2021='2'", {'sa1_code_2021': 'sa1', 'sa2_code_2021': 'sa2'}),
    '2016': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2016/SA1/MapServer/1', "state_code_2016='2'", {'sa1_maincode_2016': 'sa1', 'sa2_maincode_2016': 'sa2'}),
    '2011': ('https://geo.abs.gov.au/arcgis/rest/services/ASGS2011/SA1/MapServer/1', "state_code='2'", {'sa1_main': 'sa1'}),
}
PAGE = 2000


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'ElectionBoothAtlas/1.0 (SA1 boundaries)'}), timeout=180) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f'   retry after error: {e}')
            time.sleep(5 * (i + 1))


def fetch(year):
    base, where, fields = EDITIONS[year]
    q = {'where': where, 'returnCountOnly': 'true', 'f': 'json'}
    total = json.loads(get(base + '/query?' + urllib.parse.urlencode(q)))['count']
    print(f'{year}: {total} SA1s in Victoria')
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
        print(f'   {len(feats)}/{total}')
    out = os.path.join(ROOT, 'raw', 'boundaries', 'abs', f'sa1_{year}_vic.geojson')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fh:
        json.dump({'type': 'FeatureCollection', 'source': f'ABS ASGS {year} SA1, generalised layer via geo.abs.gov.au, retrieved {time.strftime("%Y-%m-%d")}', 'features': feats}, fh, separators=(',', ':'))
    print(f'   -> {out} ({os.path.getsize(out) // 1_000_000} MB)')


if __name__ == '__main__':
    for y in (sys.argv[1:] or ['2021', '2016', '2011']):
        fetch(y)
