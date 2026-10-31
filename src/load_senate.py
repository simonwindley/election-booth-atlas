"""Senate first preferences by polling place (Victoria), scraped from the AEC Tally Room's per-polling-place
Senate pages (the AEC publishes no CSV for this) into raw/aec/senate/senate_pp_<event>.json:
    {polling_place_id: {d: division_id, name, premises, formal, informal, groups: [{g, party, atl, total, first}]}}

Usage: python3 -m src.load_senate <event_id> <year> <raw_json> <out_dir>
Writes <out_dir>/sen_groups.csv: one row per polling place x group (ATL votes, group total incl. BTL), plus
<out_dir>/sen_booths.csv (formal/informal per polling place). Booth ids are the House ids (fed-<PollingPlaceID>).
"""
import sys, os, json
import pandas as pd
from .parties import canon_from_name, canon_from_aec

AB = {'Liberal/The Nationals': 'LIB', 'Liberal': 'LIB', 'The Nationals': 'NAT', 'UAP': 'UAP', 'Australian Labor Party': 'ALP',
      'The Greens': 'GRN', 'Australian Greens': 'GRN', "Pauline Hanson's One Nation": 'ONP', 'Victorian Socialists': 'VSP',
      'Derryn Hinch\'s Justice Party': 'DHJ', 'Legalise Cannabis Australia': 'LCP', 'Animal Justice Party': 'AJP', 'Ungrouped': 'IND',
      'Trumpet of Patriots': 'UAP', 'Palmer United Party': 'UAP', 'Liberal Democrats': 'LDP', 'Libertarian': 'LDP', 'Family First': 'FFP',
      'Family First Party': 'FFP', 'Sustainable Australia Party - Stop Overdevelopment / Corruption': 'SAP', 'Sustainable Australia': 'SAP',
      'Australian Democrats': 'DEM', 'Democratic Labour Party': 'DLP', 'Democratic Labor Party': 'DLP', 'Shooters, Fishers and Farmers': 'SFF',
      'Reason Australia': 'FRP', 'Australian Sex Party': 'FRP', 'Sex Party': 'FRP', 'Rise Up Australia Party': 'RUA', "Katter's Australian Party": 'KAP',
      'Citizens Electoral Council': 'ACP', 'Australian Citizens Party': 'ACP', 'Australian Christians': 'AUC', 'Christian Democratic Party': 'CDP',
      'Socialist Alliance': 'OTH', 'Socialist Equality Party': 'OTH'}


def canon(name):
    if name in AB:
        return AB[name]
    return canon_from_name(name) if name else 'IND'


def main(event, year, raw, out):
    eid = f'fed{year}'
    d = json.load(open(raw))
    rows, booths = [], []
    for pp, rec in d.items():
        bid = f'fed-{pp}'
        booths.append({'election_id': eid, 'booth_id': bid, 'contest_id': f'fed-{rec["d"]}', 'booth_name': rec['name'], 'premises': rec.get('premises') or '',
                       'formal': rec['formal'], 'informal': rec['informal']})
        for g in rec['groups']:
            pname = g['party'] or (f'Group {g["g"]} ({g.get("first") or "unnamed"})' if g['g'] != 'UG' else 'Ungrouped')
            rows.append({'election_id': eid, 'contest_id': f'fed-{rec["d"]}', 'booth_id': bid, 'grp': g['g'], 'party_name': pname,
                         'party': canon(g['party']) if g['party'] else 'IND', 'atl': g['atl'] or 0, 'votes': g['total'] if g['total'] is not None else (g['atl'] or 0)})
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(rows).to_csv(f'{out}/sen_groups.csv', index=False)
    pd.DataFrame(booths).to_csv(f'{out}/sen_booths.csv', index=False)
    df = pd.DataFrame(rows)
    tot = df.votes.sum(); formal = sum(b['formal'] or 0 for b in booths)
    print(f'{eid}: {len(booths)} polling places, {len(df)} group rows, group votes {tot:,} v formal {formal:,} ({"ok" if abs(tot - formal) <= len(booths) else "MISMATCH"})')
    print(df.groupby('party').votes.sum().sort_values(ascending=False).head(10).to_dict())


if __name__ == '__main__':
    main(*sys.argv[1:5])
