"""One Nation in the preference count: how strongly each party's voters rank One Nation against the alternatives,
measured from every distribution of preferences we hold outside Victoria (and Victoria's own few), for the 2026
model (the onp_effect question in analysis/questions.json).

Observations (one per exclusion: from-party, votes to each party still standing, the set still standing):
  * other states' general and by-elections (src.load_states -> data/national/state_results.json): QLD 2015-2024,
    WA 2017-2025, NSW 2019-2023, SA 2026 and by-elections
  * federal House counts in every state, 2016-2025 and by-elections incl. Farrer 2026 (src.load_national ->
    data/national.sqlite)
  * Victoria (site/data/dop.json.gz via src.pref_flows)

Model: the same Luce choice model as src.pref_flows, fitted per election on that election's exclusions. The
quantity carried into the Victorian model is a ratio, not a weight: for voters of X, the strength of One Nation
relative to a reference party in the same count (Labor for Coalition and Greens voters; the Liberals for Labor
voters). Ratios travel between electorates far better than raw weights, because each state's minor-party field is
different but the head-to-head between two parties standing in the same count is the same comparison everywhere.
The Victorian 2026 weight is then  w_vic[X][ONP] = w_vic[X][ref] x ratio.  The pooled ratio is a recency-weighted
geometric mean across elections (each election weighted by how recent it is and by how many votes informed it).

Validation: refit leaving out SA 2026 (One Nation's best state result, four seats won), plug the pooled ratios into
weights fitted on SA 2026's other flows, and run SA 2026 first preferences through the count: does the model find
One Nation's final-two places and wins?

Usage: python3 -m src.onp_flows  -> data/analysis/onp_flows.json, and the adjusted 2026 weights in
       site/data/pref_flows.json -> blend_2026.onp_adjusted (the original blend is kept alongside)
"""
import os, json, gzip, math, sqlite3
from collections import defaultdict
import numpy as np

from .pref_flows import fit_luce, KEEP, observations as vic_observations, load as vic_load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = {'LIB': 'ALP', 'NAT': 'ALP', 'GRN': 'ALP', 'ALP': 'LIB', 'IND': 'ALP', 'OTH': 'ALP'}
FROM_PARTIES = ['LIB', 'NAT', 'GRN', 'ALP', 'IND', 'OTH']
YEAR_WEIGHT = lambda y: {2026: 1.0, 2025: 1.0, 2024: 0.8, 2023: 0.6, 2022: 0.5, 2021: 0.4, 2020: 0.35, 2019: 0.3}.get(y, 0.2)


def mp(p):
    return p if p in KEEP else 'OTH'


def national_obs():
    out = []
    D = json.load(open(os.path.join(ROOT, 'data/national/state_results.json')))
    for e, st, dn, f, to, rem in D['observations']:
        to2 = defaultdict(int)
        for p, v in to.items():
            to2[mp(p)] += v
        out.append((e, f'{st}:{dn}', mp(f), dict(to2), {mp(p) for p in rem}))
    c = sqlite3.connect(os.path.join(ROOT, 'data/national.sqlite'))
    party = {(e, k): mp(p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    state = {(e, k): s for e, k, s in c.execute('select election_id, contest_id, state from contests')}
    rows = [dict(zip(('election_id', 'contest_id', 'count_no', 'candidate_id', 'transfer', 'progressive_total'), r))
            for r in c.execute('select election_id, contest_id, count_no, candidate_id, transfer, progressive_total from dop')]
    for e, cid, f, to, rem in vic_observations(rows, party):
        if state.get((e, cid)) == 'VIC':
            continue                                   # Victoria's federal counts come in with the Victorian data
        out.append((e if not e.startswith('fed2') else f'{e}-{state.get((e, cid), "X").lower()}', cid, f, to, rem))
    return out


def year_of(e):
    import re
    m = re.search(r'(\d{4})', e)
    return int(m.group(1)) if m else 2020


def ratios_by_election(obs):
    """{election: {from: {'ratio': w[ONP]/w[ref], 'votes': votes from X that had ONP and ref both standing}}}"""
    by = defaultdict(list)
    for o in obs:
        by[o[0]].append(o + (1.0,))
    out = {}
    for e, o in by.items():
        W = fit_luce(o)
        r = {}
        for f in FROM_PARTIES:
            ref = REF[f]
            w = W.get(f, {})
            votes = sum(sum(to.values()) for _, _, ff, to, rem, _ in o if ff == f and 'ONP' in rem and ref in rem)
            if votes > 0 and w.get('ONP') and w.get(ref):
                r[f] = {'ratio': w['ONP'] / w[ref], 'votes': int(votes)}
        if 'ONP' in W:
            wo = W['ONP']
            if wo.get('LIB') and wo.get('ALP'):
                r['ONP>LIB/ALP'] = {'ratio': wo['LIB'] / wo['ALP'], 'votes': int(sum(sum(to.values()) for _, _, ff, to, rem, _ in o if ff == 'ONP' and {'LIB', 'ALP'} <= rem))}
            if wo.get('NAT') and wo.get('ALP'):
                r['ONP>NAT/ALP'] = {'ratio': wo['NAT'] / wo['ALP'], 'votes': int(sum(sum(to.values()) for _, _, ff, to, rem, _ in o if ff == 'ONP' and {'NAT', 'ALP'} <= rem))}
        if r:
            out[e] = r
    return out


def pool(R, exclude=()):
    """recency- and evidence-weighted geometric mean of each ratio across elections"""
    acc = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for e, r in R.items():
        if e in exclude:
            continue
        for k, v in r.items():
            if v['votes'] < 500:
                continue
            wt = YEAR_WEIGHT(year_of(e)) * math.log10(v['votes'])
            acc[k][0] += wt * math.log(v['ratio']); acc[k][1] += wt; acc[k][2] += 1; acc[k][3] += v['votes']
    out = {}
    for k, (s, w, n, votes) in acc.items():
        logs = [math.log(r[k]['ratio']) for e, r in R.items() if k in r and e not in exclude and r[k]['votes'] >= 500]
        out[k] = {'ratio': round(math.exp(s / w), 3), 'elections': n, 'votes': votes,
                  'spread_x': round(math.exp(float(np.std(logs))), 2) if len(logs) > 1 else None,
                  'share_vs_ref': round(math.exp(s / w) / (1 + math.exp(s / w)), 3)}
    return out


def adjust(W, P):
    """put the pooled One Nation ratios into a weight set (copy)"""
    W2 = {f: dict(t) for f, t in W.items()}
    for f in FROM_PARTIES:
        if f in P and REF[f] in W2.get(f, {}):
            W2.setdefault(f, {})['ONP'] = round(W2[f][REF[f]] * P[f]['ratio'], 4)
    if 'ONP' in W2 and 'ONP>LIB/ALP' in P and 'ALP' in W2['ONP']:
        W2['ONP']['LIB'] = round(W2['ONP']['ALP'] * P['ONP>LIB/ALP']['ratio'], 4)
    if 'ONP' in W2 and 'ONP>NAT/ALP' in P and 'ALP' in W2['ONP']:
        W2['ONP']['NAT'] = round(W2['ONP']['ALP'] * P['ONP>NAT/ALP']['ratio'], 4)
    return W2


def simulate_seat(cands, W, default=1.0):
    """cands: [(party, votes)] -> final two [(party, votes)], exclusion order; one pile per party (a simplification)"""
    live = {i: [p, float(v)] for i, (p, v) in enumerate(cands) if v > 0}
    while len(live) > 2:
        x = min(live, key=lambda i: live[i][1]); p, v = live.pop(x)
        w = W.get(p) or W.get('OTH', {})
        s = {i: w.get(live[i][0], default) for i in live}; t = sum(s.values())
        for i in live:
            live[i][1] += v * s[i] / t
    return sorted(live.values(), key=lambda x: -x[1])


def validate_sa2026(nat, R):
    """leave SA 2026 out of the pooled ratios; fit SA 2026's own weights without any One Nation destination flows;
    put the pooled ratios in; run every SA 2026 district"""
    P = pool(R, exclude=('sa2026',))
    sa = [o + (1.0,) for o in nat if o[0] == 'sa2026']
    blind = []
    for e, c, f, to, rem, wt in sa:                    # hide every pile that could have gone to One Nation
        if 'ONP' in rem and f != 'ONP':
            continue
        blind.append((e, c, f, to, rem, wt))
    W = fit_luce(blind)
    W2 = adjust(W, P)
    D = json.load(open(os.path.join(ROOT, 'data/national/state_results.json')))
    seats = [s for s in D['seats'] if s['election_id'] == 'sa2026']
    res = []
    for s in seats:
        cands = [(mp(c['party']), c['fp']) for c in s['candidates']]
        fin_neutral = simulate_seat(cands, W)            # One Nation weights unseen -> neutral 1.0
        fin = simulate_seat(cands, W2)
        real = sorted(s['tcp'].items(), key=lambda x: -x[1])
        res.append({'district': s['district'], 'real_two': [p for p, _ in real], 'real_winner': real[0][0] if real else None,
                    'model_two': [p for p, _ in fin], 'model_winner': fin[0][0], 'neutral_winner': fin_neutral[0][0],
                    'real_onp_2cp': round(100 * dict(real).get('ONP', 0) / sum(dict(real).values()), 1) if real and 'ONP' in dict(real) else None,
                    'model_onp_2cp': round(100 * dict(fin).get('ONP', 0) / sum(v for _, v in fin), 1) if 'ONP' in dict(fin) else None})
    ok = [r for r in res if r['real_winner']]
    summ = {'districts': len(ok), 'winner_right': sum(r['model_winner'] == r['real_winner'] for r in ok),
            'winner_right_neutral': sum(r['neutral_winner'] == r['real_winner'] for r in ok),
            'final_two_right': sum(set(r['model_two']) == set(r['real_two']) for r in ok),
            'onp_won_real': [r['district'] for r in ok if r['real_winner'] == 'ONP'],
            'onp_won_model': [r['district'] for r in ok if r['model_winner'] == 'ONP'],
            'onp_won_neutral': [r['district'] for r in ok if r['neutral_winner'] == 'ONP'],
            'onp_in_final_two_real': sum('ONP' in r['real_two'] for r in ok), 'onp_in_final_two_model': sum('ONP' in r['model_two'] for r in ok),
            'onp_2cp_error_pts': round(float(np.mean([abs(r['model_onp_2cp'] - r['real_onp_2cp']) for r in ok if r['model_onp_2cp'] is not None and r['real_onp_2cp'] is not None] or [np.nan])), 2),
            'pooled_ratios_used': P}
    return summ, res


def surges():
    """how One Nation's seat map changed when its vote jumped between two elections of the same state"""
    from scipy.optimize import brentq
    D = json.load(open(os.path.join(ROOT, 'data/national/state_results.json')))
    def onp(e):
        out = {}
        for s in D['seats']:
            if s['election_id'] != e:
                continue
            t = sum(c['fp'] for c in s['candidates']); o = sum(c['fp'] for c in s['candidates'] if c['party'] == 'ONP')
            if t:
                out[s['district']] = (o / t, t, any(c['party'] == 'ONP' for c in s['candidates']))
        return out
    lg = lambda p: np.log(p / (1 - p))
    res = []
    for a, b, lab in (('sa2022', 'sa2026', 'South Australia 2022 to 2026'), ('qld2015', 'qld2017', 'Queensland 2015 to 2017'),
                      ('qld2020', 'qld2024', 'Queensland 2020 to 2024'), ('wa2021', 'wa2025', 'Western Australia 2021 to 2025')):
        A, B = onp(a), onp(b)
        com = [d for d in A if d in B and A[d][2] and B[d][2]]
        sa = sum(A[d][0] * A[d][1] for d in A) / sum(A[d][1] for d in A); sb = sum(B[d][0] * B[d][1] for d in B) / sum(B[d][1] for d in B)
        x = np.array([A[d][0] for d in com]); y = np.array([B[d][0] for d in com])
        uni = x + (y.mean() - x.mean()); pro = x * y.mean() / x.mean()
        lam = np.linspace(-0.5, 1.5, 201); rm = [np.sqrt(np.mean((uni + l * (pro - uni) - y) ** 2)) for l in lam]
        slope = float(np.polyfit(lg(np.clip(x, 1e-3, .99)), lg(np.clip(y, 1e-3, .99)), 1)[0])
        stood = {d: v for d, v in B.items() if v[2]}
        hi = max(stood, key=lambda d: stood[d][0]); lo = min(stood, key=lambda d: stood[d][0])
        res.append({'label': lab, 'from': a, 'to': b, 'statewide_from': round(100 * sa, 1), 'statewide_to': round(100 * sb, 1), 'seats_both': len(com),
                    'seats_stood_to': len(stood), 'seats_to': len(B), 'lambda': round(float(lam[int(np.argmin(rm))]), 2), 'logit_slope': round(slope, 2),
                    'rmse_uniform': round(100 * float(np.sqrt(np.mean((uni - y) ** 2))), 1), 'rmse_proportional': round(100 * float(np.sqrt(np.mean((pro - y) ** 2))), 1),
                    'highest': [hi, round(100 * stood[hi][0], 1)], 'lowest': [lo, round(100 * stood[lo][0], 1)],
                    'won': sorted(s['district'] for s in D['seats'] if s['election_id'] == b and s.get('winner') == 'ONP')})
    return res


def main():
    nat = national_obs()
    rows, party = vic_load()
    vic = [o for o in vic_observations(rows, party)]
    allobs = nat + vic
    R = ratios_by_election(allobs)
    P = pool(R)
    P_ext = pool({e: r for e, r in R.items() if not (e.startswith('vic') or e.startswith('fed2'))})   # other states' own elections only
    P_vic = pool({e: r for e, r in R.items() if e.startswith('vic') or (e.startswith('fed') and '-' not in e)})
    flows = json.load(open(os.path.join(ROOT, 'site/data/pref_flows.json')))
    W26 = flows['blend_2026']['weights']
    W26a = adjust(W26, P)
    # what the adjustment means in the simplest head-to-heads
    def sh(W, f, a, b):
        w = W.get(f, {}); x, y = w.get(a, 1.0), w.get(b, 1.0)
        return round(100 * x / (x + y), 1)
    heads = {f'{f} voters: ONP vs {REF[f]}': {'before': sh(W26, f, 'ONP', REF[f]), 'after': sh(W26a, f, 'ONP', REF[f])} for f in FROM_PARTIES}
    heads['ONP voters: LIB vs ALP'] = {'before': sh(W26, 'ONP', 'LIB', 'ALP'), 'after': sh(W26a, 'ONP', 'LIB', 'ALP')}
    heads['ONP voters: NAT vs ALP'] = {'before': sh(W26, 'ONP', 'NAT', 'ALP'), 'after': sh(W26a, 'ONP', 'NAT', 'ALP')}
    val, val_rows = validate_sa2026(nat, R)
    out = {'method': __doc__.split('\n\n')[0], 'n_observations': {'other_states_and_federal': len(nat), 'victoria': len(vic)},
           'by_election': {e: {k: {'ratio': round(v['ratio'], 3), 'votes': v['votes']} for k, v in r.items()} for e, r in sorted(R.items())},
           'pooled': P, 'pooled_other_state_elections_only': P_ext, 'pooled_victoria_only': P_vic,
           'head_to_head_2026': heads, 'surges': surges(), 'validation_sa2026': val, 'validation_sa2026_seats': val_rows}
    os.makedirs(os.path.join(ROOT, 'data/analysis'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'data/analysis/onp_flows.json'), 'w'), indent=1)
    flows['blend_2026']['onp_adjusted'] = {'weights': W26a, 'pooled_ratios': P, 'source': 'src.onp_flows'}
    json.dump(flows, open(os.path.join(ROOT, 'site/data/pref_flows.json'), 'w'), separators=(',', ':'))
    print('pooled ratios (ONP strength / reference):')
    for k, v in sorted(P.items()):
        print(f'   {k:12s} {v}')
    print('head to head, 2026 weights:', json.dumps(heads, indent=0))
    print('SA 2026 validation:', {k: v for k, v in val.items() if k != 'pooled_ratios_used'})


if __name__ == '__main__':
    main()
