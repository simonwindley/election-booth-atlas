"""Load AEC House of Representatives results (Victoria only) into the common schema.

Usage: python3 -m src.load_aec <event_id> <year> <raw_dir> <out_dir> [STATES]
STATES defaults to VIC (the Atlas); ALL, or a comma list such as NSW,QLD, loads other states (src.load_national).
Produces long-format CSVs in <out_dir>: contests, candidates, booths, fp_votes,
tcp_votes, dop (distribution of preferences). All keyed on election_id.
"""
import sys, os
import pandas as pd
from .parties import canon_from_aec

VOTE_TYPES = {  # AEC vote-type columns -> common booth_type codes
    'OrdinaryVotes': None,  # already represented by booths
    'AbsentVotes': 'absent', 'ProvisionalVotes': 'provisional',
    'PrePollVotes': 'early_declaration', 'PostalVotes': 'postal',
}


def rd(path):
    return pd.read_csv(path, skiprows=1, dtype=str)


def load(event, year, raw, out, states='VIC'):
    eid = f'fed{year}'
    pp = rd(f'{raw}/GeneralPollingPlacesDownload-{event}.csv')
    for col in ('Latitude', 'Longitude', 'PremisesAddress1', 'PremisesSuburb', 'PremisesPostCode', 'PremisesNm'):
        if col not in pp.columns:   # the 2004 list has no coordinates
            pp[col] = None
    ST = sorted(set(pp.State)) if states == 'ALL' else states.split(',')
    pp = pp[pp.State.isin(ST)].copy()   # the national files (2004, 2007 as downloaded) are cut to Victoria here
    cand = rd(f'{raw}/HouseCandidatesDownload-{event}.csv')
    fp = pd.concat([rd(f'{raw}/HouseStateFirstPrefsByPollingPlaceDownload-{event}-{s}.csv') for s in ST if os.path.exists(f'{raw}/HouseStateFirstPrefsByPollingPlaceDownload-{event}-{s}.csv')], ignore_index=True)
    fpvt = rd(f'{raw}/HouseFirstPrefsByCandidateByVoteTypeDownload-{event}.csv')
    tcp = rd(f'{raw}/HouseTcpByCandidateByPollingPlaceDownload-{event}.csv')
    dop = rd(f'{raw}/HouseDopByDivisionDownload-{event}.csv')
    cand, fpvt, tcp, dop = (d[d.StateAb.isin(ST)].copy() for d in (cand, fpvt, tcp, dop))
    if 'Elected' not in fpvt.columns:   # 2004: elected members come as a separate list
        won = set(rd(f'{raw}/HouseMembersElectedDownload-{event}.csv').CandidateID)
        fpvt['Elected'] = fpvt.CandidateID.isin(won).map({True: 'Y', False: 'N'})
        dop['Elected'] = dop.CandidateID.isin(won).map({True: 'Y', False: 'N'})

    # --- contests
    contests = pp[['DivisionID', 'DivisionNm']].drop_duplicates().rename(
        columns={'DivisionID': 'contest_id', 'DivisionNm': 'contest_name'})
    contests.insert(0, 'election_id', eid)
    contests['house'] = 'HoR'
    contests['contest_id'] = 'fed-' + contests['contest_id']
    if states != 'VIC':
        contests['state'] = contests.contest_id.map(dict(zip('fed-' + pp.DivisionID, pp.State)))

    # --- candidates (from FP by vote type file: has every candidate incl. informal row)
    c = fpvt[fpvt.Surname != 'Informal'].copy()
    candidates = pd.DataFrame({
        'election_id': eid,
        'contest_id': 'fed-' + c.DivisionID,
        'candidate_id': c.CandidateID,
        'surname': c.Surname, 'given_name': c.GivenNm,
        'party_name': c.PartyNm.fillna(''), 'party_ab_src': c.PartyAb.fillna(''),
        'party': [canon_from_aec(a, n) for a, n in zip(c.PartyAb, c.PartyNm)],
        'ballot_position': c.BallotPosition, 'elected': (c.Elected == 'Y').astype(int),
    })

    # --- booths: physical polling places (ordinary + pre-poll ordinary) with coordinates
    ptype = {'1': 'ordinary', '2': 'hospital', '3': 'remote', '4': 'other', '5': 'early'}
    booths = pd.DataFrame({
        'election_id': eid,
        'contest_id': 'fed-' + pp.DivisionID,
        'booth_id': 'fed-' + pp.PollingPlaceID,
        'booth_name': pp.PollingPlaceNm,
        'booth_type': pp.PollingPlaceTypeID.map(ptype).fillna('other'),
        'premises': pp.PremisesNm, 'address': pp.PremisesAddress1.fillna(''),
        'suburb': pp.PremisesSuburb.fillna('').str.title(), 'postcode': pp.PremisesPostCode,
        'lat': pd.to_numeric(pp.Latitude, errors='coerce'),
        'lon': pd.to_numeric(pp.Longitude, errors='coerce'),
    })
    # synthetic division-level "booths" for declaration vote types
    decl = []
    for div, name in contests[['contest_id', 'contest_name']].itertuples(index=False):
        for col, bt in VOTE_TYPES.items():
            if bt:
                decl.append({'election_id': eid, 'contest_id': div, 'booth_id': f'{div}-{bt}',
                             'booth_name': f'{name} {bt}', 'booth_type': bt, 'premises': '',
                             'address': '', 'suburb': '', 'postcode': '', 'lat': None, 'lon': None})
    booths = pd.concat([booths, pd.DataFrame(decl)], ignore_index=True)

    # --- first preferences by booth (ordinary + PPVC) + informal
    f = fp.copy()
    f['candidate_id'] = f.CandidateID.where(f.Surname != 'Informal', 'INFORMAL')
    fp_votes = pd.DataFrame({
        'election_id': eid, 'contest_id': 'fed-' + f.DivisionID,
        'booth_id': 'fed-' + f.PollingPlaceID, 'candidate_id': f.candidate_id,
        'votes': pd.to_numeric(f.OrdinaryVotes),
    })
    rows = []
    for r in fpvt.itertuples(index=False):
        cid = 'INFORMAL' if r.Surname == 'Informal' else r.CandidateID
        for col, bt in VOTE_TYPES.items():
            if bt:
                rows.append({'election_id': eid, 'contest_id': 'fed-' + r.DivisionID,
                             'booth_id': f'fed-{r.DivisionID}-{bt}', 'candidate_id': cid,
                             'votes': int(getattr(r, col))})
    fp_votes = pd.concat([fp_votes, pd.DataFrame(rows)], ignore_index=True)

    # --- TCP by booth (AEC gives ordinary booths; declaration TCP is in the by-vote-type TPP only)
    t = tcp.copy()
    tcp_votes = pd.DataFrame({
        'election_id': eid, 'contest_id': 'fed-' + t.DivisionID,
        'booth_id': 'fed-' + t.PollingPlaceID, 'candidate_id': t.CandidateID,
        'votes': pd.to_numeric(t.OrdinaryVotes),
    })

    # --- distribution of preferences
    d = dop[dop.CalculationType.isin(['Preference Count', 'Transfer Count'])].copy()
    d['CalculationValue'] = pd.to_numeric(d.CalculationValue)
    piv = d.pivot_table(index=['DivisionID', 'CountNumber', 'CandidateID'], columns='CalculationType',
                        values='CalculationValue', aggfunc='first').reset_index()
    piv['CountNumber'] = piv.CountNumber.astype(int)
    dop_out = pd.DataFrame({
        'election_id': eid, 'contest_id': 'fed-' + piv.DivisionID,
        'count_no': piv.CountNumber, 'candidate_id': piv.CandidateID,
        'transfer': piv['Transfer Count'].astype(int),
        'progressive_total': piv['Preference Count'].astype(int),
    })
    # mark the candidate excluded at each count: progressive total becomes 0 at count n having been >0 at n-1
    dop_out = dop_out.sort_values(['contest_id', 'candidate_id', 'count_no'])
    prev = dop_out.groupby(['contest_id', 'candidate_id']).progressive_total.shift(1)
    dop_out['excluded'] = ((dop_out.progressive_total == 0) & (prev > 0)).astype(int)
    dop_out = dop_out.sort_values(['contest_id', 'count_no', 'candidate_id'])

    os.makedirs(out, exist_ok=True)
    for name, df in [('contests', contests), ('candidates', candidates), ('booths', booths),
                     ('fp_votes', fp_votes), ('tcp_votes', tcp_votes), ('dop', dop_out)]:
        df.to_csv(f'{out}/{name}.csv', index=False)
        print(f'{eid} {name}: {len(df)} rows')


if __name__ == '__main__':
    load(*sys.argv[1:6])
