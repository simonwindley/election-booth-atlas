"""Placebo weather for the weather-and-mood question: for every station and every general election, the same readings
as election day (voting-hours rain = the next morning's 9 am figure; maximum temperature and its departure from the
station's normal for that calendar day; the 30 days before) on 40 other Saturdays, 2 to 21 weeks either side of the
election. Weather on those days cannot have moved the vote, but it has the same regional patterns as election-day
weather, so analyses run on them show what chance and regional coincidence produce.

Standard library only (runs on the Mac). Output data/weather/placebo_days.csv (k = weeks from the election; 0 is the
real day).
Usage: python3 -m src.weather_placebo
"""
import os, csv, glob, gzip, json, datetime as dt
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'raw', 'weather', 'silo')
GENERAL = ('vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022', 'fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025')
KS = [0] + [k for k in range(-21, 22) if abs(k) >= 2]


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/elections.json.gz')))
    E = {r[0]: dt.date.fromisoformat(r[2]) for r in d['rows'] if r[0] in GENERAL}
    out = open(os.path.join(ROOT, 'data/weather/placebo_days.csv'), 'w', newline='')
    w = csv.writer(out); w.writerow(['station', 'election_id', 'k', 'date', 'rain_vote', 'rain_obs', 'tmax', 'tmax_anom', 'rain_30d_ratio', 'tmax_30d_anom'])
    n = 0
    for f in sorted(glob.glob(os.path.join(SRC, '*.csv'))):
        stn = os.path.basename(f)[:-4]
        rain, rsrc, tmax = {}, {}, {}
        with open(f, newline='', encoding='latin-1') as fh:
            r = csv.reader(fh); next(r)
            for x in r:
                if len(x) < 8:
                    continue
                try:
                    dd = dt.date.fromisoformat(x[1])
                except ValueError:
                    continue
                rain[dd] = num(x[2]); rsrc[dd] = x[3].strip(); tmax[dd] = num(x[4])
        # climatology by day of year (1998-2025): mean tmax, mean rain
        ct, cr = defaultdict(list), defaultdict(list)
        for dd, v in tmax.items():
            if v is not None and dd.year <= 2025:
                ct[(dd.month, dd.day)].append(v)
        for dd, v in rain.items():
            if v is not None and dd.year <= 2025:
                cr[(dd.month, dd.day)].append(v)
        mt = {k: sum(v) / len(v) for k, v in ct.items()}; mr = {k: sum(v) / len(v) for k, v in cr.items()}
        for eid, ed in E.items():
            for k in KS:
                day = ed + dt.timedelta(weeks=k)
                nx = day + dt.timedelta(days=1)
                if day not in tmax or nx not in rain or tmax[day] is None:
                    continue
                win = [day - dt.timedelta(days=i) for i in range(1, 31)]
                rs = [rain.get(x) for x in win]; ts = [tmax.get(x) for x in win]
                if sum(v is None for v in rs) > 3:
                    r30 = ''; t30 = ''
                else:
                    norm_r = sum(mr.get((x.month, x.day), 0) for x in win); norm_t = sum(mt.get((x.month, x.day), 0) for x in win) / 30
                    r30 = round(sum(v or 0 for v in rs) / norm_r, 3) if norm_r > 0 else ''
                    t30 = round(sum(v for v in ts if v is not None) / max(1, sum(v is not None for v in ts)) - norm_t, 2)
                w.writerow([stn, eid, k, day.isoformat(), rain[nx], int(rsrc.get(nx) in ('0', '15')), tmax[day], round(tmax[day] - mt.get((day.month, day.day), tmax[day]), 2), r30, t30])
                n += 1
    out.close()
    print(n, 'station-days ->', 'data/weather/placebo_days.csv')


if __name__ == '__main__':
    main()
