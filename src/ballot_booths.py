"""Ballot-order voting at booth level: who votes by the ballot paper, from the first-preference bonus of the candidate
drawn first, booth by booth.

The candidate in position 1 is the same at every booth of an electorate, so the bonus is not separable from the
candidate's own appeal within one electorate. Across electorates it is: the draw is random, so which party sits in
position 1 varies, and the booths' deviations from their electorate (booth share minus electorate share, per
candidate) can be modelled as

    dev[b,c] = sum_k g[P(c),k] * z[b,k]  +  [c is position 1] * (delta0 + sum_k delta[k] * z[b,k])  + noise

where z[b,k] is the booth's census indicator k expressed as a deviation from its electorate mean (so the party
gradients g are how each party's local vote varies with the census profile, and the delta terms are how the
position-1 bonus varies with it). Weighted by booth size. Elections pooled over the venues the 2022 catchment census
covers (state 2018 and 2022, federal 2022 and 2025 at the same venues).

Outputs the gradients, a booth-level susceptibility score (the predicted position-1 bonus relative to the state), the
bonus by quartile of each indicator, and the correlations.

Usage: python3 -m src.ballot_booths     -> raw/pref/ballot_booths.json, site/data/ballot_booths.json
"""
import os, sys, json, gzip, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.pref_flows import KEEP  # noqa: E402
from src.ballot_effects import solve, corr  # noqa: E402

ELECTIONS = ['vic2018', 'vic2022', 'fed2022', 'fed2025']
INDS = ['other_language_home', 'english_not_well', 'born_overseas', 'bachelor_or_higher', 'year12', 'age_median', 'age_65_plus', 'adults_18_34',
        'income_household_median', 'religion_no_religion_so_described', 'flat_apartment', 'occupation_professionals', 'occupation_labourers', 'population']
MODEL_INDS = ['other_language_home', 'bachelor_or_higher', 'age_median', 'religion_no_religion_so_described', 'income_household_median']


def grp(p):
    return 'COAL' if p in ('LIB', 'NAT') else (p if p in KEEP else 'OTH')


def load():
    f = json.load(gzip.open(os.path.join(ROOT, 'site/data/fp.json.gz')))
    fp = defaultdict(lambda: defaultdict(int))     # (eid, booth) -> cand -> votes
    for e, b, c, v in f['rows']:
        if c != 'INFORMAL':
            fp[(e, b)][c] += v
    bo = json.load(gzip.open(os.path.join(ROOT, 'site/data/booths.json.gz')))
    booths = {(r[0], r[2]): dict(zip(bo['cols'], r)) for r in bo['rows'] if r[4] == 'ordinary'}
    c = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz')))
    cands = {(r[0], r[2]): dict(zip(c['cols'], r)) for r in c['rows']}
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/demog_booth_vic2022.json.gz')))
    ci = {k: i for i, k in enumerate(d['cols'])}
    venue = {vid: {k: x['v'][ci[k]] for k in INDS if k in ci and x['v'][ci[k]] is not None} for vid, x in d['booths'].items()}
    return fp, booths, cands, venue


def main():
    fp, booths, cands, venue = load()
    # observations: per election, per electorate, per booth, per candidate deviation
    obs = []   # (eid, cid, bid, cand, party group, pos1, dev, weight, z dict)
    for eid in ELECTIONS:
        by_seat = defaultdict(list)
        for (e, b), bb in booths.items():
            if e == eid and bb['venue_id'] in venue and (e, b) in fp:
                by_seat[bb['contest_id']].append(bb)
        for cid, bl in by_seat.items():
            tot = defaultdict(int); seatTot = 0
            for bb in bl:
                for c, v in fp[(eid, bb['booth_id'])].items():
                    tot[c] += v; seatTot += v
            if seatTot < 1000 or len(bl) < 4:
                continue
            seat_share = {c: v / seatTot for c, v in tot.items()}
            # electorate mean of each indicator (booth-weighted)
            W = sum(sum(fp[(eid, bb['booth_id'])].values()) for bb in bl)
            zbar = {k: sum(venue[bb['venue_id']].get(k, 0) * sum(fp[(eid, bb['booth_id'])].values()) for bb in bl if k in venue[bb['venue_id']]) / W for k in INDS}
            for bb in bl:
                row = fp[(eid, bb['booth_id'])]; n = sum(row.values())
                if n < 100:
                    continue
                z = {k: venue[bb['venue_id']][k] - zbar[k] for k in INDS if k in venue[bb['venue_id']]}
                for c, v in row.items():
                    cc = cands.get((eid, c))
                    if not cc or not cc.get('ballot_position'):
                        continue
                    obs.append((eid, cid, bb['booth_id'], c, grp(cc['party']), 1.0 if cc['ballot_position'] == 1 else 0.0, v / n - seat_share[c], n, z))
    print(f'{len(obs)} booth-candidate observations across {len({(o[0], o[1]) for o in obs})} electorate-elections')
    # ---- regression: party-group gradients on MODEL_INDS + position-1 intercept and gradients
    groups = sorted({o[4] for o in obs}); K = MODEL_INDS
    # scale the indicators to standard deviations so the deltas are comparable
    sd = {k: math.sqrt(sum(o[8].get(k, 0) ** 2 * o[7] for o in obs) / sum(o[7] for o in obs)) or 1 for k in K}
    cols = [(g, k) for g in groups for k in K] + [('pos1', None)] + [('pos1', k) for k in K]
    idx = {c: i for i, c in enumerate(cols)}
    X, Y, Wt = [], [], []
    for o in obs:
        x = [0.0] * len(cols)
        for k in K:
            x[idx[(o[4], k)]] = o[8].get(k, 0) / sd[k]
        if o[5]:
            x[idx[('pos1', None)]] = 1.0
            for k in K:
                x[idx[('pos1', k)]] = o[8].get(k, 0) / sd[k]
        X.append(x); Y.append(o[6]); Wt.append(o[7])
    n = len(cols)
    A = [[0.0] * n for _ in range(n)]; b = [0.0] * n
    for x, y, w in zip(X, Y, Wt):
        nz = [i for i in range(n) if x[i]]
        for i in nz:
            b[i] += w * x[i] * y
            for j in nz:
                A[i][j] += w * x[i] * x[j]
    beta = solve(A, b)
    deltas = {k: beta[idx[('pos1', k)]] for k in K}
    print('Position-1 bonus gradient per standard deviation of the booth indicator (points of the booth vote; + = more ballot-order voting):')
    for k in K:
        print(f'  {k:36} {100 * deltas[k]:+.2f} pts per sd')
    # ---- descriptive: position-1 deviation (net of the party gradient) by quartile of each indicator
    def resid(o):
        return o[6] - sum(beta[idx[(o[4], k)]] * o[8].get(k, 0) / sd[k] for k in K)
    pos1 = [o for o in obs if o[5]]
    quart = {}
    for k in INDS:
        vals = sorted((o[8].get(k, 0), resid(o), o[7]) for o in pos1 if k in o[8])
        if len(vals) < 200:
            continue
        q = len(vals) // 4; out = []
        for i in range(4):
            part = vals[i * q:(i + 1) * q if i < 3 else len(vals)]
            w = sum(p[2] for p in part); out.append(round(100 * sum(p[1] * p[2] for p in part) / w, 2))
        quart[k] = out
    print('Position-1 excess (net of the party\'s own gradient) by quartile of the booth\'s indicator, lowest to highest quartile, points:')
    for k, v in quart.items():
        print(f'  {k:36} ' + '  '.join(f'{x:+.2f}' for x in v))
    # ---- booth susceptibility score: predicted bonus relative to the state, from the fitted deltas
    allz = {}
    for (e, b), bb in booths.items():
        if e == 'vic2022' and bb['venue_id'] in venue:
            allz[bb['venue_id']] = venue[bb['venue_id']]
    # state means for the score (population weighted over venues)
    Wv = sum(v.get('population', 0) for v in allz.values()) or 1
    mean = {k: sum(v.get(k, 0) * v.get('population', 0) for v in allz.values()) / Wv for k in K}
    score = {}
    for vid, v in allz.items():
        s = sum(deltas[k] * (v.get(k, mean[k]) - mean[k]) / sd[k] for k in K)
        score[vid] = round(100 * s, 2)       # points of position-1 bonus above/below the state average booth
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    names = {bb['venue_id']: (bb['booth_name'], bb['contest_id']) for (e, b), bb in booths.items() if e == 'vic2022'}
    print('Most ballot-order-prone booths (predicted extra position-1 bonus, pts): ' + ', '.join(f'{names[v][0]} ({names[v][1].replace("vic-", "")}) {s:+.1f}' for v, s in ranked[:8]))
    print('Least: ' + ', '.join(f'{names[v][0]} ({names[v][1].replace("vic-", "")}) {s:+.1f}' for v, s in ranked[-8:]))
    # correlations of the raw position-1 residual with each indicator (booth level)
    cors = {}
    for k in INDS:
        pairs = [(o[8][k], resid(o)) for o in pos1 if k in o[8]]
        if len(pairs) > 200:
            cors[k] = round(corr([p[0] for p in pairs], [p[1] for p in pairs]), 3)
    print('Correlations (booth deviation of the indicator vs position-1 excess): ' + ', '.join(f'{k} {v:+.2f}' for k, v in sorted(cors.items(), key=lambda kv: -abs(kv[1]))))
    pos1_mean = sum(resid(o) * o[7] for o in pos1) / sum(o[7] for o in pos1)
    out = {'elections': ELECTIONS, 'observations': len(obs), 'pos1_candidates': len({(o[0], o[1]) for o in pos1}), 'intercept_pts': round(100 * beta[idx[('pos1', None)]], 3),
           'deltas_pts_per_sd': {k: round(100 * v, 3) for k, v in deltas.items()}, 'sd': {k: round(v, 4) for k, v in sd.items()}, 'quartiles': quart, 'correlations': cors,
           'score': score, 'score_note': 'predicted position-1 bonus at the booth relative to the average Victorian booth, points of the booth vote, from the fitted census gradients',
           'highest': [{'venue': v, 'name': names[v][0], 'contest': names[v][1], 'score': s} for v, s in ranked[:15]], 'lowest': [{'venue': v, 'name': names[v][0], 'contest': names[v][1], 'score': s} for v, s in ranked[-15:][::-1]]}
    json.dump(out, open(os.path.join(ROOT, 'raw/pref/ballot_booths.json'), 'w'), indent=0)
    slim = {k: v for k, v in out.items() if k != 'score'}
    slim['score'] = score
    json.dump(slim, open(os.path.join(ROOT, 'site/data/ballot_booths.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
