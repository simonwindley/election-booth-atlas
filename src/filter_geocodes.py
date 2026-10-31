"""Turn raw Nominatim hits for unmatched VEC booths into data/venues/geocoded.csv,
keeping only plausible ones: inside the district's footprint (centroid + radius of the
booths already pinned to AEC venues) and of a sensible feature type.

Usage: python3 -m src.filter_geocodes <raw_geocodes.json> <data_dir>
"""
import sys, json, math
import pandas as pd

GOOD_TYPES = {'suburb', 'locality', 'neighbourhood', 'village', 'town', 'hamlet', 'city', 'station',
              'school', 'park', 'administrative', 'residential', 'primary', 'secondary', 'tertiary',
              'community_centre', 'kindergarten', 'college', 'church', 'place_of_worship', 'hall',
              'sports_centre', 'pitch', 'recreation_ground', 'golf_course', 'peak', 'quarter', 'retail',
              'townhall', 'library', 'nature_reserve', 'garden', 'playground', 'social_facility', 'mall', 'post_office'}


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(d))


def main(raw_path, data_dir):
    raw = json.load(open(raw_path))
    m = pd.read_csv(f'{data_dir}/venues/vec_booth_venue.csv')
    v = pd.read_csv(f'{data_dir}/venues/venues.csv')
    mm = m[m.method.str.startswith('exact')].merge(v[['venue_id', 'lat', 'lon']], on='venue_id')
    foot = {}
    for cid, g in mm.groupby('contest_id'):
        c = (g.lat.mean(), g.lon.mean())
        r = max([km(c, (a, b)) for a, b in zip(g.lat, g.lon)] + [3])
        foot[cid] = (c, r)
    booth_contest = dict(zip(m.booth_id, m.contest_id))
    rows, rejected = [], []
    for bid, h in raw.items():
        if h.get('via') in ('none', 'err') or 'lat' not in h:
            rejected.append((bid, 'no hit')); continue
        c, r = foot.get(booth_contest.get(bid), ((None, None), None))
        if c[0] is None:
            rejected.append((bid, 'no footprint')); continue
        d = km(c, (h['lat'], h['lon']))
        if d > r + 3:
            rejected.append((bid, f'{d:.0f} km from district, outside footprint {r:.0f} km')); continue
        if h.get('type') not in GOOD_TYPES:
            rejected.append((bid, f"type {h.get('type')}")); continue
        rows.append({'booth_id': bid, 'lat': h['lat'], 'lon': h['lon'], 'via': h['via'], 'type': h['type'],
                     'display_name': h.get('disp', ''), 'dist_from_district_centroid_km': round(d, 1)})
    out = pd.DataFrame(rows)
    out.to_csv(f'{data_dir}/venues/geocoded.csv', index=False)
    pd.DataFrame(rejected, columns=['booth_id', 'reason']).to_csv(f'{data_dir}/venues/geocode_rejected.csv', index=False)
    print(f'accepted {len(out)} approximate geocodes, rejected {len(rejected)}')
    print(pd.DataFrame(rejected, columns=['booth_id', 'reason']).reason.str.split(' ').str[0].value_counts().head())


if __name__ == '__main__':
    main(*sys.argv[1:3])
