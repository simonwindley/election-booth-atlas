"""The economy, by party and by group: does local economic change move any party's vote, or any group's?

Same design as src.econ_voting (venue swings against the rest of their electorate; discover on 2014/2018
state + 2016/2019 federal, confirm on 2022 state + 2022/2025 federal), with two extensions:
  1. outcomes for each party's first-preference change (Labor, Coalition, Greens, One Nation, everyone else),
     as well as the governing party's;
  2. interactions with the venue's 2016 census profile (renters, mortgage holders, over-65s, 18-34s,
     degree holders, born overseas, low-income households, unemployment): does the effect of a local
     change differ by who lives there?
A result counts only if it is found on the discovery elections (|t| >= 2.5) and holds on the confirmation
elections with the same sign (|t| >= 2). The identical search is run with each measure taken from the wrong
(previous) term, which cannot have caused the swing, to show how many 'results' chance alone produces.

Usage: python3 -m src.econ_groups [db] [out_json]
"""
import sys, os, re, json, gzip, sqlite3, warnings
import numpy as np, pandas as pd
from .econ_voting import GOV, DISCOVER, CONFIRM, ROOT, add_sa2, salm, rents, lxr_sites, measures
warnings.filterwarnings('ignore')

PARTY = {'ALP': ['ALP'], 'COAL': ['LIB', 'NAT', 'LNP', 'CLP'], 'GRN': ['GRN'], 'ONP': ['ONP']}
DEMOG = ['rented', 'owned_mortgage', 'age_65_plus', 'adults_18_34', 'bachelor_or_higher', 'born_overseas', 'income_household_under_1000', 'unemployment_rate']


def panel(con):
    v = pd.read_sql("SELECT venue_id, lat, lon, election_id, date, contest_id, booth_id, party, votes FROM venue_party_share WHERE booth_type = 'ordinary'", con)
    v['share'] = v.votes / v.groupby(['venue_id', 'election_id']).votes.transform('sum')
    grp = {p: k for k, ps in PARTY.items() for p in ps}
    v['g'] = v.party.map(grp).fillna('OTH')
    s = v.pivot_table(index=['venue_id', 'election_id'], columns='g', values='share', aggfunc='sum').fillna(0)
    rows = []
    for eid, (prev, gov) in GOV.items():
        a = v[v.election_id == eid]
        meta = a.groupby('venue_id').agg(lat=('lat', 'first'), lon=('lon', 'first'), contest_id=('contest_id', 'first'), date=('date', 'first'), votes=('votes', 'sum'))
        prev_date = v[v.election_id == prev].date.iloc[0]
        now = s.xs(eid, level='election_id'); was = s.xs(prev, level='election_id')
        both = meta.index.intersection(was.index).intersection(now.index)
        d = meta.loc[both].copy(); d['election_id'] = eid; d['prev_date'] = prev_date
        for k in list(PARTY) + ['OTH']:
            d[f'sw_{k}'] = 100 * (now.reindex(both)[k] if k in now else 0) - 100 * (was.reindex(both)[k] if k in was else 0)
        gk = 'COAL' if gov[0] in ('LIB', 'NAT', 'LNP') else 'ALP'
        d['sw_GOV'] = d[f'sw_{gk}']
        rows.append(d.reset_index())
    p = pd.concat(rows, ignore_index=True); p = p[p.votes >= 200]
    for k in ['GOV'] + list(PARTY) + ['OTH']:
        def dev(g, c=f'sw_{k}'):
            w = g.votes; return g[c] - ((g[c] * w).sum() - g[c] * w) / (w.sum() - w).replace(0, np.nan)
        p[f'dev_{k}'] = p.groupby(['election_id', 'contest_id'], group_keys=False).apply(dev)
    return p


def census_2016(con):
    """2016 census profile for each venue, from the federal booths held there (catchment-apportioned SA1s)"""
    d = json.load(gzip.open(os.path.join(ROOT, 'data', 'national', 'census_booths', '2016_vic.json.gz')))
    cols = d['cols']; idx = [cols.index(c) for c in DEMOG]
    vb = pd.read_sql("SELECT DISTINCT venue_id, election_id, booth_id FROM venue_party_share WHERE election_id IN ('fed2016','fed2019','fed2022') AND booth_type = 'ordinary'", con)
    rows = []
    for r in vb.itertuples():
        vals = d['booths'].get(r.election_id, {}).get(r.booth_id)
        if vals: rows.append([r.venue_id] + [vals[i] for i in idx])
    c = pd.DataFrame(rows, columns=['venue_id'] + DEMOG)
    return c.groupby('venue_id').mean()


def ols_cl(y, X, cl):
    m = np.isfinite(y) & np.all(np.isfinite(X), axis=1); y, X, cl = y[m], X[m], cl[m]
    if len(y) < 200:
        return None
    X = np.column_stack([np.ones(len(y)), X])
    XtX_inv = np.linalg.pinv(X.T @ X); b = XtX_inv @ X.T @ y; u = y - X @ b
    meat = np.zeros((X.shape[1], X.shape[1]))
    for c in np.unique(cl):
        s = X[cl == c].T @ u[cl == c]; meat += np.outer(s, s)
    V = XtX_inv @ meat @ XtX_inv; se = np.sqrt(np.diag(V))
    return b, se, len(y)


def z(x):
    x = x.astype(float); return (x - np.nanmean(x)) / np.nanstd(x)


def run(d, mcols, outcomes, demog):
    """main effects for every outcome x measure, and interactions with each census group, on both sample splits"""
    res = []
    for o in outcomes:
        for m in mcols:
            for kind, zc in [('main', None)] + [('x', g) for g in demog]:
                row = {'outcome': o, 'measure': m, 'group': zc}
                for split, ids in [('discover', DISCOVER), ('confirm', CONFIRM)]:
                    s = d[d.election_id.isin(ids)]
                    x = z(s[m].values)
                    if zc is None:
                        X = x[:, None]
                    else:
                        g = z(s[zc].values); X = np.column_stack([x, g, x * g])
                    r = ols_cl(s[f'dev_{o}'].values, X, (s.election_id + '|' + s.contest_id).values)
                    if r is None:
                        row[split] = None; continue
                    b, se, n = r; k = 1 if zc is None else 3
                    row[split] = {'b': round(float(b[k]), 3), 'se': round(float(se[k]), 3), 't': round(float(b[k] / se[k]), 2), 'n': int(n)}
                dd, cc = row.get('discover'), row.get('confirm')
                row['found'] = bool(dd and abs(dd['t']) >= 2.5)
                row['holds'] = bool(row['found'] and cc and abs(cc['t']) >= 2 and np.sign(cc['b']) == np.sign(dd['b']))
                res.append(row)
    return res


def main(db=os.path.join(ROOT, 'data', 'elections.sqlite'), out=os.path.join(ROOT, 'data', 'analysis', 'econ_groups.json')):
    con = sqlite3.connect(db)
    p = add_sa2(panel(con)); d = measures(p, salm(), rents(), lxr_sites())
    d = d.merge(census_2016(con), left_on='venue_id', right_index=True, how='left')
    mcols = [c for c in d.columns if re.match(r'(unemp|rent|lxr)_', c)]
    outcomes = ['GOV'] + list(PARTY) + ['OTH']
    real = run(d, mcols, outcomes, DEMOG)
    # the same search with each measure from the previous term (cannot cause this term's swing)
    nxt = {prev: e for e, (prev, _) in GOV.items()}
    k = d[['venue_id', 'election_id'] + mcols].copy(); k['election_id'] = k.election_id.map(nxt); k = k.dropna(subset=['election_id'])
    dp = d.drop(columns=mcols).merge(k, on=['venue_id', 'election_id'], how='inner')
    placebo = run(dp, mcols, outcomes, DEMOG)
    tally = lambda rs: {'tests': len(rs), 'found': sum(r['found'] for r in rs), 'holds': sum(r['holds'] for r in rs),
                        'found_main': sum(r['found'] for r in rs if r['group'] is None), 'holds_main': sum(r['holds'] for r in rs if r['group'] is None)}
    out_d = {'design': {'outcomes': outcomes, 'measures': mcols, 'groups': DEMOG, 'discover': DISCOVER, 'confirm': CONFIRM,
                        'rule': 'found: |t| >= 2.5 on discovery elections; holds: then |t| >= 2 with the same sign on confirmation elections',
                        'census': '2016 census, catchment-apportioned to each venue from the federal booths held there'},
             'observations': int(len(d)), 'with_census': int(d[DEMOG[0]].notna().sum()),
             'real': tally(real), 'placebo_previous_term': tally(placebo),
             'results': [r for r in real if r['found'] or r['group'] is None],
             'placebo_hits': [r for r in placebo if r['holds']]}
    out_d = json.loads(json.dumps(out_d).replace('NaN', 'null'))   # browsers can't parse NaN
    json.dump(out_d, open(out, 'w'), indent=1)
    print('real', out_d['real'], '\nplacebo', out_d['placebo_previous_term'], '\nobs', out_d['observations'], 'with census', out_d['with_census'])
    f = lambda q: f"{q['b']:+.2f} (t {q['t']:+.1f})" if q else '–'
    print('\nmain effects with |t|>=2 anywhere:')
    for r in real:
        if r['group'] is None and ((r['discover'] and abs(r['discover']['t']) >= 2) or (r['confirm'] and abs(r['confirm']['t']) >= 2)):
            print(f"  {r['outcome']:4s} {r['measure']:11s} discover {f(r['discover']):16s} confirm {f(r['confirm'])}")
    print('\nfound on discovery (and whether it holds):')
    for r in real:
        if r['found']:
            print(f"  {'HOLDS' if r['holds'] else '     '} {r['outcome']:4s} {r['measure']:11s} x {str(r['group']):28s} discover {f(r['discover']):16s} confirm {f(r['confirm'])}")
    print('\nplacebo hits that held:', [(r['outcome'], r['measure'], r['group']) for r in out_d['placebo_hits']])


if __name__ == '__main__':
    main(*sys.argv[1:3])
