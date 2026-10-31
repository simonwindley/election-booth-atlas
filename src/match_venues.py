"""Match VEC voting centres (name only) to AEC polling places (name + coordinates).

Strategy, per VEC district:
 1. exact (normalised) name match against all Victorian AEC booths from the federal
    elections supplied; if the name is unique in VIC, accept.
 2. if the name is ambiguous (e.g. several "Central" booths), pick the candidate closest
    to the centroid of the district's already-accepted booths.
 3. fuzzy match (token-based) for the remainder, again constrained to be near the district centroid.
Outputs a venue table and a booth->venue mapping with a confidence code.

Usage: python3 -m src.match_venues <vec_booths.csv> <out_dir> <aec_booths.csv> [<aec_booths.csv> ...]
"""
import sys, os, re, math
import pandas as pd
from difflib import SequenceMatcher


def norm(s):
    s = str(s).lower()
    s = re.sub(r'\b(st|st\.)\b', 'saint', s)
    s = re.sub(r'\bmt\b', 'mount', s)
    s = re.sub(r'[^a-z0-9 ]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(d))


def main(vec_path, out, *aec_paths):
    vec = pd.concat([pd.read_csv(p) for p in vec_path.split(',')], ignore_index=True)
    vec = vec[vec.booth_type == 'ordinary'].drop_duplicates('booth_id').copy()
    aec = pd.concat([pd.read_csv(p) for p in aec_paths], ignore_index=True)
    aec = aec[aec.lat.notna() & aec.booth_type.isin(['ordinary', 'early', 'hospital', 'other'])].copy()
    aec['key'] = aec.booth_name.map(norm)
    # one venue per distinct premises+coords (rounded) across federal elections
    aec['vkey'] = aec.premises.fillna('').map(norm) + '|' + aec.lat.round(2).astype(str) + '|' + aec.lon.round(2).astype(str)
    venues = (aec.sort_values('election_id', ascending=False)
                 .groupby('vkey').agg(premises=('premises', 'first'), address=('address', 'first'),
                                      suburb=('suburb', 'first'), postcode=('postcode', 'first'),
                                      lat=('lat', 'first'), lon=('lon', 'first'),
                                      aec_names=('key', lambda s: sorted(set(s))),
                                      aec_booth_ids=('booth_id', lambda s: sorted(set(s))))
                 .reset_index())
    venues['venue_id'] = ['v' + str(i + 1).zfill(5) for i in range(len(venues))]
    name_index = {}
    for v in venues.itertuples(index=False):
        for n in v.aec_names:
            name_index.setdefault(n, []).append(v)
    all_keys = list(name_index.keys())

    def centroid(pts):
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None

    rows = []
    for cid, grp in vec.groupby('contest_id'):
        accepted = []  # (lat, lon)
        pending = []
        for b in grp.itertuples(index=False):
            k = norm(b.booth_name)
            cands = name_index.get(k, [])
            # same name at venues all within 2 km of each other = one place that moved premises/years
            if cands and all(km((v.lat, v.lon), (cands[0].lat, cands[0].lon)) < 2 for v in cands):
                v = cands[0]; accepted.append((v.lat, v.lon))
                rows.append({'booth_id': b.booth_id, 'contest_id': cid, 'booth_name': b.booth_name, 'venue_id': v.venue_id,
                             'method': 'exact_unique' if len(cands) == 1 else 'exact_cluster', 'score': 1.0, 'dist_km': None})
            else:
                pending.append((b, k, cands))
        c = centroid(accepted)
        radius = max([km(c, p) for p in accepted] + [5]) if c else 50
        for b, k, cands in pending:
            if cands and c:
                v = min(cands, key=lambda v: km(c, (v.lat, v.lon)))
                dist = km(c, (v.lat, v.lon))
                if dist < radius * 1.5:
                    accepted.append((v.lat, v.lon))
                    rows.append({'booth_id': b.booth_id, 'contest_id': cid, 'booth_name': b.booth_name, 'venue_id': v.venue_id,
                                 'method': 'exact_nearest', 'score': 1.0, 'dist_km': round(dist, 1)})
                    continue
            best = None
            for key in all_keys:
                sc = SequenceMatcher(None, k, key).ratio()
                if sc < 0.85:
                    continue
                for v in name_index[key]:
                    dist = km(c, (v.lat, v.lon)) if c else 0
                    if dist > radius * 1.2:
                        continue
                    cand = (sc - dist / 100, sc, dist, v)
                    if best is None or cand > best:
                        best = cand
            if best:
                _, sc, dist, v = best
                rows.append({'booth_id': b.booth_id, 'contest_id': cid, 'booth_name': b.booth_name, 'venue_id': v.venue_id,
                             'method': 'fuzzy', 'score': round(sc, 2), 'dist_km': round(dist, 1)})
            else:
                rows.append({'booth_id': b.booth_id, 'contest_id': cid, 'booth_name': b.booth_name, 'venue_id': None,
                             'method': 'unmatched', 'score': None, 'dist_km': None})
    m = pd.DataFrame(rows)
    os.makedirs(out, exist_ok=True)
    venues.to_csv(f'{out}/venues.csv', index=False)
    m.to_csv(f'{out}/vec_booth_venue.csv', index=False)
    print(m.method.value_counts())
    print(f'matched {m.venue_id.notna().mean():.1%} of {len(m)} VEC ordinary voting centres')
    return m


if __name__ == '__main__':
    main(*sys.argv[1:])
