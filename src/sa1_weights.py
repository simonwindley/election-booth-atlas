"""Apportion SA1s (2021, 2016 or 2011 edition) to the 2022 Victorian districts and to the election-day booth
catchments on those boundaries (catchment_vic2022 + catchment_vic2023n for Narracan), by area.

SA1s are small (a few hundred people, usually a few streets), so the share of an SA1's area that falls inside a
district or a booth catchment is a fair estimate of the share of its people who live there. Pieces under 0.5% of
the SA1 are dropped and the rest renormalised, so slivers from boundary mismatch do not scatter population.

Usage: python3 -m src.sa1_weights 2021            (also 2016, 2011)
Writes raw/abs/sa1_weights_<year>.json:
  {year, boundaries, sa1: {code: {"d": {contest_id: w}, "b": {booth_id: w}, "f24": {division: w} (2021 only)}}}
"""
import sys, json, gzip, os
from collections import defaultdict
from shapely.geometry import shape
from shapely.strtree import STRtree
from shapely.validation import make_valid
from shapely.ops import transform
from pyproj import Transformer
import warnings; warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TO_M = Transformer.from_crs('EPSG:4326', 'EPSG:3111', always_xy=True).transform


def load_fc(path):
    return json.load(gzip.open(path)) if path.endswith('.gz') else json.load(open(path))


def geom(f):
    g = shape(f['geometry'])
    if not g.is_valid:
        g = make_valid(g)
    return transform(TO_M, g)


def apportion(units, targets, min_share=0.005):
    """units: [(code, geom)]; targets: [(id, geom)] -> {code: {id: share}}"""
    tree = STRtree([g for _, g in targets])
    out = {}
    for code, g in units:
        if g.is_empty or g.area <= 0:
            continue
        w = {}
        for i in tree.query(g):
            tid, tg = targets[i]
            a = g.intersection(tg).area
            if a > 0:
                w[tid] = w.get(tid, 0) + a
        tot = sum(w.values())
        if tot <= 0:
            continue
        w = {k: v / tot for k, v in w.items() if v / tot >= min_share}
        t2 = sum(w.values())
        out[code] = {k: round(v / t2, 5) for k, v in w.items()}
    return out


def main(year):
    sa1 = [(f['properties']['sa1'], geom(f)) for f in load_fc(os.path.join(ROOT, f'raw/boundaries/abs/sa1_{year}_vic.geojson'))['features'] if f.get('geometry')]
    dist = [(f['properties']['contest_id'], geom(f)) for f in load_fc(os.path.join(ROOT, 'site/data/boundary_vic_la_2022.geojson.gz'))['features']]
    cat = []
    for e in ('vic2022', 'vic2023n'):
        for f in load_fc(os.path.join(ROOT, f'site/data/catchment_{e}.geojson.gz'))['features']:
            cat.append((f['properties']['booth_id'], geom(f)))
    # Narracan's 2022 catchments (if any) are superseded by the 2023 supplementary's
    narr = {b for b, _ in cat if b.startswith('vic-narracan-')}
    print(f'{year}: {len(sa1)} SA1s, {len(dist)} districts, {len(cat)} catchments')
    wd = apportion(sa1, dist)
    wb = apportion(sa1, cat)
    out = {code: {'d': wd.get(code, {}), 'b': wb.get(code, {})} for code in set(wd) | set(wb)}
    if year == '2021':
        # the Victorian federal divisions as redrawn in 2024 (used at the 2025 election): a census file of their own
        fed = [(f['properties']['contest_id'], geom(f)) for f in load_fc(os.path.join(ROOT, 'site/data/boundary_fed_2024.geojson.gz'))['features'] if f['properties'].get('contest_id')]
        wf = apportion(sa1, fed)
        for code, ws in wf.items():
            out.setdefault(code, {'d': {}, 'b': {}})['f24'] = ws
        print(f'   federal 2024 boundaries: {len(fed)} divisions, {len(wf)} SA1s')
    path = os.path.join(ROOT, f'raw/abs/sa1_weights_{year}.json')
    json.dump({'year': int(year), 'boundaries': 'vic_la_2022', 'method': 'area share of each SA1 inside each district / booth catchment (catchment_vic2022 + catchment_vic2023n)', 'sa1': out}, open(path, 'w'), separators=(',', ':'))
    split_d = sum(1 for v in out.values() if len(v['d']) > 1); split_b = sum(1 for v in out.values() if len(v['b']) > 1)
    print(f'   {len(out)} apportioned; split across districts: {split_d}; across catchments: {split_b} -> {path}')


if __name__ == '__main__':
    for y in sys.argv[1:] or ['2021', '2016', '2011']:
        main(y)
