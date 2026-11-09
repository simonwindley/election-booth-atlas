"""Reduce the SILO station files (raw/weather/silo/*.csv, tools/fetch_silo.py) to what the weather question needs:
for every station and every election (general and by-election, state and federal) the election-day rain (the
reading of the morning after: rainfall is the 24 hours to 9 am, so voting-hours rain lands in the next day's figure) and
temperatures, the 30 days before, and each station's normal for those same calendar days (the mean over 1998-2025
of the same windows, so an election day can be read as wetter or hotter than usual).

Standard library only (runs on the Mac). Output data/weather/station_elections.csv and data/weather/stations.csv.
Usage: python3 -m src.weather_reduce
"""
import os, csv, glob, gzip, json, datetime as dt
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'raw', 'weather', 'silo')
OUT = os.path.join(ROOT, 'data', 'weather')
LEAD = 30


def elections():
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/elections.json.gz')))
    return {r[0]: dt.date.fromisoformat(r[2]) for r in d['rows']}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    E = elections()
    os.makedirs(OUT, exist_ok=True)
    stations = []; rows = []
    for f in sorted(glob.glob(os.path.join(SRC, '*.csv'))):
        stn = os.path.basename(f)[:-4]
        day = {}; meta = {}
        with open(f, newline='', encoding='latin-1') as fh:
            r = csv.reader(fh); head = next(r)
            for x in r:
                if len(x) < 8:
                    continue
                m = x[8] if len(x) > 8 else ''
                if '=' in m:
                    k, v = m.split('=', 1); meta[k.strip()] = v.strip().strip('"')
                try:
                    d = dt.date.fromisoformat(x[1])
                except ValueError:
                    continue
                day[d] = (num(x[2]), x[3].strip(), num(x[4]), x[5].strip(), num(x[6]), x[7].strip())
        if not day:
            continue
        stations.append({'station': stn, 'name': meta.get('name', ''), 'lat': meta.get('latitude', ''), 'lon': meta.get('longitude', ''), 'elevation': meta.get('elevation', ''),
                         'first': min(day).isoformat(), 'last': max(day).isoformat()})
        years = sorted({d.year for d in day})
        for eid, ed in E.items():
            if ed not in day:
                continue
            def window(end, n):
                ds = [end - dt.timedelta(days=i) for i in range(1, n + 1)]
                v = [day.get(d) for d in ds]
                v = [x for x in v if x]
                if len(v) < n * 0.9:
                    return None
                return (sum(x[0] or 0 for x in v), sum(x[2] for x in v if x[2] is not None) / len(v), sum(1 for x in v if (x[0] or 0) >= 1))
            e = day[ed]; w = window(ed, LEAD)
            nx = day.get(ed + dt.timedelta(days=1))   # rain falling during voting (8 am - 6 pm) is in the next morning's 9 am reading
            # normals: the same calendar day / window in every other year
            nd, nw, nn = [], [], []
            for y in years:
                if y == ed.year:
                    continue
                try:
                    d2 = ed.replace(year=y)
                except ValueError:
                    continue
                if d2 in day and day[d2][0] is not None:
                    nd.append(day[d2])
                n2 = day.get(d2 + dt.timedelta(days=1))
                if n2 and n2[0] is not None:
                    nn.append(n2[0])
                ww = window(d2, LEAD)
                if ww:
                    nw.append(ww)
            if len(nd) < 10:
                continue
            avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else ''
            rows.append({'station': stn, 'election_id': eid, 'date': ed.isoformat(),
                         'rain_vote': nx[0] if nx else '', 'rain_vote_src': nx[1] if nx else '', 'rain_vote_normal': avg(nn), 'rain_vote_wet_share': round(sum(1 for x in nn if x >= 1) / len(nn), 3) if nn else '',
                         'rain': e[0], 'rain_src': e[1], 'tmax': e[2], 'tmax_src': e[3], 'tmin': e[4], 'tmin_src': e[5],
                         'rain_normal': avg([x[0] or 0 for x in nd]), 'rain_wet_share': round(sum(1 for x in nd if (x[0] or 0) >= 1) / len(nd), 3),
                         'tmax_normal': avg([x[2] for x in nd if x[2] is not None]),
                         'rain_30d': round(w[0], 1) if w else '', 'tmax_30d': round(w[1], 2) if w else '', 'wetdays_30d': w[2] if w else '',
                         'rain_30d_normal': avg([x[0] for x in nw]), 'tmax_30d_normal': avg([x[1] for x in nw]), 'wetdays_30d_normal': avg([x[2] for x in nw])})
    for name, data in (('stations.csv', stations), ('station_elections.csv', rows)):
        with open(os.path.join(OUT, name), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0])); w.writeheader(); w.writerows(data)
    print(len(stations), 'stations;', len(rows), 'station-elections ->', OUT)


if __name__ == '__main__':
    main()
