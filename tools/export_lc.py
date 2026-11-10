"""Rebuild only the site's upper-house files from data/*/lc_*.csv (the same queries as src.export_site).

Usage: python3 tools/export_lc.py [data_dir] [site_data_dir]
Writes lc_contests, lc_candidates, lc_groups, lc_result, lc_flows and lc_votes_<election> (.json.gz).
Elections whose votes are region totals only (2006: booth_type 'region') get no lc_votes_<election> file.
"""
import sys, os, glob, sqlite3, re
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.export_site import write


def main(data_dir='data', out='site/data'):
    con = sqlite3.connect(':memory:')
    for t in ['lc_contests', 'lc_candidates', 'lc_votes', 'lc_dop']:
        parts = [pd.read_csv(f) for f in sorted(glob.glob(f'{data_dir}/vic*/{t}.csv'))]
        pd.concat(parts, ignore_index=True).to_sql(t, con, index=False)
    q = lambda s: pd.read_sql(s, con)
    sizes = {}
    names = {'South Eastern Metropolitan': 'South-Eastern Metropolitan'}
    lcc0 = q('SELECT * FROM lc_contests'); lcc0['contest_name'] = lcc0.contest_name.replace(names)
    sizes['lc_contests'] = write(out, 'lc_contests', lcc0)
    sizes['lc_candidates'] = write(out, 'lc_candidates', q('SELECT election_id, contest_id, candidate_id, "group", party, party_name, name, is_atl FROM lc_candidates'))
    for eid in [r[0] for r in con.execute("SELECT DISTINCT election_id FROM lc_votes WHERE booth_type <> 'region'")]:
        sizes['lc_votes_' + eid] = write(out, 'lc_votes_' + eid, q(f"SELECT election_id, contest_id, booth_id, booth_type, candidate_id, votes FROM lc_votes WHERE election_id = '{eid}'"))
    sizes['lc_groups'] = write(out, 'lc_groups', q('''
        SELECT v.election_id, v.contest_id, c."group" AS grp, c.party, c.party_name,
               SUM(CASE WHEN c.is_atl = 1 THEN v.votes ELSE 0 END) AS atl, SUM(CASE WHEN c.is_atl = 0 THEN v.votes ELSE 0 END) AS btl, SUM(v.votes) AS total
        FROM lc_votes v JOIN lc_candidates c ON c.election_id = v.election_id AND c.candidate_id = v.candidate_id
        GROUP BY 1, 2, 3, 4, 5'''))
    lcc = q('SELECT election_id, contest_id, candidate_id, "group" AS grp, party, party_name, name FROM lc_candidates WHERE is_atl = 0')
    nk = lambda x: re.sub(r'[^a-z]', '', str(x).lower())
    lcc['nk'] = lcc.name.map(nk)
    cand_by = {(r.election_id, r.contest_id, r.nk): r for r in lcc.itertuples()}
    who = lambda eid, cid, name: cand_by.get((eid, cid, nk(name)))
    el = q("SELECT election_id, contest_id, MIN(count_no) AS count_no, \"column\" AS name FROM lc_dop WHERE elected = 1 GROUP BY 1, 2, 4 ORDER BY 1, 2, 3")
    # within a count, the bigger first-preference total was elected first (the VEC's own listing)
    fp = q("SELECT election_id, contest_id, \"column\" AS name, progressive_total AS fp FROM lc_dop WHERE count_no = 1")
    el = el.merge(fp, how='left', on=['election_id', 'contest_id', 'name'])
    rows = []
    for (eid, cid), g in el.groupby(['election_id', 'contest_id'], sort=False):
        for order, r in enumerate(g.sort_values(['count_no', 'fp'], ascending=[True, False]).itertuples(), start=1):
            c = who(eid, cid, r.name)
            rows.append({'election_id': eid, 'contest_id': cid, 'name': r.name, 'party': c.party if c else 'OTH', 'party_name': c.party_name if c else '', 'grp': c.grp if c else '', 'order_elected': order, 'count_no': int(r.count_no)})
    sizes['lc_result'] = write(out, 'lc_result', pd.DataFrame(rows))
    dop = q("SELECT election_id, contest_id, count_no, description, \"column\" AS name, value FROM lc_dop WHERE value IS NOT NULL AND value <> 0 AND \"column\" <> 'TOTAL'")
    m = dop.description.str.extract(r'^(Exclusion|Surplus) of (.+?), ([\d,]+) ballot papers')
    m2 = dop.description.str.extract(r'^(Exclusion|Surplus) of (.+?)(?: \(|$)')
    dop['kind'] = m[0].fillna(m2[0]).str.lower(); dop['from_name'] = m[1].fillna(m2[1])
    dop = dop[dop.kind.notna() & (dop.name != dop.from_name)]
    fl = dop.groupby(['election_id', 'contest_id', 'kind', 'from_name', 'name'], as_index=False).value.sum()
    fl = fl[fl.value > 0]
    def party_of(r, col):
        c = who(r.election_id, r.contest_id, getattr(r, col)); return c.party if c else ('EXH' if getattr(r, col) == 'Exhausted' else 'OTH')
    fl['from_party'] = [party_of(r, 'from_name') for r in fl.itertuples()]
    fl['to_party'] = [party_of(r, 'name') for r in fl.itertuples()]
    fl = fl.rename(columns={'name': 'to_name'})
    sizes['lc_flows'] = write(out, 'lc_flows', fl[['election_id', 'contest_id', 'kind', 'from_name', 'from_party', 'to_name', 'to_party', 'value']])
    for k, v in sizes.items():
        print(f'{k:24s} {v/1024:8.1f} KB')
    print(q('SELECT election_id, COUNT(*) n, SUM(formal) formal FROM lc_contests GROUP BY 1').to_string(index=False))
    r = pd.DataFrame(rows); print(r.groupby(['election_id', 'party']).size().unstack(fill_value=0).to_string())


if __name__ == '__main__':
    main(*sys.argv[1:3])
