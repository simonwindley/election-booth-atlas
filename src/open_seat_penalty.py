"""Why does a retiring member cost their party ~2.6 points of first preferences but barely anything in the two-party count?

member_effects measures the open-seat penalty on the party's first-preference share; seat_swing_deviation measures seats on
the two-party-preferred count with the last margin held constant, and finds a much smaller effect. This decomposes the gap.
For every seat whose member's party was Labor or the Coalition, the change in each quantity is measured against the same
party's seats with a veteran member standing again at the same election (election x party baseline, as in member_effects):

  fp_party      the party's first-preference share           (the member_effects measure)
  fp_other_major the other major party's first preferences
  fp_minor      everyone else: Greens, independents, minor parties
  n_candidates  candidates on the ballot
  tpp_party     the party's two-party-preferred share (Labor v Coalition seats both times; notional where boundaries changed)
then the two-party effect again with the last margin held constant (regression to the mean), and split by the retiring
member's tenure and by party.

usage: python3 -m src.open_seat_penalty   -> data/analysis/open_seat_penalty.json
"""
import os, csv, json, sqlite3
import numpy as np
from collections import defaultdict
from src.seat_loss import load

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def boot_diff(a, b, groups_a, groups_b, n=1000, seed=3):
    """mean(a) - mean(b), bootstrap over seats within elections"""
    rng = np.random.default_rng(seed); out = []
    ga, gb = defaultdict(list), defaultdict(list)
    for x, g in zip(a, groups_a): ga[g].append(x)
    for x, g in zip(b, groups_b): gb[g].append(x)
    for _ in range(n):
        A = [v for k in ga for v in rng.choice(ga[k], len(ga[k]))]; B = [v for k in gb for v in rng.choice(gb[k], len(gb[k]))]
        out.append(np.mean(A) - np.mean(B))
    return round(float(np.mean(a) - np.mean(b)), 2), round(float(np.percentile(out, 5)), 2), round(float(np.percentile(out, 95)), 2)


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite')); D = load(c)
    NOT = {}
    for rd in json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']:
        for st in rd['seats']: NOT[(rd['for'], st['seat'])] = st
    rows = []
    for h in csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv'))):
        if h['via'] != 'general' or h['party'] not in ('ALP', 'COAL') or h['category'] not in ('veteran', 'open'): continue
        P, O = h['party'], ('COAL' if h['party'] == 'ALP' else 'ALP'); t0, t1, nm = h['from'], h['to'], h['seat']
        F0, F1 = D['fp'].get((t0, nm)), D['fp'].get((t1, nm))
        if not F0 or not F1: continue
        r = dict(level=h['level'], to=t1, seat=nm, party=P, cat=h['category'], wins=int(h['wins'] or 0),
                 fp_party=100 * (F1.get(P, 0) - F0.get(P, 0)), fp_other_major=100 * (F1.get(O, 0) - F0.get(O, 0)),
                 fp_minor=100 * ((1 - F1.get('ALP', 0) - F1.get('COAL', 0)) - (1 - F0.get('ALP', 0) - F0.get('COAL', 0))),
                 n_candidates=(D['ncand'].get((t1, nm), 0) - D['ncand'].get((t0, nm), 0)))
        T0, T1 = D['tcp'].get((t0, nm)), D['tcp'].get((t1, nm))
        if T1 and set(T1) == {'ALP', 'COAL'}:
            a0 = NOT[(t1, nm)]['alp_2pp'] if (t1, nm) in NOT else (T0['ALP'] if T0 and set(T0) == {'ALP', 'COAL'} else None)
            if a0 is not None:
                s = 1 if P == 'ALP' else -1
                r['tpp_party'] = 100 * s * (T1['ALP'] - a0); r['margin'] = 100 * (s * (a0 - 0.5))
        rows.append(r)
    # election x party baseline: subtract the veterans' mean
    base = defaultdict(dict)
    keys = ['fp_party', 'fp_other_major', 'fp_minor', 'n_candidates', 'tpp_party']
    for k in keys:
        g = defaultdict(list)
        for r in rows:
            if r['cat'] == 'veteran' and r.get(k) is not None: g[(r['to'], r['party'])].append(r[k])
        for key, v in g.items(): base[k][key] = float(np.mean(v))
    for r in rows:
        for k in keys:
            if r.get(k) is not None and (r['to'], r['party']) in base[k]: r['rel_' + k] = r[k] - base[k][(r['to'], r['party'])]
    res = {'method': __doc__.split('\n\n')[1].strip()}

    def compare(sel, label):
        out = {}
        for k in keys:
            A = [r for r in rows if sel(r) and r['cat'] == 'open' and r.get('rel_' + k) is not None]
            B = [r for r in rows if sel(r) and r['cat'] == 'veteran' and r.get('rel_' + k) is not None]
            if len(A) < 5: continue
            out[k] = dict(zip(('open_minus_veteran', 'lo', 'hi'), boot_diff([r['rel_' + k] for r in A], [r['rel_' + k] for r in B], [r['to'] for r in A], [r['to'] for r in B])), n_open=len(A))
        res[label] = out
        print(label, {k: (v['open_minus_veteran'], v['lo'], v['hi'], v['n_open']) for k, v in out.items()})

    compare(lambda r: True, 'all')
    compare(lambda r: r['level'] == 'state', 'state')
    compare(lambda r: r['level'] == 'federal', 'federal')
    compare(lambda r: r['party'] == 'ALP', 'labor_seats')
    compare(lambda r: r['party'] == 'COAL', 'coalition_seats')
    compare(lambda r: r['wins'] >= 3, 'long_serving')
    compare(lambda r: r['wins'] <= 2, 'short_serving')
    # two-party effect with the margin held constant: regress rel_tpp on open + margin (+ election x party already removed)
    R = [r for r in rows if r.get('rel_tpp_party') is not None and r.get('margin') is not None]
    y = np.array([r['rel_tpp_party'] for r in R]); X = np.column_stack([np.ones(len(R)), [r['cat'] == 'open' for r in R], [r['margin'] for r in R]]).astype(float)
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    rng = np.random.default_rng(9); B = []
    for _ in range(1000):
        ix = rng.integers(0, len(R), len(R)); B.append(np.linalg.lstsq(X[ix], y[ix], rcond=None)[0])
    B = np.array(B)
    mo = np.mean([r['margin'] for r in R if r['cat'] == 'open']); mv = np.mean([r['margin'] for r in R if r['cat'] == 'veteran'])
    res['tpp_with_margin'] = dict(open=[round(float(b[1]), 2), round(float(np.percentile(B[:, 1], 5)), 2), round(float(np.percentile(B[:, 1], 95)), 2)],
                                  per_pt_margin=round(float(b[2]), 3), mean_margin_open=round(float(mo), 1), mean_margin_veteran=round(float(mv), 1), n=len(R))
    print('tpp with margin', res['tpp_with_margin'])
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/open_seat_penalty.json'), 'w'), indent=1)
    return res


if __name__ == '__main__':
    main()
