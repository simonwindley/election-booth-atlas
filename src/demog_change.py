"""Demographic change and the vote: does a booth area's changing population move its vote, and for which groups?
(the demographic_change question in analysis/questions.json)

Data: every Victorian polling place (venue) used at state elections 2006-2022 and federal elections 2004-2025, with
its ordinary-booth first preferences grouped ALP / COAL / GRN / ONP / OTH (minor parties and independents), and the
census profile of its catchment on fixed 2022 geography for 2006, 2011, 2016 and 2021 (src.load_sa1_census,
src.load_cd_census), linearly interpolated to each election date (no extrapolation past the 2021 Census).

Three readings
  1  gradients (cross-section): at each election, a party's share across polling places against the shares of eight
     groups in the area (points of vote per point of group share, all eight together). How these move from election
     to election is conversion: the same kinds of places voting differently (e.g. the education divide widening).
  2  composition (panel): the change in a party's share at the same polling place between consecutive elections of
     a level, against the change in the area's population mix, with the statewide swing and each election's
     conversion (starting levels x transition) taken out. The coefficient is what one point more of a group does to
     the vote when the group grows in a place; set beside the cross-sectional gradient it says whether newcomers vote
     like the people of that kind already there.
  3  decomposition: each district's change in a party's vote, 2006 -> 2022 (state), split into statewide swing,
     composition (population change x the composition coefficients) and the rest (conversion plus local factors).

Ecological caveat: these are areas, not people. A gradient is how places differ, not how individuals vote.

Usage: python3 -m src.demog_change  -> data/analysis/demog_change.json
"""
import os, json, gzip
from collections import defaultdict
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUPS = ['ALP', 'COAL', 'GRN', 'ONP', 'OTH']
X = ['adults_18_34', 'adults_55_plus', 'bachelor_or_higher', 'certificate', 'other_language_home', 'religion_no_religion_so_described', 'rented', 'flat_apartment']
XL = {'adults_18_34': 'Adults 18-34', 'adults_55_plus': 'Adults 55+', 'bachelor_or_higher': 'Degree', 'certificate': 'Trade certificate',
      'other_language_home': 'Other language at home', 'religion_no_religion_so_described': 'No religion', 'rented': 'Renting', 'flat_apartment': 'Flats and apartments'}
CENSUS_T = {'2006': 2006.6, '2011': 2011.6, '2016': 2016.6, '2021': 2021.6}


def rd(name):
    d = json.load(gzip.open(os.path.join(ROOT, f'site/data/{name}.json.gz')))
    return pd.DataFrame(d['rows'], columns=d['cols'])


def g5(p):
    return 'COAL' if p in ('LIB', 'NAT') else p if p in ('ALP', 'GRN', 'ONP') else 'OTH'


def venue_shares():
    E = rd('elections'); B = rd('booths'); F = rd('fp'); K = rd('candidates')
    gen = E[E.election_id.str.match(r'^(vic|fed)\d{4}$') & (E.election_id != 'vic2023n') & (E.election_id >= 'fed2004')]
    gen = gen[~gen.election_id.isin(['vic1999', 'vic2002'])]
    date = {e: pd.Timestamp(d) for e, d in zip(gen.election_id, gen.date)}
    B = B[B.election_id.isin(date) & B.booth_type.eq('ordinary') & B.venue_id.notna()]
    F = F[F.candidate_id != 'INFORMAL'].merge(B[['election_id', 'booth_id', 'venue_id', 'contest_id']], on=['election_id', 'booth_id'])
    F = F.merge(K[['election_id', 'candidate_id', 'party']], on=['election_id', 'candidate_id'], how='left')
    F['g'] = F.party.map(g5).fillna('OTH')
    V = F.pivot_table(index=['election_id', 'venue_id'], columns='g', values='votes', aggfunc='sum', fill_value=0)
    for g in GROUPS:
        if g not in V:
            V[g] = 0
    V['tot'] = V[GROUPS].sum(axis=1)
    V = V[V.tot >= 200].copy()
    for g in GROUPS:
        V[g] = 100 * V[g] / V['tot']
    V = V.reset_index()
    # the venue's district at that election (most of its votes)
    dist = F.groupby(['election_id', 'venue_id', 'contest_id']).votes.sum().reset_index().sort_values('votes').drop_duplicates(['election_id', 'venue_id'], keep='last')
    V = V.merge(dist[['election_id', 'venue_id', 'contest_id']], on=['election_id', 'venue_id'])
    V['t'] = V.election_id.map(lambda e: date[e].year + (date[e].dayofyear - 1) / 365.25)
    V['level'] = V.election_id.str[:3]
    return V


def census_at(V):
    C = {y: json.load(open(os.path.join(ROOT, f'raw/abs/sa1_census_{y}.json')))['booths'] for y in CENSUS_T}
    ys = sorted(CENSUS_T, key=CENSUS_T.get)
    rows = []
    for v, t in zip(V.venue_id, V.t):
        t = min(max(t, CENSUS_T['2006']), CENSUS_T['2021'])
        a = max(y for y in ys if CENSUS_T[y] <= t); b = min(y for y in ys if CENSUS_T[y] >= t)
        w = 0 if a == b else (t - CENSUS_T[a]) / (CENSUS_T[b] - CENSUS_T[a])
        ca, cb = C[a].get(v), C[b].get(v)
        if not ca or not cb:
            rows.append({k: np.nan for k in X}); continue
        rows.append({k: (100 * ((1 - w) * ca[k] + w * cb[k]) if ca.get(k) is not None and cb.get(k) is not None else np.nan) for k in X})
    return pd.concat([V.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def ols(y, Xm, cluster=None):
    Xm = np.column_stack([np.ones(len(y)), Xm])
    b, *_ = np.linalg.lstsq(Xm, y, rcond=None)
    e = y - Xm @ b
    XtX_inv = np.linalg.pinv(Xm.T @ Xm)
    if cluster is not None:
        meat = np.zeros((Xm.shape[1], Xm.shape[1]))
        for c in np.unique(cluster):
            i = cluster == c; s = Xm[i].T @ e[i]; meat += np.outer(s, s)
        G = len(np.unique(cluster)); n, k = Xm.shape
        V = XtX_inv @ meat @ XtX_inv * G / (G - 1) * (n - 1) / (n - k)
    else:
        V = XtX_inv * (e @ e) / (len(y) - Xm.shape[1])
    return b, np.sqrt(np.diag(V)), 1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))


def gradients(D):
    out = {}
    for e, g in D.groupby('election_id'):
        g = g.dropna(subset=X)
        out[e] = {}
        for p in GROUPS:
            if g[p].mean() < 1:
                continue
            b, se, r2 = ols(g[p].values, g[X].values, pd.factorize(g.contest_id)[0])
            out[e][p] = {'r2': round(float(r2), 3), 'n': int(len(g)), 'mean': round(float(g[p].mean()), 2),
                         **{XL[k]: {'pts': round(float(b[i + 1]), 3), 'se': round(float(se[i + 1]), 3)} for i, k in enumerate(X)}}
    return out


def composition(D):
    """first differences at the same venue between consecutive elections of a level"""
    out = {}
    for lv, es in (('state', ['vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022']), ('federal', ['fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022'])):
        P = []
        for a, b in zip(es, es[1:]):
            A = D[D.election_id == a].set_index('venue_id'); Bb = D[D.election_id == b].set_index('venue_id')
            j = A.index.intersection(Bb.index)
            d = pd.DataFrame({'venue_id': j, 'tr': f'{a}->{b}', 'contest_id': Bb.loc[j, 'contest_id'].values})
            for p in GROUPS:
                d['d_' + p] = Bb.loc[j, p].values - A.loc[j, p].values
            for k in X:
                d['dx_' + k] = Bb.loc[j, k].values - A.loc[j, k].values
                d['x0_' + k] = A.loc[j, k].values
            P.append(d)
        P = pd.concat(P).dropna()
        trs = sorted(P.tr.unique())
        res = {'transitions': trs, 'venue_pairs': int(len(P)), 'by_party': {}}
        for p in GROUPS:
            if P['d_' + p].abs().mean() < 0.3:
                continue
            cols = [P['dx_' + k].values for k in X]
            names = ['dx_' + k for k in X]
            for t in trs[1:]:                                   # transition effects (statewide swing); the first is the intercept
                cols.append((P.tr == t).astype(float).values); names.append('tr_' + t)
            for t in trs:                                       # conversion: each transition's own pull on starting levels
                for k in X:
                    cols.append(((P.tr == t) * P['x0_' + k]).values); names.append(f'conv_{t}_{k}')
            b, se, r2 = ols(P['d_' + p].values, np.column_stack(cols), pd.factorize(P.contest_id + P.tr)[0])
            res['by_party'][p] = {'r2': round(float(r2), 3),
                                  'composition': {XL[k]: {'pts': round(float(b[i + 1]), 3), 'se': round(float(se[i + 1]), 3)} for i, k in enumerate(X)}}
        out[lv] = res
        out[lv]['_panel'] = P
    return out


def decompose(D, comp, a='vic2006', b='vic2022'):
    """district change a -> b (2022 districts, venues in both): statewide swing + composition + the rest"""
    A = D[D.election_id == a].set_index('venue_id'); Bb = D[D.election_id == b].set_index('venue_id')
    j = A.index.intersection(Bb.index)
    d = pd.DataFrame({'venue_id': j, 'contest_id': Bb.loc[j, 'contest_id'].values, 'w': Bb.loc[j, 'tot'].values})
    for k in X:
        d['dx_' + k] = Bb.loc[j, k].values - A.loc[j, k].values
    for p in GROUPS:
        d['d_' + p] = Bb.loc[j, p].values - A.loc[j, p].values
    d = d.dropna()
    names = rd('contests').drop_duplicates(['contest_id']).set_index('contest_id').contest_name
    out = {'from': a, 'to': b, 'venues': int(len(d)), 'statewide': {}, 'districts': []}
    for p in GROUPS:
        if p not in comp['state']['by_party']:
            continue
        beta = np.array([comp['state']['by_party'][p]['composition'][XL[k]]['pts'] for k in X])
        d['c_' + p] = d[['dx_' + k for k in X]].values @ beta
        out['statewide'][p] = {'change': round(float(np.average(d['d_' + p], weights=d.w)), 2), 'composition': round(float(np.average(d['c_' + p], weights=d.w)), 2)}
    for cid, g in d.groupby('contest_id'):
        r = {'seat': names.get(cid, cid), 'venues': int(len(g)), 'pop_change': {XL[k]: round(float(np.average(g['dx_' + k], weights=g.w)), 1) for k in X}}
        for p in out['statewide']:
            ch = float(np.average(g['d_' + p], weights=g.w)); co = float(np.average(g['c_' + p], weights=g.w))
            r[p] = {'change': round(ch, 2), 'statewide': out['statewide'][p]['change'], 'composition': round(co, 2),
                    'local': round(ch - out['statewide'][p]['change'] - (co - out['statewide'][p]['composition']), 2), 'composition_rel': round(co - out['statewide'][p]['composition'], 2)}
        out['districts'].append(r)
    return out


BIV = ['other_language_home', 'bachelor_or_higher', 'certificate', 'adults_55_plus', 'rented', 'religion_no_religion_so_described']


def bivariate(D):
    """one group at a time: points of a party's vote per 10 points more of the group in the area, by election"""
    out = {}
    for lv, pre in (('state', 'vic'), ('federal', 'fed')):
        out[lv] = {}
        es = sorted(e for e in D.election_id.unique() if e.startswith(pre))
        for k in BIV:
            out[lv][XL[k]] = {}
            for p in ('ALP', 'COAL', 'GRN'):
                row = []
                for e in es:
                    g = D[D.election_id == e].dropna(subset=[k])
                    b, se, _ = ols(g[p].values, g[[k]].values, pd.factorize(g.contest_id)[0])
                    row.append({'e': e, 'year': int(e[3:]), 'pts': round(10 * float(b[1]), 2), 'se': round(10 * float(se[1]), 2)})
                out[lv][XL[k]][p] = row
    return out


def holdout(comp):
    """fit composition on the earlier state transitions, predict the 2018->2022 polling-place swings (beyond statewide)"""
    P = comp['state']['_panel']; test = 'vic2018->vic2022'
    tr, te = P[P.tr != test], P[P.tr == test]
    out = {}
    for p in ('ALP', 'COAL', 'GRN'):
        trs = sorted(tr.tr.unique()); cols = [tr['dx_' + k].values for k in X]
        for t in trs[1:]:
            cols.append((tr.tr == t).astype(float).values)
        for t in trs:
            for k in X:
                cols.append(((tr.tr == t) * tr['x0_' + k]).values)
        b, _, _ = ols(tr['d_' + p].values, np.column_stack(cols))
        y = te['d_' + p].values - te['d_' + p].mean(); pr = te[['dx_' + k for k in X]].values @ b[1:1 + len(X)]; pr -= pr.mean()
        out[p] = {'r2': round(float(1 - np.mean((y - pr) ** 2) / np.mean(y ** 2)), 3), 'corr': round(float(np.corrcoef(pr, y)[0, 1]), 3), 'venues': int(len(te))}
    return out


def main():
    D = census_at(venue_shares())
    res = {'about': __doc__.split('\n\n')[0], 'groups_x': [XL[k] for k in X], 'venue_elections': int(D.dropna(subset=X).shape[0])}
    res['gradients'] = gradients(D)
    comp = composition(D)
    res['composition'] = {lv: {k: v for k, v in c.items() if k != '_panel'} for lv, c in comp.items()}
    res['bivariate'] = bivariate(D)
    res['holdout_2018_2022'] = holdout(comp)
    res['decomposition_2006_2022'] = decompose(D, comp, 'vic2006', 'vic2022')
    res['decomposition_2018_2022'] = decompose(D, comp, 'vic2018', 'vic2022')
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/demog_change.json'), 'w'), indent=1)
    # console summary
    for lv in ('state', 'federal'):
        print(f'== composition ({lv}, {comp[lv]["venue_pairs"]} venue pairs): points of party vote per point of population change')
        print('   ' + ' '.join(f'{XL[k][:12]:>13s}' for k in X))
        for p, r in comp[lv]['by_party'].items():
            print(f'{p:5s}' + ' '.join(f"{r['composition'][XL[k]]['pts']:+6.2f}({r['composition'][XL[k]]['se']:.2f})" for k in X))
    for p in ('ALP', 'COAL', 'GRN'):
        print(f'== gradient ({p}), state:', {e: res['gradients'][e][p][XL['bachelor_or_higher']]['pts'] for e in ('vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022')})
    print('== statewide 2006->2022 at common venues:', res['decomposition_2006_2022']['statewide'])


if __name__ == '__main__':
    main()
