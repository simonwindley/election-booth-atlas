"""The One Nation Effect, part 1 (Victoria): where One Nation's vote lives, where it grows, and who it takes from.

At every Victorian polling place (venue) with a census profile (the 2021 Census for the area nearest the venue,
src.load_sa1_census):
  * One Nation's Senate share at the 2016, 2019, 2022 and 2025 federal elections (it stands statewide in the
    Senate), and its 2022 Legislative Council share (its only statewide state vote).
  * Level model: One Nation's 2025 Senate share (log-odds) on a dozen census indicators (ridge regression, each
    indicator standardised). Scored out of sample: ten folds, whole districts held out together.
  * Growth model: the change from 2022 to 2025, against the proportional rule (growth in proportion to the
    starting share, lambda from src.primary_swings) and against the census model with the starting share.
  * Who it takes from: at the same venues, the House first-preference change 2022 -> 2025 for Labor, the Coalition
    and the Greens against One Nation's House change, within each division.
  * District propensity for 2026: observed (2022 upper house, 2025 Senate, aggregated from venues) and census-
    predicted, on the 2022 districts.

Inputs  data/elections.sqlite, site/data/demog_booth_vic2022.json.gz, site/data/demog_vic_la_2022.json.gz
Output  data/analysis/onp_effect.json
Usage   python3 -m src.onp_effect
"""
import os, json, gzip, math, sqlite3
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X_KEYS = ['age_median', 'bachelor_or_higher', 'certificate', 'occupation_technicians_and_trades_workers', 'occupation_labourers',
          'occupation_machinery_operators_and_drivers', 'occupation_professionals', 'income_household_median', 'born_overseas',
          'other_language_home', 'owned_outright', 'owned_mortgage', 'rented', 'religion_christianity_total', 'religion_no_religion_so_described',
          'industry_construction', 'industry_manufacturing', 'industry_agriculture_forestry_and_fishing', 'indigenous', 'separate_house']
LABEL = {'age_median': 'Median age', 'bachelor_or_higher': 'Bachelor degree or higher', 'certificate': 'Trade certificate (highest qualification)',
         'occupation_technicians_and_trades_workers': 'Technicians and trades workers', 'occupation_labourers': 'Labourers',
         'occupation_machinery_operators_and_drivers': 'Machinery operators and drivers', 'occupation_professionals': 'Professionals',
         'income_household_median': 'Median household income', 'born_overseas': 'Born overseas', 'other_language_home': 'Language other than English at home',
         'owned_outright': 'Home owned outright', 'owned_mortgage': 'Home owned with a mortgage', 'rented': 'Renting',
         'religion_christianity_total': 'Christian', 'religion_no_religion_so_described': 'No religion', 'industry_construction': 'Works in construction',
         'industry_manufacturing': 'Works in manufacturing', 'industry_agriculture_forestry_and_fishing': 'Works in agriculture',
         'indigenous': 'Aboriginal and Torres Strait Islander', 'separate_house': 'Separate houses'}


def venue_shares(c, eid, table='sen_groups'):
    """{venue: (One Nation share, total)} from Senate groups (federal) at ordinary booths"""
    ven = {b: v for b, v in c.execute("select booth_id, venue_id from booth_geo where election_id = ? and booth_type = 'ordinary' and venue_id is not null", (eid,))}
    tot = defaultdict(float); onp = defaultdict(float)
    for b, p, v in c.execute('select booth_id, party, sum(votes) from sen_groups where election_id = ? group by 1, 2', (eid,)):
        if b in ven:
            tot[ven[b]] += v or 0
            if p == 'ONP':
                onp[ven[b]] += v or 0
    return {k: (onp[k] / t, t) for k, t in tot.items() if t >= 150}


def lc_shares(c):
    ven = {b: v for b, v in c.execute("select booth_id, venue_id from booth_geo where election_id = 'vic2022' and venue_id is not null")}
    party = {k: p for k, p in c.execute("select candidate_id, party from lc_candidates where election_id = 'vic2022'")}
    tot = defaultdict(float); onp = defaultdict(float)
    for b, k, v in c.execute("select booth_id, candidate_id, sum(votes) from lc_votes where election_id = 'vic2022' group by 1, 2"):
        if b in ven:
            tot[ven[b]] += v or 0
            if party.get(k) == 'ONP':
                onp[ven[b]] += v or 0
    return {k: (onp[k] / t, t) for k, t in tot.items() if t >= 150}


def house_shares(c, eid):
    ven = {b: v for b, v in c.execute("select booth_id, venue_id from booth_geo where election_id = ? and booth_type = 'ordinary' and venue_id is not null", (eid,))}
    div = {b: ct for b, ct in c.execute("select booth_id, contest_id from booth_geo where election_id = ?", (eid,))}
    party = {k: p for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (eid,))}
    g = defaultdict(lambda: defaultdict(float)); dv = {}
    for b, k, v in c.execute("select booth_id, candidate_id, sum(votes) from fp_votes where election_id = ? and candidate_id <> 'INFORMAL' group by 1, 2", (eid,)):
        if b not in ven:
            continue
        p = party.get(k, 'OTH'); p = 'COAL' if p in ('LIB', 'NAT') else (p if p in ('ALP', 'GRN', 'ONP') else 'OTH')
        g[ven[b]][p] += v or 0; dv[ven[b]] = div.get(b)
    return {k: ({p: x / sum(d.values()) for p, x in d.items()}, sum(d.values()), dv[k]) for k, d in g.items() if sum(d.values()) >= 150}


def ridge(X, y, w, lam=1.0):
    W = np.sqrt(w)[:, None]
    A = np.hstack([np.ones((len(y), 1)), X]) * W
    R = lam * np.eye(A.shape[1]); R[0, 0] = 0
    return np.linalg.solve(A.T @ A + R, A.T @ (y * W[:, 0]))


def cv_r2(X, y, w, groups, lam=1.0, k=10, seed=1):
    ug = sorted(set(groups)); rng = np.random.default_rng(seed); rng.shuffle(ug)
    fold = {g: i % k for i, g in enumerate(ug)}; f = np.array([fold[g] for g in groups]); pred = np.zeros(len(y))
    for i in range(k):
        tr, te = f != i, f == i
        b = ridge(X[tr], y[tr], w[tr], lam); pred[te] = b[0] + X[te] @ b[1:]
    ss = np.average((y - pred) ** 2, weights=w); st = np.average((y - np.average(y, weights=w)) ** 2, weights=w)
    return 1 - ss / st, pred


def logit(p):
    p = np.clip(p, 0.002, 0.998); return np.log(p / (1 - p))


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    B = json.load(gzip.open(os.path.join(ROOT, 'site/data/demog_booth_vic2022.json.gz')))
    cols = B['cols']; ci = {k: cols.index(k) for k in X_KEYS}
    cen = {v: d['v'] for v, d in B['booths'].items()}
    # venue -> 2022 state district (for grouping and aggregation)
    vd = {v: ct for v, ct in c.execute("select venue_id, contest_id from booth_geo where election_id = 'vic2022' and booth_type = 'ordinary' and venue_id is not null")}
    S = {e: venue_shares(c, e) for e in ('fed2016', 'fed2019', 'fed2022', 'fed2025')}
    LC = lc_shares(c)
    res = {'method': __doc__.split('\n\n')[1].strip()}
    # statewide (ordinary votes at matched venues)
    res['senate_statewide'] = {e: round(100 * sum(s * t for s, t in d.values()) / sum(t for s, t in d.values()), 2) for e, d in S.items()}
    res['lc2022_statewide'] = round(100 * sum(s * t for s, t in LC.values()) / sum(t for s, t in LC.values()), 2)
    print('One Nation, ordinary votes at venues: Senate', res['senate_statewide'], ' upper house 2022', res['lc2022_statewide'])
    # correlations between the maps
    def corr(a, b):
        k = [v for v in a if v in b]; x = np.array([a[v][0] for v in k]); y = np.array([b[v][0] for v in k]); return round(float(np.corrcoef(x, y)[0, 1]), 3), len(k)
    res['map_correlations'] = {'senate2022_v_senate2025': corr(S['fed2022'], S['fed2025']), 'lc2022_v_senate2022': corr(LC, S['fed2022']), 'lc2022_v_senate2025': corr(LC, S['fed2025']),
                               'senate2019_v_senate2025': corr(S['fed2019'], S['fed2025'])}
    print('map correlations:', res['map_correlations'])
    # level model, Senate 2025
    vs = [v for v in S['fed2025'] if v in cen and v in vd]
    X = np.array([[cen[v][ci[k]] or 0 for k in X_KEYS] for v in vs], float)
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1; Z = (X - mu) / sd
    y = logit(np.array([S['fed2025'][v][0] for v in vs])); w = np.array([S['fed2025'][v][1] for v in vs])
    g = [vd[v] for v in vs]
    b = ridge(Z, y, w, 2.0); r2, pred = cv_r2(Z, y, w, g, 2.0)
    res['level'] = {'venues': len(vs), 'cv_r2': round(r2, 3), 'coef': sorted([{'key': k, 'label': LABEL[k], 'beta': round(float(x), 3)} for k, x in zip(X_KEYS, b[1:])], key=lambda r: -abs(r['beta']))}
    print(f"level model (log-odds of One Nation's 2025 Senate share), {len(vs)} venues, out-of-sample R2 {r2:.2f}: " + ', '.join(f"{r['key']} {r['beta']:+.2f}" for r in res['level']['coef'][:8]))
    # growth 2022 -> 2025: proportional rule v census + start
    vg = [v for v in vs if v in S['fed2022']]
    s0 = np.array([S['fed2022'][v][0] for v in vg]); s1 = np.array([S['fed2025'][v][0] for v in vg]); wg = np.array([S['fed2025'][v][1] for v in vg])
    S0, S1 = np.average(s0, weights=wg), np.average(s1, weights=wg)
    uni = s0 + (S1 - S0); pro = s0 * S1 / S0
    lam = float(np.sum(wg * (s1 - uni) * (pro - uni)) / np.sum(wg * (pro - uni) ** 2)); mix = uni + lam * (pro - uni)
    Zg = Z[[vs.index(v) for v in vg]]
    Xg = np.hstack([Zg, ((s0 - s0.mean()) / s0.std())[:, None]])
    r2g, predg = cv_r2(Xg, s1 - s0, wg, [vd[v] for v in vg], 2.0)
    rm = lambda p: round(100 * float(np.sqrt(np.average((s1 - p) ** 2, weights=wg))), 3)
    bg = ridge(Xg, s1 - s0, wg, 2.0)
    res['growth'] = {'venues': len(vg), 'from': round(100 * S0, 2), 'to': round(100 * S1, 2), 'lambda': round(lam, 2),
                     'rmse_uniform': rm(uni), 'rmse_proportional': rm(pro), 'rmse_lambda': rm(mix), 'rmse_census_out_of_sample': rm(s0 + predg),
                     'coef': sorted([{'key': k, 'label': LABEL.get(k, 'Starting share'), 'beta_pts': round(100 * float(x), 3)} for k, x in zip(X_KEYS + ['start'], bg[1:])], key=lambda r: -abs(r['beta_pts']))}
    print(f"growth {100 * S0:.1f}% -> {100 * S1:.1f}%: error uniform {rm(uni)}, proportional {rm(pro)}, lambda {lam:.2f} {rm(mix)}, census + start (out of sample) {rm(s0 + predg)}")
    # who it takes from: House 2022 -> 2025 at the same venues, within division
    H0, H1 = house_shares(c, 'fed2022'), house_shares(c, 'fed2025')
    vh = [v for v in H1 if v in H0 and 'ONP' in H1[v][0] and 'ONP' in H0[v][0]]
    d = {p: np.array([H1[v][0].get(p, 0) - H0[v][0].get(p, 0) for v in vh]) for p in ('ALP', 'COAL', 'GRN', 'ONP', 'OTH')}
    dv = [H1[v][2] for v in vh]
    def demean(x):
        m = defaultdict(list)
        for i, k in enumerate(dv):
            m[k].append(x[i])
        mm = {k: np.mean(v) for k, v in m.items()}
        return x - np.array([mm[k] for k in dv])
    xo = demean(d['ONP'])
    res['takes_from'] = {'venues': len(vh), 'per_point_of_one_nation_gain': {p: round(float(np.sum(xo * demean(d[p])) / np.sum(xo ** 2)), 3) for p in ('ALP', 'COAL', 'GRN', 'OTH')},
                         'mean_change_pts': {p: round(100 * float(d[p].mean()), 2) for p in d}}
    print('who loses where One Nation gains (House, within division, per point):', res['takes_from']['per_point_of_one_nation_gain'], ' mean changes', res['takes_from']['mean_change_pts'])
    # by area type: does the source differ in the outer suburbs / regions?
    # district propensity for 2026
    D = json.load(gzip.open(os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')))['districts']
    agg = defaultdict(lambda: defaultdict(float))
    for src, dd in (('senate2025', S['fed2025']), ('lc2022', LC), ('senate2022', S['fed2022'])):
        for v, (s, t) in dd.items():
            if v in vd:
                agg[vd[v]][src + '_v'] += s * t; agg[vd[v]][src + '_t'] += t
    out = []
    for cid, dd in D.items():
        x = np.array([(dd.get(k) or 0) for k in X_KEYS], float)
        pz = b[0] + ((x - mu) / sd) @ b[1:]
        a = agg.get(cid, {})
        row = {'contest_id': cid, 'seat': dd.get('name'), 'census_predicted_senate2025': round(100 / (1 + math.exp(-pz)), 2)}
        for src in ('senate2025', 'lc2022', 'senate2022'):
            row[src] = round(100 * a[src + '_v'] / a[src + '_t'], 2) if a.get(src + '_t') else None
        out.append(row)
    res['districts'] = sorted(out, key=lambda r: -(r['senate2025'] or r['census_predicted_senate2025']))
    print('districts most One Nation (Senate 2025): ' + ', '.join(f"{r['seat']} {r['senate2025']}" for r in res['districts'][:10]))
    print('least: ' + ', '.join(f"{r['seat']} {r['senate2025']}" for r in res['districts'][-6:]))
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/onp_effect.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
