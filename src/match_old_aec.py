"""Give the 2004 and 2007 federal polling places a venue.

The venue table (data/venues/venues.csv) is built from the AEC's 2010-2025 polling-place lists, one venue per
premises and coordinates. The 2007 list has coordinates, the 2004 list does not, and both share the AEC's
polling-place ids with later elections (the id follows the booth name, not the premises). So:

  2007: same premises+coordinates as a venue -> that venue; else the nearest venue within 300 m; else the venue the
        id maps to if it is within 1 km (the premises was renamed); else a new venue, appended to venues.csv with the
        next id so every existing venue id is unchanged.
  2004: the 2007 booth with the same id, when its premises name matches -> that booth's venue; else the id's venue when
        the premises name matches the venue's; else the id's venue anyway (flagged 'id_only': the booth may have moved);
        else unmatched (no coordinates to go on).

Writes data/venues/aec_old_booth_venue.csv (election_id, booth_id, venue_id, method), read by src.build_db.

Usage: python3 -m src.match_old_aec data/venues data/fed2007/booths.csv data/fed2004/booths.csv
"""
import sys, os, ast, math
import pandas as pd
from .match_venues import norm, km


def main(vdir, b2007, b2004):
    V = pd.read_csv(f'{vdir}/venues.csv')
    V['names'] = V.aec_names.map(ast.literal_eval); V['ids'] = V.aec_booth_ids.map(ast.literal_eval)
    by_id = {b: r.venue_id for r in V.itertuples() for b in r.ids}
    by_vkey = dict(zip(V.vkey, V.venue_id))
    vprem = dict(zip(V.venue_id, V.premises.fillna('').map(norm)))
    coords = list(zip(V.venue_id, V.lat, V.lon))
    nxt = [int(V.venue_id.str[1:].max()) + 1]
    new_rows = []
    rows = []

    def nearest(lat, lon, within):
        best = None
        for vid, vla, vlo in coords:
            if abs(vla - lat) > 0.02 or abs(vlo - lon) > 0.02:
                continue
            d = km((lat, lon), (vla, vlo))
            if d <= within and (best is None or d < best[0]):
                best = (d, vid)
        return best

    b7 = pd.read_csv(b2007); b7 = b7[b7.booth_type.isin(['ordinary', 'early', 'hospital', 'other']) & b7.lat.notna()]
    map7 = {}
    for b in b7.itertuples():
        vk = norm(b.premises if isinstance(b.premises, str) else '') + '|' + str(round(b.lat, 2)) + '|' + str(round(b.lon, 2))
        if vk in by_vkey:
            vid, how = by_vkey[vk], 'premises'
        else:
            n = nearest(b.lat, b.lon, 0.3)
            if n:
                vid, how = n[1], 'nearest'
            elif b.booth_id in by_id and km((b.lat, b.lon), next((la, lo) for v, la, lo in coords if v == by_id[b.booth_id])) <= 1.0:
                vid, how = by_id[b.booth_id], 'id'
            else:
                vid = f'v{nxt[0]:05d}'; nxt[0] += 1; how = 'new'
                new_rows.append({'vkey': vk, 'premises': b.premises, 'address': b.address, 'suburb': b.suburb, 'postcode': b.postcode,
                                 'lat': b.lat, 'lon': b.lon, 'aec_names': str([norm(b.booth_name)]), 'aec_booth_ids': str([b.booth_id]), 'venue_id': vid})
                by_vkey[vk] = vid; coords.append((vid, b.lat, b.lon)); vprem[vid] = norm(b.premises if isinstance(b.premises, str) else '')
        map7[b.booth_id] = (vid, norm(b.premises if isinstance(b.premises, str) else ''))
        rows.append({'election_id': 'fed2007', 'booth_id': b.booth_id, 'venue_id': vid, 'method': how})

    b4 = pd.read_csv(b2004); b4 = b4[b4.booth_type.isin(['ordinary', 'early', 'hospital', 'other'])]
    for b in b4.itertuples():
        prem = norm(b.premises if isinstance(b.premises, str) else '')
        if b.booth_id in map7 and map7[b.booth_id][1] == prem:
            vid, how = map7[b.booth_id][0], 'id_2007'
        elif b.booth_id in by_id and vprem.get(by_id[b.booth_id]) == prem:
            vid, how = by_id[b.booth_id], 'id_premises'
        elif b.booth_id in map7:
            vid, how = map7[b.booth_id][0], 'id_only'
        elif b.booth_id in by_id:
            vid, how = by_id[b.booth_id], 'id_only'
        else:
            vid, how = None, 'unmatched'
        rows.append({'election_id': 'fed2004', 'booth_id': b.booth_id, 'venue_id': vid, 'method': how})
    m = pd.DataFrame(rows)
    m.to_csv(f'{vdir}/aec_old_booth_venue.csv', index=False)
    if new_rows:
        pd.concat([V.drop(columns=['names', 'ids']), pd.DataFrame(new_rows)], ignore_index=True).to_csv(f'{vdir}/venues.csv', index=False)
    print(m.groupby('election_id').method.value_counts())
    print(f'{len(new_rows)} new venues appended (2007 premises not seen 2010-2025)')


if __name__ == '__main__':
    main(*sys.argv[1:4])
