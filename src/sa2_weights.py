"""Apportion 2021 SA2s to electorates on a given boundary set, for aggregating SA2-level census counts.

Each SA2 is split by the electorate boundaries; each piece is weighted by an estimate of the people living in it.
The population proxy is election-day votes: every booth catchment (site/data/catchment_<election>.geojson.gz,
the area nearest each booth within its district) carries the formal votes cast at that booth, and votes are spread
evenly over the catchment's area. A piece's weight is then the votes falling inside it; where an SA2 has no
catchment votes at all (water, parkland, unpopulated), its area share is used instead.

Usage: python3 -m src.sa2_weights vic_la_2022 vic2022 raw/abs/sa2_to_vic_la_2022.json
Writes {sa2_code: {contest_id: weight}} with each SA2's weights summing to 1.
"""
import sys, json, gzip
from collections import defaultdict
from shapely.geometry import shape
from shapely.strtree import STRtree
from shapely.validation import make_valid
from pyproj import Transformer
from shapely.ops import transform
import warnings; warnings.filterwarnings('ignore', category=DeprecationWarning)

TO_M = Transformer.from_crs('EPSG:4326', 'EPSG:3111', always_xy=True).transform   # VicGrid, metres


def load_fc(path):
    return json.load(gzip.open(path)) if path.endswith('.gz') else json.load(open(path))


def geom(f):
    g = shape(f['geometry'])
    if not g.is_valid:
        g = make_valid(g)
    return transform(TO_M, g)


def booth_votes(eids):
    j = json.load(gzip.open('site/data/shares.json.gz'))
    rows = [dict(zip(j['cols'], r)) for r in j['rows']] if 'cols' in j else j
    v = defaultdict(int)
    for r in rows:
        if r['election_id'] in eids:
            v[r['booth_id']] += r['votes']
    return v


def main(bset, eid, out):
    sa2 = [(f['properties']['sa2_code_2021'], f['properties']['sa2_name_2021'], geom(f)) for f in load_fc('raw/boundaries/abs/sa2_2021_vic.geojson')['features'] if f['geometry']]
    dist = [(f['properties']['contest_id'], geom(f)) for f in load_fc(f'site/data/boundary_{bset}.geojson.gz')['features']]
    eids = eid.split(',')   # e.g. vic2022,vic2023n: Narracan's 2022 poll was the January 2023 supplementary
    votes = booth_votes(eids)
    cat = []
    for e in eids:
        for f in load_fc(f'site/data/catchment_{e}.geojson.gz')['features']:
            p = f['properties']; g = geom(f); n = votes.get(p['booth_id'], 0)
            if n and g.area > 0:
                cat.append((p['contest_id'], g, n / g.area))
    dtree = STRtree([g for _, g in dist]); ctree = STRtree([g for _, g, _ in cat])
    weights, stats = {}, {'sa2': 0, 'split': 0, 'area_fallback': 0}
    for code, name, g in sa2:
        stats['sa2'] += 1
        pieces = {}
        for i in dtree.query(g):
            cid, dg = dist[i]
            inter = g.intersection(dg)
            if inter.area > 1:
                pieces[cid] = inter
        if not pieces:
            continue
        w = defaultdict(float)
        for i in ctree.query(g):
            ccid, cg, dens = cat[i]
            if ccid not in pieces:
                continue
            a = pieces[ccid].intersection(cg).area
            if a > 0:
                w[ccid] += a * dens
        if sum(w.values()) <= 0:
            stats['area_fallback'] += 1
            w = {cid: p.area for cid, p in pieces.items()}
        # a piece in a district with no catchment votes recorded at all keeps an area-based share rather than vanishing
        covered = {c for c, _, _ in cat}
        for cid, p in pieces.items():
            if cid not in covered and cid not in w:
                w[cid] = p.area * (sum(w.values()) / max(1.0, sum(pp.area for c2, pp in pieces.items() if c2 in w)))
        tot = sum(w.values())
        ww = {cid: x / tot for cid, x in w.items() if x / tot >= 0.001}
        t2 = sum(ww.values()); ww = {cid: round(x / t2, 5) for cid, x in ww.items()}
        if len(ww) > 1:
            stats['split'] += 1
        weights[code] = ww
    json.dump({'boundaries': bset, 'population_proxy': f'{eid} election-day votes by booth catchment', 'weights': weights}, open(out, 'w'), indent=0)
    print(f'{bset}: {stats["sa2"]} SA2s, {len(weights)} apportioned, {stats["split"]} split across electorates, {stats["area_fallback"]} by area ->', out)


if __name__ == '__main__':
    main(*sys.argv[1:4])
