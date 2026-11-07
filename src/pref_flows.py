"""Preference-flow model from the distributions of preferences in the Atlas (every Victorian state and federal
contest, 2010-2025), for projecting a two-candidate result from first preferences.

Observations: at each count of each distribution exactly one candidate is excluded and their pile goes to the
candidates still standing. That gives (election, from-party, set of parties remaining, votes to each). Each
pile is treated as the excluded party's voters (it also carries votes received earlier, which is the usual
simplification).

Model: a Luce ("ratio of strengths") choice model per from-party. Voters of X have a weight w[X][Y] for every
other party Y; when the parties remaining are R, the share of X's pile going to Y is w[X][Y] / sum over Z in R of
w[X][Z]. Fitted by maximum likelihood (minorisation-maximisation) on every exclusion of X, so a flow is estimated
even for a combination of remaining parties never seen; the direct observation (X excluded with exactly A and B
left) is also kept where it exists. Parties with few candidates are pooled as OTH; LIB and NAT stay separate
(three-cornered contests) and are grouped only when reporting.

Fitted per election and as a blend for 2026 (state 2022 weighted 2, federal 2025 weighted 1 for the flows a
state count has rarely seen, e.g. One Nation's; earlier elections weighted 0.5 then 0.25).

Validation: fit on 2018 (plus federal 2019), run the 2022 first preferences through the exclusion simulation and
compare the final pair and 2CP with the real 2022 distribution.

Usage: python3 -m src.pref_flows   -> site/data/pref_flows.json  (+ raw/pref/flow_observations.json)
"""
import os, json, gzip, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEEP = {'ALP', 'LIB', 'NAT', 'GRN', 'ONP', 'VSP', 'AJP', 'FFP', 'LDP', 'DLP', 'FRP', 'RUA', 'SFF', 'UAP', 'LCP', 'DHJ', 'IND', 'SAP', 'TMP', 'CYA', 'NDP'}
GRP = {'LIB': 'COAL', 'NAT': 'COAL'}
ELECTIONS = ['vic2010', 'vic2014', 'vic2018', 'vic2022', 'vic2023n', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025', 'vicby-mulgrave-2023', 'vicby-prahran-2025', 'vicby-werribee-2025', 'vicby-nepean-2026']
BLEND_2026 = {'vic2022': 2.0, 'vic2023n': 1.0, 'vicby-mulgrave-2023': 1.0, 'vicby-prahran-2025': 1.0, 'vicby-werribee-2025': 1.0, 'vicby-nepean-2026': 1.0, 'fed2025': 1.0, 'fed2022': 0.5, 'vic2018': 0.5, 'fed2019': 0.25, 'vic2014': 0.25}


def load():
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/dop.json.gz'))); rows = [dict(zip(d['cols'], r)) for r in d['rows']]
    c = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz'))); cc = [dict(zip(c['cols'], r)) for r in c['rows']]
    party = {(r['election_id'], r['candidate_id']): (r['party'] if r['party'] in KEEP else 'OTH') for r in cc}
    return rows, party


def observations(rows, party):
    """[(eid, contest, from_party, {to_party: votes}, remaining set)]"""
    by = defaultdict(list)
    for r in rows:
        by[(r['election_id'], r['contest_id'], r['count_no'])].append(r)
    obs = []
    for (eid, cid, cn), rs in by.items():
        if cn == 0:
            continue
        exc = [r for r in rs if r['transfer'] < 0]
        if len(exc) != 1:
            continue
        fp = party.get((eid, exc[0]['candidate_id']), 'OTH')
        out = -exc[0]['transfer']
        to = defaultdict(int)
        for r in rs:
            if r['transfer'] > 0:
                to[party.get((eid, r['candidate_id']), 'OTH')] += r['transfer']
        remaining = {party.get((eid, r['candidate_id']), 'OTH') for r in rs if r['candidate_id'] != exc[0]['candidate_id'] and r['progressive_total'] > 0}
        if out > 0 and to:
            obs.append((eid, cid, fp, dict(to), remaining))
    return obs


def fit_luce(obs_list, iters=200):
    """per from-party, weights over destination parties (geometric-mean normalised); MM algorithm for the Luce model"""
    byfrom = defaultdict(list)
    for eid, cid, fp, to, rem, wt in obs_list:
        byfrom[fp].append((to, rem, wt))
    W = {}
    for fp, data in byfrom.items():
        parties = sorted({p for to, rem, wt in data for p in rem} | {p for to, rem, wt in data for p in to})
        w = {p: 1.0 for p in parties}
        for _ in range(iters):
            num, den = defaultdict(float), defaultdict(float)
            for to, rem, wt in data:
                tot = sum(to.values()) * wt
                s = sum(w[p] for p in rem if p in w)
                if s <= 0:
                    continue
                for p in rem:
                    if p in w:
                        den[p] += tot / s
                for p, v in to.items():
                    num[p] += v * wt
            new = {p: (num[p] / den[p] if den[p] > 0 and num[p] > 0 else w[p] * 0.5) for p in parties}
            g = math.exp(sum(math.log(x) for x in new.values()) / len(new))
            w = {p: x / g for p, x in new.items()}
        W[fp] = {p: round(x, 4) for p, x in w.items()}
    return W


def share(W, fp, remaining):
    """how X's pile splits among the remaining parties under the fitted weights"""
    w = W.get(fp) or {}
    s = {p: w.get(p, 0.3) for p in remaining}   # a destination never seen for X gets a small default
    tot = sum(s.values())
    return {p: v / tot for p, v in s.items()} if tot else {p: 1 / len(remaining) for p in remaining}


def pairs(obs_list):
    """direct observations: X excluded with exactly two parties left -> share to the first (alphabetical) of the pair"""
    acc = defaultdict(lambda: [0.0, 0.0, 0])
    for eid, cid, fp, to, rem, wt in obs_list:
        if len(rem) != 2:
            continue
        a, b = sorted(rem)
        acc[(fp, a, b)][0] += to.get(a, 0); acc[(fp, a, b)][1] += to.get(a, 0) + to.get(b, 0); acc[(fp, a, b)][2] += 1
    return {f'{fp}|{a}|{b}': {'to_first': round(x / y, 4), 'votes': int(y), 'contests': n} for (fp, a, b), (x, y, n) in acc.items() if y > 0}


def simulate(fps, W, pair=None):
    """fps: {candidate_id: (party, votes)}; exclude the lowest each round and redistribute by the fitted shares.
    pair: keep these two candidate ids to the end. Returns the ladder and the final piles."""
    piles = {c: float(v) for c, (p, v) in fps.items()}
    party = {c: p for c, (p, v) in fps.items()}
    ladder = []
    while len(piles) > 2:
        cands = [c for c in piles if not pair or c not in pair]
        if not cands:
            break
        x = min(cands, key=lambda c: piles[c])
        rem = {c: party[c] for c in piles if c != x}
        sh = share(W, party[x], set(rem.values()))
        # several remaining candidates of one party (rare) split that party's share equally
        per_party = defaultdict(list)
        for c, p in rem.items():
            per_party[p].append(c)
        moved = {}
        for p, cs in per_party.items():
            for c in cs:
                moved[c] = piles[x] * sh.get(p, 0) / len(cs)
        ladder.append({'excluded': x, 'party': party[x], 'votes': round(piles[x]), 'to': {c: round(v) for c, v in moved.items()}})
        for c, v in moved.items():
            piles[c] += v
        del piles[x]
    return ladder, {c: round(v) for c, v in piles.items()}


def validate(W, rows, party, eid):
    """run eid's first preferences through the model and compare with its real final pairs"""
    by = defaultdict(list)
    for r in rows:
        if r['election_id'] == eid:
            by[r['contest_id']].append(r)
    t = json.load(gzip.open(os.path.join(ROOT, 'site/data/contest_tcp.json.gz'))); tcp = defaultdict(dict)
    for r in t['rows']:
        r = dict(zip(t['cols'], r))
        if r['election_id'] == eid:
            tcp[r['contest_id']][r['candidate_id']] = r['votes']
    out = []
    for cid, rs in by.items():
        fps = {r['candidate_id']: (party[(eid, r['candidate_id'])], r['progressive_total']) for r in rs if r['count_no'] == 0}
        final = tcp.get(cid, {})   # the official two-candidate preferred count
        if len(fps) < 3 or len(final) != 2 or not all(c in fps for c in final):
            continue
        ladder, piles = simulate(fps, W)
        real_pair = set(final); model_pair = set(piles)
        a = sorted(final, key=lambda c: -final[c])[0]
        # model 2CP for the real pair
        _, p2 = simulate(fps, W, pair=real_pair)
        tot = sum(p2.values()); real_tot = sum(final.values())
        out.append({'contest': cid, 'pair_right': real_pair == model_pair, 'winner_right': max(p2, key=p2.get) == a,
                    'real': round(100 * final[a] / real_tot, 2), 'model': round(100 * p2[a] / tot, 2), 'err': round(100 * p2[a] / tot - 100 * final[a] / real_tot, 2)})
    return out


def main():
    rows, party = load()
    obs = observations(rows, party)
    per_election = {}
    for eid in ELECTIONS:
        o = [(e, c, f, t, r, 1.0) for e, c, f, t, r in obs if e == eid]
        if o:
            per_election[eid] = {'n_exclusions': len(o), 'weights': fit_luce(o), 'pairs': pairs(o)}
    # validation: 2018 state + 2019 federal -> 2022 state
    train = [(e, c, f, t, r, {'vic2018': 2.0, 'fed2019': 1.0, 'vic2014': 0.5}[e]) for e, c, f, t, r in obs if e in ('vic2018', 'fed2019', 'vic2014')]
    W18 = fit_luce(train)
    val = validate(W18, rows, party, 'vic2022')
    errs = [abs(v['err']) for v in val]
    val_summary = {'fitted_on': 'vic2018 (x2), fed2019, vic2014 (x0.5)', 'tested_on': 'vic2022', 'contests': len(val),
                   'final_pair_right': sum(v['pair_right'] for v in val), 'winner_right': sum(v['winner_right'] for v in val),
                   'mean_abs_error_2cp_pts': round(sum(errs) / len(errs), 2), 'median_abs_error_2cp_pts': round(sorted(errs)[len(errs) // 2], 2),
                   'worst': sorted(val, key=lambda v: -abs(v['err']))[:8]}
    print(f"validation 2018->2022: {val_summary['contests']} contests, final pair right {val_summary['final_pair_right']}, winner right {val_summary['winner_right']}, "
          f"mean |error| {val_summary['mean_abs_error_2cp_pts']} pts, median {val_summary['median_abs_error_2cp_pts']}")
    for v in val_summary['worst'][:5]:
        print('   ', v)
    # the 2026 blend
    blend = [(e, c, f, t, r, BLEND_2026[e]) for e, c, f, t, r in obs if e in BLEND_2026]
    W26 = fit_luce(blend)
    # also a self-test: the blend run on 2022 (in-sample, so optimistic)
    val22 = validate(W26, rows, party, 'vic2022'); e22 = [abs(v['err']) for v in val22]
    print(f"blend on 2022 (in sample): pair right {sum(v['pair_right'] for v in val22)}/{len(val22)}, mean |error| {sum(e22) / len(e22):.2f} pts")
    out = {'model': 'Luce choice model per voter-party, fitted by maximum likelihood on every exclusion in the distributions of preferences',
           'blend_2026': {'weights': W26, 'elections': BLEND_2026, 'n_exclusions': len(blend), 'pairs': pairs(blend)},
           'per_election': per_election, 'validation': val_summary, 'grouping': GRP, 'parties': sorted(KEEP | {'OTH'})}
    os.makedirs(os.path.join(ROOT, 'raw/pref'), exist_ok=True)
    json.dump([{'election': e, 'contest': c, 'from': f, 'to': t, 'remaining': sorted(r)} for e, c, f, t, r in obs], open(os.path.join(ROOT, 'raw/pref/flow_observations.json'), 'w'), separators=(',', ':'))
    json.dump(out, open(os.path.join(ROOT, 'site/data/pref_flows.json'), 'w'), separators=(',', ':'))
    print(len(obs), 'exclusions ->', os.path.join(ROOT, 'site/data/pref_flows.json'))
    # a few headline flows, grouped
    for fp in ('GRN', 'LIB', 'ONP', 'VSP', 'IND', 'AJP', 'FFP'):
        for eid in ('vic2018', 'vic2022', 'fed2025'):
            W = per_election.get(eid, {}).get('weights', {}).get(fp)
            if W:
                sh = share(per_election[eid]['weights'], fp, {'ALP', 'LIB'}) if fp != 'LIB' else share(per_election[eid]['weights'], fp, {'ALP', 'GRN'})
                print(f'   {fp} voters, {eid}: ' + ', '.join(f'{p} {100 * v:.0f}%' for p, v in sorted(sh.items())))


if __name__ == '__main__':
    main()
