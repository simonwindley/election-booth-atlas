"""Sex of leaders, candidates and members, and the vote (the leader_sex question in analysis/questions.json).

Data: every major-party candidate (ALP, LIB, NAT, GRN) at Victorian state (1999-2022) and federal (2004-2025, Victorian
divisions) general elections. Sex: candidates' given names through a name dictionary (gender_guesser), with
hand corrections for public figures and ambiguous names in raw/reference/candidate_sex_overrides.json; anyone still
ambiguous is left out, never guessed. Leaders: raw/reference/party_leaders.json.

Questions and designs
  1  candidate sex, seat level: party primary in a seat relative to the party's statewide primary that election,
     with seat x party fixed effects (so the comparison is a party's female vs male candidates in the same seat over
     time) and party x election effects (the statewide mood), controlling for the candidate being the sitting member
     and for a first-term member. Standard errors clustered by seat.
  2  leader sex x candidate sex: does a female candidate do better or worse when her party has a female leader?
     Leader sex itself is absorbed by party x election (every seat shares it); only the interaction is identified,
     from ALP 2010 (Gillard), Greens 2013 (Milne), Victorian Greens 2018 and 2022 (Ratnam).
  3  members: the same, restricted to sitting members (does a female leader change a member's personal vote, and does
     it differ for female and male members?)
  4  cohorts, booth level: within a seat, does a female candidate do relatively better in booths with particular
     people (older, religious, overseas-born, degree-educated, ...)? Booth share minus seat share, regressed on census
     indicators interacted with party x election (how each party's vote normally varies across booths) plus the same
     indicators x female candidate.
  5  leader switches, booth level: party swing between consecutive elections by booth (same venue), regressed on
     census indicators, transition by transition; the transitions into and out of a female leader compared with the
     party's other transitions. Descriptive: one leader per switch.

Usage: python3 -m src.sex_effects  -> data/analysis/sex_effects.json
"""
import os, re, json, gzip
from collections import defaultdict
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTIES = ('ALP', 'LIB', 'NAT', 'GRN')
NAME_RULES = {'jess': 'F', 'jo': 'F', 'jackie': 'F', 'lesley': 'F', 'lauren': 'F', 'courtney': 'F', 'maree': 'F', 'robyn': 'F', 'lynn': 'F', 'gail': 'F',
              'gayle': 'F', 'kat': 'F', 'steph': 'F', 'ros': 'F', 'bec': 'F', 'libby': 'F', 'mal': 'M', 'norm': 'M', 'les': 'M',
              # ambiguous: left out unless the person is listed in the overrides
              'chris': None, 'sam': None, 'kim': None, 'robin': None, 'pat': None, 'jordan': None, 'leslie': None, 'ashley': None, 'jamie': None,
              'dale': None, 'kerry': None, 'shannon': None, 'ged': None, 'alex': None, 'jude': None, 'dallas': None, 'tully': None, 'avery': None,
              'jy': None, 'loki': None, 'shelby': None, 'brook': None, 'blair': None, 'leigh': None, 'charlie': None, 'frankie': None, 'riley': None,
              'taylor': None, 'jessie': None, 'drew': None, 'casey': None, 'morgan': None, 'sydney': None, 'terry': None, 'lindsay': None}
CENSUS = ['age_65_plus', 'bachelor_or_higher', 'other_language_home', 'religion_christianity_total', 'occupation_technicians_and_trades_workers', 'rented']
CLABEL = {'age_65_plus': 'aged 65+', 'adults_18_34': 'adults 18-34', 'bachelor_or_higher': 'degree', 'born_overseas': 'born overseas',
          'other_language_home': 'other language at home', 'religion_christianity_total': 'Christian', 'religion_no_religion_so_described': 'no religion',
          'occupation_technicians_and_trades_workers': 'trades workers', 'owned_outright': 'home owned outright', 'rented': 'renting'}


def rd(name):
    d = json.load(gzip.open(os.path.join(ROOT, f'site/data/{name}.json.gz')))
    return pd.DataFrame(d['rows'], columns=d['cols'])


def sex_classifier():
    import gender_guesser.detector as gd
    D = gd.Detector(case_sensitive=False)
    O = json.load(open(os.path.join(ROOT, 'raw/reference/candidate_sex_overrides.json')))
    person = {n: 'F' for n in O['F']}; person.update({n: 'M' for n in O['M']})

    def f(given, surname):
        given = given if isinstance(given, str) else ''; surname = surname if isinstance(surname, str) else ''
        key = f'{given} {surname}'.lower().strip()
        if key in person:
            return person[key]
        g = re.sub(r'["()]', ' ', given or '').strip().split()
        if not g:
            return None
        first = g[0].lower().rstrip('.')
        if first in NAME_RULES:
            return NAME_RULES[first]
        if len(first) <= 2:
            return None
        return {'male': 'M', 'female': 'F', 'mostly_male': 'M', 'mostly_female': 'F'}.get(D.get_gender(g[0]))
    return f


def seat_table():
    E = rd('elections'); C = rd('contests'); K = rd('candidates'); V = rd('contest_cand')
    gen = E[E.election_id.str.match(r'^(vic|fed)\d{4}$') & (E.election_id != 'vic2023n')]
    lvl = dict(zip(gen.election_id, gen.level)); date = dict(zip(gen.election_id, gen.date))
    C = C[C.election_id.isin(lvl)]
    K = K[K.election_id.isin(lvl)].merge(V, on=['election_id', 'contest_id', 'candidate_id']).merge(C[['election_id', 'contest_id', 'contest_name']], on=['election_id', 'contest_id'])
    tot = K.groupby(['election_id', 'contest_id']).votes.transform('sum')
    K['share'] = K.votes / tot
    sx = sex_classifier()
    K['sex'] = [sx(g, s) for g, s in zip(K.given_name, K.surname)]
    K['level'] = K.election_id.map(lvl); K['date'] = K.election_id.map(date)
    K['who'] = [f"{g.split()[0].lower() if isinstance(g, str) and g.split() else ''} {s.lower() if isinstance(s, str) else ''}" for g, s in zip(K.given_name, K.surname)]
    # sitting member: elected in the same seat (name) at the previous general election of the same level; first term
    order = {l: sorted(e for e in lvl if lvl[e] == l) for l in ('state', 'federal')}
    prev = {e: (order[lvl[e]][order[lvl[e]].index(e) - 1] if order[lvl[e]].index(e) else None) for e in lvl}
    won = {(r.election_id, r.contest_name, r.who) for r in K[K.elected == 1].itertuples()}
    K['sitting'] = [(prev[e], c, w) in won for e, c, w in zip(K.election_id, K.contest_name, K.who)]
    K['first_term'] = [s and not ((prev.get(prev[e]) if prev[e] else None), c, w) in won for s, e, c, w in zip(K.sitting, K.election_id, K.contest_name, K.who)]
    S = K[K.party.isin(PARTIES)].copy()
    # statewide (Victorian) party share at that election = votes / all formal votes
    state_tot = K.groupby('election_id').votes.sum()
    pshare = S.groupby(['election_id', 'party']).votes.sum() / state_tot.reindex(S.groupby(['election_id', 'party']).votes.sum().index.get_level_values(0)).values
    S['party_state'] = [pshare[(e, p)] for e, p in zip(S.election_id, S.party)]
    S['rel'] = 100 * (S.share - S.party_state)
    L = json.load(open(os.path.join(ROOT, 'raw/reference/party_leaders.json')))
    S['leader_sex'] = [L.get(e, {}).get(p, [None, None])[1] for e, p in zip(S.election_id, S.party)]
    S['leader'] = [L.get(e, {}).get(p, [None, None])[0] for e, p in zip(S.election_id, S.party)]
    S['seat'] = S.level + ':' + S.contest_name
    return K, S


def coef(m, name):
    t = m.tidy()
    if name not in t.index:
        return None
    r = t.loc[name]
    return {'pts': round(float(r['Estimate']), 2), 'lo': round(float(r['2.5%']), 2), 'hi': round(float(r['97.5%']), 2), 'p': round(float(r['Pr(>|t|)']), 3)}


def feols(fml, d):
    import pyfixest as pf
    return pf.feols(fml, data=d, vcov={'CRV1': 'seat'})


def candidate_models(S):
    d = S[S.sex.notna()].copy()
    d['female'] = (d.sex == 'F').astype(int)
    d['fem_leader'] = (d.leader_sex == 'F').astype(int)
    d['fxl'] = d.female * d.fem_leader
    d['sitting'] = d.sitting.astype(int); d['first_term'] = d.first_term.astype(int)
    d['pe'] = d.party + '_' + d.election_id; d['sp'] = d.seat + '_' + d.party
    out = {'n_candidates': int(len(d)), 'n_unclassified': int(S.sex.isna().sum()),
           'female_share': {p: {lv: round(float(d[(d.party == p) & (d.level == lv)].female.mean()), 3) for lv in ('state', 'federal')} for p in PARTIES},
           'female_share_by_election': {e: round(float(g.female.mean()), 3) for e, g in d.groupby('election_id')},
           'female_share_by_party_election': {f'{p}_{e}': round(float(g.female.mean()), 3) for (p, e), g in d.groupby(['party', 'election_id'])}}
    d = d[d.groupby('sp').sp.transform('size') >= 2]
    m = feols('rel ~ female + sitting + first_term | pe + sp', d)
    out['female_candidate'] = coef(m, 'female'); out['sitting_member'] = coef(m, 'sitting'); out['first_term'] = coef(m, 'first_term'); out['n_model'] = int(m._N)
    # without seat effects: the raw gap (where women are preselected matters)
    m0 = feols('rel ~ female + sitting + first_term | pe', d); out['female_candidate_no_seat_fe'] = coef(m0, 'female')
    out['by_party'] = {}
    for p in PARTIES:
        dp = d[d.party == p]
        mp = feols('rel ~ female + sitting + first_term | pe + sp', dp)
        out['by_party'][p] = (coef(mp, 'female') or {}) | {'n': int(mp._N), 'female_n': int(dp.female.sum())}
        out['by_party'][p]['raw_gap_no_seat_fe'] = coef(feols('rel ~ female + sitting + first_term | pe', dp), 'female')
    out['by_level'] = {lv: (coef(feols('rel ~ female + sitting + first_term | pe + sp', d[d.level == lv]), 'female') or {}) for lv in ('state', 'federal')}
    out['non_incumbents'] = coef(feols('rel ~ female | pe + sp', d[d.sitting == 0]), 'female')
    m2 = feols('rel ~ female + fxl + sitting + first_term | pe + sp', d)
    out['female_candidate_x_female_leader'] = coef(m2, 'fxl'); out['female_candidate_male_leader'] = coef(m2, 'female')
    out['by_female_leader'] = {}
    for p, e in (('ALP', 'fed2010'), ('GRN', 'fed2013'), ('GRN', 'vic2018'), ('GRN', 'vic2022')):
        x = d.copy(); x['case'] = ((x.party == p) & (x.election_id == e)).astype(int) * x.female
        out['by_female_leader'][f'{p} {e}'] = coef(feols('rel ~ female + case + sitting + first_term | pe + sp', x), 'case')
    dg = d[d.party == 'GRN']
    out['greens_female_x_female_leader'] = coef(feols('rel ~ female + fxl + sitting | pe + sp', dg), 'fxl')
    # sitting members: personal vote relative to the party statewide, member x seat effects; leader sex vs member sex
    dm = d[d.sitting == 1].copy(); dm['ms'] = dm.sp + '_' + dm.who
    dm = dm[dm.groupby('ms').ms.transform('size') >= 2]
    m4 = feols('rel ~ fem_leader + fxl + first_term | ms + election_id', dm)
    out['members'] = {'female_leader_male_member': coef(m4, 'fem_leader'), 'extra_for_female_member': coef(m4, 'fxl'), 'n': int(m4._N),
                      'members_with_female_leader_obs': int(dm.fem_leader.sum()),
                      'note': 'Within the same member and seat over time; election effects only (a party x election effect would absorb the leader), so the leader term mixes the leader with that party-election.'}
    return out, d


def booth_cohorts(S, K):
    """within-seat booth deviations x census, interacted with candidate sex"""
    B = rd('booths'); F = rd('fp')
    B = B[B.booth_type.eq('ordinary') & B.venue_id.notna()]
    F = F.merge(B[['election_id', 'booth_id', 'contest_id', 'venue_id']], on=['election_id', 'booth_id'])
    tot = F.groupby(['election_id', 'booth_id']).votes.transform('sum')
    F = F[tot >= 200]; F['bshare'] = F.votes / tot[tot >= 200]
    s = S[S.sex.notna()][['election_id', 'contest_id', 'candidate_id', 'party', 'sex', 'share', 'seat', 'level', 'leader_sex']]
    F = F.merge(s, on=['election_id', 'contest_id', 'candidate_id'])
    F['dev'] = 100 * (F.bshare - F.share)
    cen = {}
    for y in ('2006', '2011', '2016', '2021'):
        c = json.load(open(os.path.join(ROOT, f'raw/abs/sa1_census_{y}.json')))['booths']
        cen[y] = pd.DataFrame([{'venue_id': v, **{k: b.get(k) for k in CENSUS}} for v, b in c.items()])
    yr = lambda e: min(('2006', '2011', '2016', '2021'), key=lambda y: abs(int(y) - int(e[-4:])))
    parts = []
    for e, g in F.groupby('election_id'):
        parts.append(g.merge(cen[yr(e)], on='venue_id'))
    F = pd.concat(parts).dropna(subset=CENSUS)
    for k in CENSUS:                                    # standardise: effects per 1 SD of the booth spread
        F[k] = (F[k] - F[k].mean()) / F[k].std()
    F['female'] = (F.sex == 'F').astype(int)
    F['pe'] = F.party + '_' + F.election_id
    out = {}
    for p in PARTIES:
        g = F[F.party == p]
        if g.female.sum() < 200:
            continue
        rhs = ' + '.join(f'{k}:C(pe) + {k}:female' for k in CENSUS)
        m = smf.ols(f'dev ~ {rhs}', data=g).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(g.seat + g.election_id)[0]})
        ci = m.conf_int()
        out[p] = {'n_booths': int(m.nobs), 'female_booths': int(g.female.sum()),
                  'female_x': {CLABEL[k]: {'pts': round(float(m.params[f'{k}:female']), 2), 'lo': round(float(ci.loc[f'{k}:female', 0]), 2),
                                            'hi': round(float(ci.loc[f'{k}:female', 1]), 2), 'p': round(float(m.pvalues[f'{k}:female']), 3)} for k in CENSUS}}
    return out, F


def leader_switch(F):
    """party booth swing (same venue) between consecutive general elections of a level, regressed on census, transition
    by transition; the transitions into and out of a female leader set against the party's other transitions"""
    L = json.load(open(os.path.join(ROOT, 'raw/reference/party_leaders.json')))
    B = rd('booths'); P = rd('fp'); K = rd('candidates')
    B = B[B.booth_type.eq('ordinary') & B.venue_id.notna() & B.election_id.str.match(r'^(vic|fed)\d{4}$') & (B.election_id != 'vic2023n')]
    P = P.merge(B[['election_id', 'booth_id', 'venue_id']], on=['election_id', 'booth_id']).merge(K[['election_id', 'candidate_id', 'party']], on=['election_id', 'candidate_id'], how='left')
    tot = P.groupby(['election_id', 'venue_id']).votes.sum()
    V = P[P.party.isin(PARTIES)].groupby(['election_id', 'venue_id', 'party']).votes.sum().reset_index()
    V['tot'] = [tot[(e, v)] for e, v in zip(V.election_id, V.venue_id)]
    V = V[V.tot >= 200]; V['sh'] = 100 * V.votes / V.tot
    els = {lv: sorted(e for e in V.election_id.unique() if e.startswith(lv)) for lv in ('vic', 'fed')}
    cen = {y: json.load(open(os.path.join(ROOT, f'raw/abs/sa1_census_{y}.json')))['booths'] for y in ('2006', '2011', '2016', '2021')}
    yr = lambda e: min(cen, key=lambda y: abs(int(y) - int(e[-4:])))
    rows = []
    for lv, es in els.items():
        for a, b in zip(es, es[1:]):
            for p in PARTIES:
                x = V[(V.election_id == a) & (V.party == p)].set_index('venue_id').sh
                y = V[(V.election_id == b) & (V.party == p)].set_index('venue_id').sh
                j = x.index.intersection(y.index)
                if len(j) < 150:
                    continue
                c = cen[yr(b)]
                X = pd.DataFrame([{k: c.get(v, {}).get(k) for k in CENSUS} for v in j], index=j).dropna()
                if len(X) < 150:
                    continue
                X = (X - X.mean()) / X.std()
                sw = (y[X.index] - x[X.index]).values
                A = np.column_stack([np.ones(len(X)), X.values])
                beta = np.linalg.lstsq(A, sw, rcond=None)[0]
                la, lb = L.get(a, {}).get(p, [None, None]), L.get(b, {}).get(p, [None, None])
                kind = 'to_female' if (la[1] != 'F' and lb[1] == 'F') else ('from_female' if (la[1] == 'F' and lb[1] != 'F') else ('female_both' if la[1] == lb[1] == 'F' else 'other'))
                rows.append({'party': p, 'from': a, 'to': b, 'leaders': f'{la[0]} -> {lb[0]}', 'kind': kind, 'n_venues': len(X), 'mean_swing': round(float(sw.mean()), 2),
                             **{CLABEL[k]: round(float(beta[i + 1]), 2) for i, k in enumerate(CENSUS)}})
    R = pd.DataFrame(rows)
    out = {'transitions': rows, 'contrast': {}}
    for p in PARTIES:
        oth = R[(R.party == p) & (R.kind == 'other')]
        for r in R[(R.party == p) & (R.kind != 'other')].to_dict('records'):
            out['contrast'][f"{p} {r['from']}->{r['to']} ({r['leaders']})"] = {
                CLABEL[k]: {'this': r[CLABEL[k]], 'other_mean': round(float(oth[CLABEL[k]].mean()), 2), 'other_sd': round(float(oth[CLABEL[k]].std()), 2),
                            'z': round(float((r[CLABEL[k]] - oth[CLABEL[k]].mean()) / (oth[CLABEL[k]].std() or 1)), 2)} for k in CENSUS} | {'n_other_transitions': int(len(oth))}
    return out


def main():
    K, S = seat_table()
    res = {'about': __doc__.split('\n\n')[0]}
    res['candidates'], d = candidate_models(S)
    res['booth_cohorts'], F = booth_cohorts(S, K)
    res['leader_switch'] = leader_switch(F)
    os.makedirs(os.path.join(ROOT, 'data/analysis'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/sex_effects.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1)[:6000])


if __name__ == '__main__':
    main()
