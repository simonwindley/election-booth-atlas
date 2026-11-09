"""Census profiles for every federal election-day polling place in Australia (2016, 2019, 2022, 2025), state by
state: the national version of src.sa1_weights + src.load_sa1_census.

For each federal election and state:
  * catchments: a Voronoi cell around every ordinary polling place open at that election (places sharing a
    location share a cell). The cells cover the whole state, so every SA1 lands somewhere. They are not clipped to
    divisions (we do not hold national division boundaries for every redistribution); voters mostly use the nearest
    booth whatever the division, so this is the better guess of who lives around a booth anyway.
  * weights: the share of each SA1's area inside each cell (pieces under 0.5% dropped, as in src.sa1_weights).
  * indicators: the same SPEC as src.load_sa1_census (numerators and denominators summed over SA1s, medians as
    population-weighted means), for each census (2011, 2016, 2021) so later work can interpolate between them.
Geometry is done in a local equirectangular projection (km), so pyproj is not needed.

Inputs  data/national/fed_booths_geo.csv                         election_id, booth_id, state, contest_id, lat, lon
        raw/boundaries/abs/sa1_<year>_<st>.geojson               (tools/fetch_census_national.py)
        raw/abs/datapacks/<year>_<GCP|BCP>_SA1_for_<ST>_short-header.zip
Outputs data/national/census_booths/<year>_<st>.json.gz          {census, state, indicators, cols, state_totals,
                                                                  booths: {election_id: {booth_id: [values]}}, check}
Usage   python3 -m src.national_census_booths [states ...] [--years 2021 2016 2011]   (default: every state found)
"""
import sys, os, io, re, csv, json, gzip, math, time, zipfile
from collections import defaultdict
import numpy as np
import shapely
from shapely.geometry import shape, MultiPoint, Point
from shapely.strtree import STRtree
from shapely.validation import make_valid
from shapely.ops import transform
import warnings; warnings.filterwarnings('ignore')

from src.load_sa1_census import SPEC, TAB, YEARS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATES = ('NSW', 'VIC', 'QLD', 'SA', 'WA', 'TAS', 'NT', 'ACT')
PACK = {'2021': 'GCP', '2016': 'GCP', '2011': 'BCP'}
MIN_SHARE = 0.005


# ---------- census tables, read straight from the DataPack zip ----------
def headers(year, st):
    path = os.path.join(ROOT, 'raw/abs/datapacks', f'{year}_{PACK[year]}_SA1_for_{st}_short-header.zip')
    if not os.path.exists(path):
        return None, None
    z = zipfile.ZipFile(path); hdr = {}
    for m in z.namelist():
        b = os.path.basename(m)
        if not b.lower().endswith('.csv') or '_SA1' not in b:
            continue
        mt = re.search(r'_([GB]\d+[A-Z]?)_', b)
        if not mt:
            continue
        with z.open(m) as fh:
            hdr[mt.group(1)] = (m, fh.readline().decode('utf-8-sig').strip().split(','))
    return z, hdr


def resolve(year, hdr, expr):
    fam, rx = expr.split(':', 1)
    neg = rx.startswith('-'); rx = rx[1:] if neg else rx
    code = TAB[fam][YEARS.index(year)]
    out = []
    for t, (f, cols) in hdr.items():
        if re.fullmatch(code + '[A-Z]?', t):
            out += [(f, c, neg) for c in cols[1:] if re.fullmatch(rx, c)]
    return out


def sa1_matrix(year, st):
    """-> (plan, sa1 codes as in the DataPack, N, D): per-SA1 numerators and denominators for every indicator"""
    z, hdr = headers(year, st)
    if z is None:
        return None
    yi = YEARS.index(year)
    plan, need = [], defaultdict(set)
    for id_, group, label, kind, nums, den in SPEC:
        nexprs = [(n[yi] if isinstance(n, tuple) else n) for n in nums]
        dexpr = den[yi] if isinstance(den, tuple) else den
        if any(n is None for n in nexprs) or (dexpr is None and kind != 'count'):
            continue
        ncols = [c for n in nexprs for c in resolve(year, hdr, n)]
        dcols = resolve(year, hdr, dexpr) if dexpr else []
        if not ncols or (dexpr and not dcols):
            continue
        plan.append((id_, group, label, kind, ncols, dcols))
        for f, c, _ in ncols + dcols:
            need[f].add(c)
    data, codes = {}, set()
    for f, cols in need.items():
        with z.open(f) as raw:
            rd = csv.reader(io.TextIOWrapper(raw, encoding='utf-8-sig'))
            head = next(rd); idx = {c: head.index(c) for c in cols}
            store = {c: {} for c in cols}
            for row in rd:
                code = row[0]; codes.add(code)
                for c, i in idx.items():
                    try:
                        store[c][code] = float(row[i])
                    except ValueError:
                        pass
        for c in cols:
            data[(f, c)] = store[c]
    sa1s = sorted(codes); si = {s: i for i, s in enumerate(sa1s)}
    N, D = np.zeros((len(sa1s), len(plan))), np.zeros((len(sa1s), len(plan)))
    for j, (id_, group, label, kind, ncols, dcols) in enumerate(plan):
        if kind in ('years', 'dollars', 'ratio'):
            base = np.zeros(len(sa1s))
            for f, c, neg in dcols:
                for s, v in data[(f, c)].items():
                    base[si[s]] += v
            med = np.zeros(len(sa1s)); has = np.zeros(len(sa1s), bool)
            for f, c, neg in ncols:
                for s, v in data[(f, c)].items():
                    if v > 0:
                        med[si[s]] = v; has[si[s]] = True
            N[:, j] = np.where(has, med * base, 0); D[:, j] = np.where(has, base, 0)
        else:
            for f, c, neg in ncols:
                for s, v in data[(f, c)].items():
                    N[si[s], j] += -v if neg else v
            for f, c, neg in dcols:
                for s, v in data[(f, c)].items():
                    D[si[s], j] += v
    return plan, sa1s, N, D


# ---------- geometry ----------
class Proj:
    def __init__(self, lat0):
        self.kx = 111.32 * math.cos(math.radians(lat0)); self.ky = 110.57

    def fwd(self, x, y, z=None):
        return np.asarray(x) * self.kx, np.asarray(y) * self.ky


def sa1_polygons(year, st, proj):
    path = os.path.join(ROOT, 'raw/boundaries/abs', f'sa1_{year}_{st.lower()}.geojson')
    if not os.path.exists(path):
        return None
    fc = json.load(open(path))
    codes, geoms = [], []
    for f in fc['features']:
        if not f.get('geometry'):
            continue
        g = shape(f['geometry'])
        if not g.is_valid:
            g = make_valid(g)
        g = transform(proj.fwd, g)
        if g.is_empty or g.area <= 0:
            continue
        codes.append(f['properties']['sa1']); geoms.append(g)
    return codes, np.array(geoms, dtype=object)


def catchments(points, envelope):
    """points: [(x, y)] unique locations -> array of Voronoi cells in the same order"""
    if len(points) == 1:
        return np.array([envelope], dtype=object)
    vd = shapely.voronoi_polygons(MultiPoint(points), extend_to=envelope, ordered=True)
    cells = np.array(list(vd.geoms), dtype=object)
    return shapely.intersection(cells, envelope)


def apportion(sa1_geoms, cells):
    """-> list of (sa1 index, cell index, share) with slivers under MIN_SHARE dropped and shares renormalised"""
    tree = STRtree(cells)
    a_idx, c_idx = tree.query(sa1_geoms, predicate='intersects')
    areas = shapely.area(shapely.intersection(sa1_geoms[a_idx], cells[c_idx]))
    tot = np.bincount(a_idx, weights=areas, minlength=len(sa1_geoms))
    share = areas / np.where(tot[a_idx] > 0, tot[a_idx], 1)
    keep = share >= MIN_SHARE
    a_idx, c_idx, share = a_idx[keep], c_idx[keep], share[keep]
    t2 = np.bincount(a_idx, weights=share, minlength=len(sa1_geoms))
    share = share / np.where(t2[a_idx] > 0, t2[a_idx], 1)
    return a_idx, c_idx, share


def finish(plan, n, d):
    out = []
    for j, (id_, group, label, kind, _, _) in enumerate(plan):
        if kind == 'count':
            out.append(int(round(float(n[j]))))
        elif d[j] > 0:
            out.append(round(float(n[j] / d[j]), 5 if kind == 'share' else 2))
        else:
            out.append(None)
    return out


def load_booths():
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'data/national/fed_booths_geo.csv'))))
    for r in rows:
        r['lat'] = float(r['lat']); r['lon'] = float(r['lon'])
    return rows


def run(st, years, booths):
    B = [r for r in booths if r['state'] == st]
    if not B:
        print(f'{st}: no booths'); return
    lat0 = float(np.median([r['lat'] for r in B]))
    proj = Proj(lat0)
    os.makedirs(os.path.join(ROOT, 'data/national/census_booths'), exist_ok=True)
    for year in years:
        t0 = time.time()
        geo = sa1_polygons(year, st, proj)
        mat = sa1_matrix(year, st)
        if geo is None or mat is None:
            print(f'{st} {year}: missing {"boundaries" if geo is None else "DataPack"}, skipped'); continue
        codes, geoms = geo
        plan, sa1s, N, D = mat
        # 2016 and 2011 DataPacks key SA1s by the 7-digit code (state + last four of the SA2 + SA1)
        if sa1s and all(len(s) == 7 for s in sa1s[:50]):
            codes = [c if len(c) == 7 else c[0] + c[5:9] + c[9:11] for c in codes]
        row_of = {s: i for i, s in enumerate(sa1s)}
        has = np.array([c in row_of for c in codes])
        geoms = geoms[has]; rows = np.array([row_of[c] for c, h in zip(codes, has) if h], dtype=int)
        envelope = shapely.union_all(shapely.envelope(geoms)).envelope.buffer(50)
        tree_sa1 = STRtree(geoms)
        res, check = {}, {}
        for e in sorted({r['election_id'] for r in B}):
            Be = [r for r in B if r['election_id'] == e]
            # drop places whose coordinates sit more than 25 km from any SA1 of the state (bad geocodes)
            pts = [Point(*proj.fwd(r['lon'], r['lat'])) for r in Be]
            idx, dist = tree_sa1.query_nearest(pts, return_distance=True, all_matches=False)   # one match per place, in order
            ok = [i for i in range(len(Be)) if dist[i] <= 25]
            locs, loc_of = {}, {}
            for i in ok:
                p = pts[i]; k = (round(p.x, 2), round(p.y, 2))   # ~10 m
                locs.setdefault(k, len(locs)); loc_of[Be[i]['booth_id']] = locs[k]
            cells = catchments(list(locs), envelope)
            a, c, w = apportion(geoms, cells)
            nloc = len(locs)
            accN = np.zeros((nloc, len(plan))); accD = np.zeros((nloc, len(plan)))
            np.add.at(accN, c, N[rows[a]] * w[:, None]); np.add.at(accD, c, D[rows[a]] * w[:, None])
            prof = [finish(plan, accN[k], accD[k]) for k in range(nloc)]
            res[e] = {b: prof[k] for b, k in loc_of.items()}
            pj = [p[0] for p in plan].index('population')
            check[e] = {'booths': len(Be), 'placed': len(loc_of), 'dropped_far': len(Be) - len(ok), 'locations': nloc,
                        'population_in_catchments': int(round(accN[:, pj].sum())), 'sa1_assigned': int(len(np.unique(a)))}
        tN, tD = N[rows].sum(axis=0), D[rows].sum(axis=0)
        tot = finish(plan, N.sum(axis=0), D.sum(axis=0))
        obj = {'census': int(year), 'state': st,
               'source': f'ABS Census {year} SA1 DataPack ({"General" if year != "2011" else "Basic"} Community Profile), apportioned by area onto Voronoi catchments of the ordinary polling places at each federal election',
               'indicators': [{'id': p[0], 'group': p[1], 'label': p[2], 'kind': p[3]} for p in plan], 'cols': [p[0] for p in plan],
               'state_totals': dict(zip([p[0] for p in plan], tot)), 'sa1': {'datapack': len(sa1s), 'with_boundary': int(has.sum()), 'boundaries': len(has)},
               'check': check, 'booths': res}
        out = os.path.join(ROOT, 'data/national/census_booths', f'{year}_{st.lower()}.json.gz')
        with gzip.open(out, 'wt') as fh:
            json.dump(obj, fh, separators=(',', ':'), allow_nan=False)
        pj = [p[0] for p in plan].index('population')
        print(f'{st} {year}: {len(plan)} indicators; SA1s {has.sum()}/{len(has)} with data; DataPack pop {tot[pj]:,} (with boundary {int(round(tN[pj])):,}); '
              + '; '.join(f"{e} {v['placed']}/{v['booths']} pop {v['population_in_catchments']:,}" for e, v in check.items()) + f'  [{time.time() - t0:.0f}s]')


def main(argv):
    years = list(YEARS)
    if '--years' in argv:
        i = argv.index('--years'); years = argv[i + 1:]; argv = argv[:i]
    states = [s.upper() for s in argv] or list(STATES)
    booths = load_booths()
    for st in states:
        run(st, years, booths)


if __name__ == '__main__':
    main(sys.argv[1:])
