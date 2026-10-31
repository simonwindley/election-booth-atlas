"""Booth catchments: a Voronoi cell for every election-day booth, clipped to the district the booth
served, so that any geography can be expressed as a weighted sum of booths.

For each (election, boundary set):
  - take ordinary booths with coordinates
  - Voronoi-partition each district among its own booths and clip to the district polygon
  - write data/catchments/<election_id>.geojson with booth_id, contest_id, area_km2
Also writes data/catchments/h3_<election_id>.csv: booth -> H3 cell (res 7, ~5 km2) share by area,
so booth results can be re-aggregated onto a hex grid in the front end.

Usage: python3 -m src.catchments <db_path>
"""
import sys, os, json, sqlite3
import pandas as pd
from shapely.geometry import shape, Point, MultiPoint, mapping, Polygon
from shapely.ops import voronoi_diagram
from shapely import make_valid
import h3

OUT = 'data/catchments'
SETS = {'vic2010': 'vic_la_2001', 'vic2014': 'vic_la_2013', 'vic2018': 'vic_la_2013', 'vic2022': 'vic_la_2022', 'vic2023n': 'vic_la_2022', 'fed2010': 'fed_2003', 'fed2013': 'fed_2010', 'fed2016': 'fed_2010', 'fed2019': 'fed_2018', 'fed2022': 'fed_2021', 'fed2025': 'fed_2024'}


def polygons(set_name):
    fc = json.load(open(f'data/boundaries/{set_name}.geojson'))
    return {f['properties']['contest_id']: make_valid(shape(f['geometry'])) for f in fc['features']}


def build(con, eid, set_name):
    polys = polygons(set_name)
    b = pd.read_sql(f"""SELECT g.contest_id, g.booth_id, g.lat, g.lon, g.geo_source, b.booth_name
                        FROM booth_geo g JOIN booths b ON b.booth_id = g.booth_id AND b.election_id = g.election_id
                        WHERE g.election_id = '{eid}' AND g.booth_type = 'ordinary' AND g.lat IS NOT NULL""", con)
    feats, h3rows, outside = [], [], []
    for cid, grp in b.groupby('contest_id'):
        poly = polys.get(cid)
        if poly is None:
            continue
        pts = []
        for r in grp.itertuples():
            p = Point(r.lon, r.lat)
            if poly.contains(p) or poly.distance(p) < 0.01:  # allow ~1 km slop for approximate geocodes
                pts.append((r.booth_id, p))
            else:
                outside.append((cid, r.booth_id, r.booth_name, r.geo_source, round(poly.distance(p) * 111, 1)))
        if not pts:
            continue
        if len(pts) == 1:
            cells = {pts[0][0]: poly}
        else:
            vd = voronoi_diagram(MultiPoint([p for _, p in pts]), envelope=poly.envelope.buffer(1))
            cells = {}
            for cell in vd.geoms:
                for bid, p in pts:
                    if cell.contains(p):
                        cells[bid] = make_valid(cell.intersection(poly))
                        break
        for bid, geom in cells.items():
            if geom.is_empty:
                continue
            # approximate area in km2 (degrees -> km at this latitude)
            lat = geom.centroid.y
            area_km2 = geom.area * 111.32 * 111.32 * abs(__import__('math').cos(__import__('math').radians(lat)))
            feats.append({'type': 'Feature', 'properties': {'booth_id': bid, 'contest_id': cid, 'area_km2': round(area_km2, 3)},
                          'geometry': json.loads(json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), 5))})
            # H3 coverage: polyfill the cell at res 8, share = 1/n cells (area-weighted would be nicer; cells are equal-area)
            try:
                cells_h3 = h3.geo_to_cells(h3.geo_to_h3shape(mapping(geom)), 7) if geom.geom_type == 'Polygon' else \
                    [c for g in geom.geoms for c in h3.geo_to_cells(h3.geo_to_h3shape(mapping(g)), 7)]
            except Exception:
                cells_h3 = []
            if not cells_h3:
                cells_h3 = [h3.latlng_to_cell(geom.centroid.y, geom.centroid.x, 7)]
            for c in cells_h3:
                h3rows.append({'election_id': eid, 'booth_id': bid, 'h3': c, 'share': round(1 / len(cells_h3), 6)})
    os.makedirs(OUT, exist_ok=True)
    with open(f'{OUT}/{eid}.geojson', 'w') as f:
        json.dump({'type': 'FeatureCollection', 'features': feats}, f, separators=(',', ':'))
    pd.DataFrame(h3rows).to_csv(f'{OUT}/h3_{eid}.csv', index=False)
    pd.DataFrame(outside, columns=['contest_id', 'booth_id', 'booth_name', 'geo_source', 'km_outside']).to_csv(f'{OUT}/outside_{eid}.csv', index=False)
    print(f'{eid}: {len(feats)} catchments, {len(h3rows)} h3 rows, {len(outside)} booths outside their district (skipped)')


if __name__ == '__main__':
    con = sqlite3.connect(sys.argv[1])
    for eid, s in SETS.items():
        build(con, eid, s)
