"""Load the national AEC files (every state and territory) into a separate database, data/national.sqlite.

The Victorian Atlas is untouched: this is the start of the national expansion and the evidence base for the One
Nation work (preference flows where One Nation is still in the count, House v Senate, by-elections).

Inputs  raw/national/aec/<event>/   (tools/fetch_national.sh)
Output  data/national/<election_id>/*.csv and data/national.sqlite
          tables: elections, contests (with state), candidates, booths, fp_votes, tcp_votes, dop, sen_division
Usage   python3 -m src.load_national
"""
import os, io, glob, zipfile, sqlite3
import pandas as pd
from .load_aec import load as load_aec
from .parties import canon_from_aec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'raw/national/aec')
OUT = os.path.join(ROOT, 'data/national')
GENERAL = {'31496': ('2025', '2025-05-03'), '27966': ('2022', '2022-05-21'), '24310': ('2019', '2019-05-18'), '20499': ('2016', '2016-07-02')}
BYELECTIONS = {   # event: (election_id, date, state)
    '31633': ('fedby-farrer-2026', '2026-05-09', 'NSW'), '29807': ('fedby-cook-2024', '2024-04-13', 'NSW'),
    '29778': ('fedby-dunkley-2024', '2024-03-02', 'VIC'), '29422': ('fedby-fadden-2023', '2023-07-15', 'QLD'),
    '28791': ('fedby-aston-2023', '2023-04-01', 'VIC'), '25881': ('fedby-groom-2020', '2020-11-28', 'QLD'),
    '25820': ('fedby-edenmonaro-2020', '2020-07-04', 'NSW')}
EXTRA = {'GRPF': 'PFP', 'XEN': 'CEN'}    # parties outside Victoria's history; kept out of src/parties.py so the Atlas is unchanged


def rd(path_or_buf):
    return pd.read_csv(path_or_buf, skiprows=1, dtype=str)


def canon(ab, name):
    return EXTRA.get(str(ab).strip(), canon_from_aec(ab, name))


def general(event, year):
    out = os.path.join(OUT, f'fed{year}')
    load_aec(event, year, os.path.join(RAW, event), out, states='ALL')
    c = pd.read_csv(f'{out}/candidates.csv', dtype=str)
    c['party'] = [EXTRA.get(a, p) for a, p in zip(c.party_ab_src.fillna(''), c.party)]
    c.to_csv(f'{out}/candidates.csv', index=False)
    # Senate first preferences by division (groups), for House v Senate
    f = os.path.join(RAW, event, f'SenateFirstPrefsByDivisionByVoteTypeDownload-{event}.csv')
    if os.path.exists(f):
        s = rd(f)
        s['votes'] = pd.to_numeric(s.TotalVotes, errors='coerce').fillna(0)
        s['party'] = [canon(a, n) for a, n in zip(s.PartyAb.fillna(''), s.PartyName.fillna(''))] if 'PartyName' in s.columns else [canon(a, '') for a in s.PartyAb.fillna('')]
        g = s.groupby(['StateAb', 'DivisionID', 'DivisionNm', 'party'], as_index=False).votes.sum()
        g.insert(0, 'election_id', f'fed{year}'); g['contest_id'] = 'fed-' + g.DivisionID
        g.rename(columns={'StateAb': 'state', 'DivisionNm': 'contest_name'})[['election_id', 'state', 'contest_id', 'contest_name', 'party', 'votes']].to_csv(f'{out}/sen_division.csv', index=False)


def byelection(event, eid, state):
    raw = os.path.join(RAW, event); out = os.path.join(OUT, eid)
    cand = rd(f'{raw}/HouseCandidatesDownload-{event}.csv')
    z = zipfile.ZipFile(f'{raw}/HouseDopByPPDownload-{event}-{state}.zip')
    d = rd(io.TextIOWrapper(z.open(z.namelist()[0]), encoding='utf-8-sig'))
    d['v'] = pd.to_numeric(d.CalculationValue, errors='coerce').fillna(0)
    div = d.DivisionId.iloc[0]; cid = f'fed-{div}'; name = d.DivisionNm.iloc[0]
    contests = pd.DataFrame([{'election_id': eid, 'contest_id': cid, 'contest_name': name, 'house': 'HoR', 'state': state}])
    candidates = pd.DataFrame({'election_id': eid, 'contest_id': cid, 'candidate_id': cand.CandidateID, 'surname': cand.Surname, 'given_name': cand.GivenNm,
                               'party_name': cand.PartyNm.fillna(''), 'party_ab_src': cand.PartyAb.fillna(''),
                               'party': [canon(a, n) for a, n in zip(cand.PartyAb.fillna(''), cand.PartyNm.fillna(''))],
                               'ballot_position': None, 'elected': (cand.Elected == 'Y').astype(int)})
    pos = d.drop_duplicates('CandidateId').set_index('CandidateId').BallotPosition
    candidates['ballot_position'] = candidates.candidate_id.map(pos)
    pc = d[d.CalculationType == 'Preference Count']
    first = pc[pc.CountNum == '0']
    booths = first.drop_duplicates('PPId')[['PPId', 'PPNm']]
    booths = pd.DataFrame({'election_id': eid, 'contest_id': cid, 'booth_id': 'fed-' + booths.PPId, 'booth_name': booths.PPNm, 'booth_type': 'ordinary',
                           'premises': '', 'address': '', 'suburb': '', 'postcode': '', 'lat': None, 'lon': None})
    fp_votes = pd.DataFrame({'election_id': eid, 'contest_id': cid, 'booth_id': 'fed-' + first.PPId, 'candidate_id': first.CandidateId, 'votes': first.v.astype(int)})
    tot = pc.groupby(['CountNum', 'CandidateId'], as_index=False).v.sum()
    tr = d[d.CalculationType == 'Transfer Count'].groupby(['CountNum', 'CandidateId'], as_index=False).v.sum().rename(columns={'v': 't'})
    m = tot.merge(tr, on=['CountNum', 'CandidateId'], how='left').fillna({'t': 0})
    m['count_no'] = m.CountNum.astype(int)
    dop = pd.DataFrame({'election_id': eid, 'contest_id': cid, 'count_no': m.count_no, 'candidate_id': m.CandidateId, 'transfer': m.t.astype(int), 'progressive_total': m.v.astype(int)})
    dop = dop.sort_values(['candidate_id', 'count_no'])
    prev = dop.groupby('candidate_id').progressive_total.shift(1)
    dop['excluded'] = ((dop.progressive_total == 0) & (prev > 0)).astype(int)
    t = rd(f'{raw}/HouseTcpByCandidateByPollingPlaceDownload-{event}.csv')
    tcp_votes = pd.DataFrame({'election_id': eid, 'contest_id': cid, 'booth_id': 'fed-' + t.PollingPlaceID, 'candidate_id': t.CandidateID, 'votes': pd.to_numeric(t.OrdinaryVotes)})
    os.makedirs(out, exist_ok=True)
    for n, df in [('contests', contests), ('candidates', candidates), ('booths', booths), ('fp_votes', fp_votes), ('tcp_votes', tcp_votes), ('dop', dop.sort_values(['count_no', 'candidate_id']))]:
        df.to_csv(f'{out}/{n}.csv', index=False)
    print(f'{eid}: {len(candidates)} candidates, {dop.count_no.max()} counts')


def build():
    db = os.path.join(ROOT, 'data/national.sqlite')
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db); tables = {}
    for d in sorted(glob.glob(f'{OUT}/*/')):
        for f in glob.glob(f'{d}/*.csv'):
            tables.setdefault(os.path.basename(f)[:-4], []).append(pd.read_csv(f, dtype={'candidate_id': str, 'booth_id': str, 'contest_id': str}))
    for t, dfs in tables.items():
        pd.concat(dfs, ignore_index=True).to_sql(t, con, index=False)
    el = [{'election_id': f'fed{y}', 'level': 'federal', 'date': dt, 'name': f'Federal election {y}'} for e, (y, dt) in GENERAL.items()]
    el += [{'election_id': eid, 'level': 'federal-by', 'date': dt, 'name': eid.split('-')[1].title() + ' by-election ' + eid[-4:]} for e, (eid, dt, s) in BYELECTIONS.items()]
    pd.DataFrame(el).to_sql('elections', con, index=False)
    for ix in ('create index ix_fp on fp_votes(election_id, contest_id)', 'create index ix_dop on dop(election_id, contest_id)', 'create index ix_c on candidates(election_id, candidate_id)'):
        con.execute(ix)
    con.commit()
    print(db, {t: sum(len(x) for x in v) for t, v in tables.items()})


def main():
    for e, (y, dt) in GENERAL.items():
        if os.path.isdir(os.path.join(RAW, e)):
            general(e, y)
    for e, (eid, dt, s) in BYELECTIONS.items():
        if os.path.isdir(os.path.join(RAW, e)):
            byelection(e, eid, s)
    build()


if __name__ == '__main__':
    main()
