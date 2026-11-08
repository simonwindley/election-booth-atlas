"""Apportion the 2006 Census Collection Districts (CDs) to electoral areas by area, as src.sa1_weights does for SA1s.

A CD is the 2006 census's smallest area (about 220 dwellings, a few streets in a city, more country in the bush).
Targets:
  d22  the 2022 Victorian districts            -> 2006 history for the 2022-boundary census file
  b22  the 2022 election-day booth catchments  -> 2006 history for each booth venue (the same area, 16 years earlier)
  d01  the 2001 Victorian districts            -> the census file for the 2002, 2006 and 2010 elections
  f03  the federal divisions as at 2003-2010    -> the census file for the 2004, 2007 and 2010 federal elections

Input  raw/boundaries/abs/cd06/CD06aVIC.shp   (ABS ASGC 2006 digital boundaries, cat. 1259.0.30.002, GDA94)
Output raw/abs/cd_weights_2006.json           {cd: {"d22": {id: w}, "b22": {...}, "d01": {...}, "f03": {...}}}
Usage  python3 -m src.cd_weights
"""
import os, json
import shapefile
from shapely.geometry import shape
from shapely.validation import make_valid
from shapely.ops import transform
from .sa1_weights import ROOT, TO_M, load_fc, geom, apportion


def cds():
    r = shapefile.Reader(os.path.join(ROOT, 'raw/boundaries/abs/cd06/CD06aVIC.shp'))
    out = []
    for sr in r.iterShapeRecords():
        g = shape(sr.shape.__geo_interface__)
        if not g.is_valid:
            g = make_valid(g)
        out.append((sr.record['CD_CODE06'], transform(TO_M, g)))   # GDA94 ~ WGS84 at this scale
    return out


def targets(name):
    if name == 'b22':
        t = []
        for e in ('vic2022', 'vic2023n'):
            t += [(f['properties']['booth_id'], geom(f)) for f in load_fc(os.path.join(ROOT, f'site/data/catchment_{e}.geojson.gz'))['features']]
        return t
    bset = {'d22': 'vic_la_2022', 'd01': 'vic_la_2001', 'f03': 'fed_2003'}[name]
    return [(f['properties']['contest_id'], geom(f)) for f in load_fc(os.path.join(ROOT, f'site/data/boundary_{bset}.geojson.gz'))['features'] if f['properties'].get('contest_id')]


def main():
    units = cds()
    print(f'{len(units)} CDs')
    W = {}
    for name in ('d22', 'b22', 'd01', 'f03'):
        t = targets(name)
        w = apportion(units, t)
        for code, ws in w.items():
            W.setdefault(code, {})[name] = ws
        print(f'  {name}: {len(t)} targets, {len(w)} CDs apportioned, {sum(1 for v in w.values() if len(v) > 1)} split')
    path = os.path.join(ROOT, 'raw/abs/cd_weights_2006.json')
    json.dump({'census': 2006, 'method': 'area share of each 2006 CD inside each target (pieces under 0.5% dropped, renormalised)', 'cd': W}, open(path, 'w'), separators=(',', ':'))
    print('->', path)


if __name__ == '__main__':
    main()
