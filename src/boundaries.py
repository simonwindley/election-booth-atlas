"""Normalise electoral boundary layers into one GeoJSON per boundary set, simplified for the web.

Outputs data/boundaries/<set>.geojson with properties: set, contest_id, name, house.
  vic_la_2013 / vic_la_2022   Legislative Assembly districts (Vicmap, via WFS)
  vic_lc_2013 / vic_lc_2022   Legislative Council regions
  fed_2021 / fed_2024         federal divisions in Victoria (AEC shapefiles)

Usage: python3 -m src.boundaries
"""
import os, json, re
import shapefile
from shapely.geometry import shape, mapping
from shapely.validation import make_valid
from .load_vec import slug

RAW = 'raw/boundaries'
OUT = 'data/boundaries'
TOL = 0.0003  # degrees, ~30 m


def simplify(geom):
    g = make_valid(shape(geom))
    g = g.simplify(TOL, preserve_topology=True)
    return json.loads(json.dumps(mapping(g)), parse_float=lambda x: round(float(x), 5))


def write(name, feats):
    os.makedirs(OUT, exist_ok=True)
    fc = {'type': 'FeatureCollection', 'features': feats}
    with open(f'{OUT}/{name}.geojson', 'w') as f:
        json.dump(fc, f, separators=(',', ':'))
    print(name, len(feats), 'features', os.path.getsize(f'{OUT}/{name}.geojson') // 1024, 'KB')


def vicmap(layer, out, house):
    j = json.load(open(f'{RAW}/{layer}.geojson'))
    feats = []
    for f in j['features']:
        p = f['properties']
        if house == 'LA':
            nm = p['district_label'].replace(' District', '').title().replace("'S", "'s")
            cid = f'vic-{slug(nm)}'
        else:
            nm = p['region_label'].replace(' Region', '')
            cid = f'vicr-{slug(nm)}'
        feats.append({'type': 'Feature', 'properties': {'set': out, 'contest_id': cid, 'name': nm, 'house': house},
                      'geometry': simplify(f['geometry'])})
    write(out, feats)


def aec(shp, out, div_ids, src_crs=None):
    r = shapefile.Reader(shp)
    fields = [f[0] for f in r.fields[1:]]
    feats = []
    tf = None
    if src_crs:   # e.g. the 2010 file is in VicGrid94 (EPSG:3111); everything else is already lat/lon
        from pyproj import Transformer
        tf = Transformer.from_crs(src_crs, 'EPSG:4326', always_xy=True)
    def reproject(geom):
        def walk(c):
            if isinstance(c[0], (int, float)):
                x, y = tf.transform(c[0], c[1]); return [x, y]
            return [walk(x) for x in c]
        return {'type': geom['type'], 'coordinates': walk(geom['coordinates'])}
    for sr in r.shapeRecords():
        rec = dict(zip(fields, sr.record))
        nm = rec.get('Elect_div') or rec.get('ELECT_DIV') or rec.get('DIVNAME')
        cid = div_ids.get(nm.upper())
        g = sr.shape.__geo_interface__
        if tf:
            g = reproject({'type': g['type'], 'coordinates': [list(map(list, ring)) for ring in g['coordinates']] if g['type'] == 'Polygon' else [[list(map(list, ring)) for ring in poly] for poly in g['coordinates']]})
        feats.append({'type': 'Feature', 'properties': {'set': out, 'contest_id': cid, 'name': nm, 'house': 'HoR'},
                      'geometry': simplify(g)})
    missing = [f['properties']['name'] for f in feats if not f['properties']['contest_id']]
    if missing:
        print('  divisions without a contest id:', missing)
    write(out, feats)


def mif(path_mif, path_mid, out, div_ids, name_col=1):
    """MapInfo interchange (MIF/MID) regions in lat/lon -> one feature per record. Only Region objects are handled."""
    import csv
    names = [row[name_col].strip() for row in csv.reader(open(path_mid, encoding='latin-1'))]
    lines = open(path_mif, encoding='latin-1').read().split('\n')
    i = next(k for k, l in enumerate(lines) if l.strip() == 'Data') + 1
    feats, n = [], 0
    while i < len(lines):
        l = lines[i].strip()
        if l.lower().startswith('region'):
            nrings = int(l.split()[1]); i += 1; rings = []
            for _ in range(nrings):
                npts = int(lines[i].strip()); i += 1
                ring = [[float(x) for x in lines[i + k].split()] for k in range(npts)]; i += npts
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                rings.append(ring)
            # the largest ring is the outer boundary; others may be islands (separate polygons) or holes - let shapely sort it out
            polys = [{'type': 'Polygon', 'coordinates': [r]} for r in rings]
            from shapely.ops import unary_union
            g = unary_union([make_valid(shape(pg)) for pg in polys])
            nm = names[n]; n += 1
            feats.append({'type': 'Feature', 'properties': {'set': out, 'contest_id': div_ids.get(nm.upper()), 'name': nm, 'house': 'HoR'},
                          'geometry': simplify(mapping(g))})
        else:
            i += 1
    missing = [f['properties']['name'] for f in feats if not f['properties']['contest_id']]
    if missing:
        print('  divisions without a contest id:', missing)
    write(out, feats)


if __name__ == '__main__':
    import pandas as pd
    vicmap('state_assembly_2022', 'vic_la_2022', 'LA')
    vicmap('state_assembly_2013', 'vic_la_2013', 'LA')
    vicmap('state_council_2022', 'vic_lc_2022', 'LC')
    vicmap('state_council_2013', 'vic_lc_2013', 'LC')
    ids22 = {r.contest_name.upper(): r.contest_id for r in pd.read_csv('data/fed2022/contests.csv').itertuples()}
    ids25 = {r.contest_name.upper(): r.contest_id for r in pd.read_csv('data/fed2025/contests.csv').itertuples()}
    aec(f'{RAW}/aec/vic-july-2021-esri/E_VIC21_region.shp', 'fed_2021', ids22)
    aec(f'{RAW}/aec/Vic-october-2024-esri/Vic-october-2024-esri/E_VIC24_region.shp', 'fed_2024', ids25)
    ids19 = {r.contest_name.upper(): r.contest_id for r in pd.read_csv('data/fed2019/contests.csv').itertuples()}
    aec(f'{RAW}/aec/vic-july-2018-esri/E_AUGFN3_region.shp', 'fed_2018', ids19)
    ids10 = {}
    for y in ('2010', '2013', '2016'):
        ids10.update({r.contest_name.upper(): r.contest_id for r in pd.read_csv(f'data/fed{y}/contests.csv').itertuples()})
    aec(f'{RAW}/aec/vic-esri-24122010/vic 24122010.shp', 'fed_2010', ids10, src_crs='EPSG:3111')   # determined Dec 2010: used at the 2013 and 2016 elections
    mif(f'{RAW}/aec/vic-20100201/VIC_ELB.MIF', f'{RAW}/aec/vic-20100201/VIC_ELB.MID', 'fed_2003', ids10)   # as at Feb 2010: used at the 2010 election
    # sanity: every LA contest in the results has a polygon
    la = set(pd.read_csv('data/vic2022/contests.csv').contest_id)
    poly = {f['properties']['contest_id'] for f in json.load(open(f'{OUT}/vic_la_2022.geojson'))['features']}
    print('LA 2022 contests without polygon:', sorted(la - poly), '| polygons without contest:', sorted(poly - la))
