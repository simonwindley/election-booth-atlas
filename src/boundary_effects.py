"""Boundary effects: what redistributions do to seats, margins and members, from the notional results (src.notional).

  1. Check: our notional two-party margins against Antony Green's published ones (2022 state, 2025 federal).
  2. What each redistribution did: seats abolished and created, how much of each seat came from its namesake, how far
     notional margins moved, and which seats changed hands on paper.
  3. Notional flips: when a redistribution hands a seat to the other side on paper, does that side win it?
  4. The cost of new territory: a member standing again in a redrawn seat, compared with the notional result. The
     seat's swing (actual two-candidate minus notional two-party, Labor v Coalition contests) relative to the statewide
     swing on the same basis, against the share of the new seat that came from another party's seat and from a
     same-party colleague's seat. The member's own old voters carry their personal vote; new ones should not.

Inputs  data/analysis/notionals.json, data/analysis/member_history.csv, data/elections.sqlite, raw/reference/notional_margins_green.json
Output  data/analysis/boundary_effects.json
Usage   python3 -m src.boundary_effects
"""
import os, re, csv, json, sqlite3
from collections import defaultdict
import math
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUP = {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL'}


def norm(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


def actual_2cp(c, eid):
    """{seat name: (ALP share of the final two, pair)}"""
    name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (eid,))}
    party = {k: GROUP.get(p, p) for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (eid,))}
    t = defaultdict(lambda: defaultdict(float))
    for cid, k, v in c.execute('select contest_id, candidate_id, sum(votes) from tcp_votes where election_id = ? group by 1, 2', (eid,)):
        t[name.get(cid)][party.get(k, 'OTH')] += v or 0
    return {nm: (d.get('ALP', 0) / sum(d.values()) if set(d) == {'ALP', 'COAL'} else None, tuple(sorted(d))) for nm, d in t.items() if sum(d.values())}


def validate(N):
    p = os.path.join(ROOT, 'raw/reference/notional_margins_green.json')
    if not os.path.exists(p):
        return None
    ref = json.load(open(p)); out = {'source': ref['source']}
    for e in ('vic2022', 'fed2025'):
        rows = []
        for s, v in ref[e].items():
            if v['holder'] in ('ALP', 'COAL') and v['vs'] in ('ALP', 'COAL') and v['margin'] is not None and s in N[e]:
                g = 50 + v['margin'] if v['holder'] == 'ALP' else 50 - v['margin']
                rows.append({'seat': s, 'green': round(g, 2), 'atlas': round(100 * N[e][s]['alp_2pp'], 2)})
        d = np.array([r['atlas'] - r['green'] for r in rows])
        out[e] = {'seats': len(rows), 'mean_diff': round(float(d.mean()), 2), 'mean_abs_diff': round(float(np.abs(d).mean()), 2),
                  'within_1pt': int((np.abs(d) <= 1).sum()), 'largest': sorted(rows, key=lambda r: -abs(r['atlas'] - r['green']))[:5],
                  'holder_disagree': [r for r in rows if (r['atlas'] >= 50) != (r['green'] >= 50)], 'rows': rows}
        print(f"check {e}: {len(rows)} seats, mean difference {d.mean():+.2f}, mean absolute {np.abs(d).mean():.2f} pts, {out[e]['within_1pt']} within 1 pt")
    return out


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    NR = json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']
    N = {r['for']: {s['seat']: s for s in r['seats']} for r in NR}
    res = {'method': __doc__.split('\n\n')[1].strip(), 'check': validate(N), 'redistributions': [], 'flips': [], 'territory': {}}
    hist = list(csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv'))))
    terr = []
    for rd in NR:
        t0, t1 = rd['from'], rd['for']
        act = actual_2cp(c, t1); old = rd['old_seats']
        # statewide swing on the notional basis: mean of actual minus notional over Labor v Coalition seats
        sw = [act[s['seat']][0] - s['alp_2pp'] for s in rd['seats'] if s['seat'] in act and act[s['seat']][0] is not None]
        swing = float(np.mean(sw)) if sw else 0.0
        shifts, flips = [], []
        for s in rd['seats']:
            o = old.get(s['seat'])
            prev_holder = o['holder'] if o else (s['sources'][0]['holder'] if s['sources'] else None)
            if o and o['holder'] in ('ALP', 'COAL'):
                shifts.append(s['alp_2pp'] - o['alp_2pp'])
            if s['holder'] in ('ALP', 'COAL') and prev_holder in ('ALP', 'COAL') and s['holder'] != prev_holder:
                f = {'for': t1, 'seat': s['seat'], 'new_seat': o is None, 'was': prev_holder, 'notional': s['holder'], 'notional_margin_pts': round(100 * s['margin_2pp'], 2),
                     'winner': s['actual_winner'], 'notional_party_won': s['actual_winner'] == s['holder'],
                     'swing_to_notional_party_pts': round(100 * swing * (1 if s['holder'] == 'ALP' else -1), 2)}
                # chance the notional party wins on uniform swing, seats scattering by 3.25 pts (src.seat_loss)
                z = (100 * s['margin_2pp'] + f['swing_to_notional_party_pts']) / 3.25
                f['p_uniform'] = round(0.5 * (1 + math.erf(z / math.sqrt(2))), 3)
                flips.append(f)
        res['flips'] += flips
        heavy = [s for s in rd['seats'] if s['same_name_share'] < 0.7]
        summ = {'from': t0, 'for': t1, 'seats': len(rd['seats']), 'abolished': rd['abolished'], 'created': rd['created'], 'swing_on_notional_pts': round(100 * swing, 2),
                'median_from_namesake': round(float(np.median([s['same_name_share'] for s in rd['seats'] if s['seat'] in old])), 3) if old else None,
                'heavily_redrawn': sorted(s['seat'] for s in heavy if s['seat'] in old), 'mean_abs_shift_pts': round(100 * float(np.mean(np.abs(shifts))), 2) if shifts else None,
                'largest_shifts': sorted([{'seat': s['seat'], 'old': round(100 * old[s['seat']]['alp_2pp'], 1), 'notional': round(100 * s['alp_2pp'], 1)} for s in rd['seats'] if s['seat'] in old and old[s['seat']]['holder'] in ('ALP', 'COAL')],
                                         key=lambda x: -abs(x['notional'] - x['old']))[:6],
                'notional_flips': len(flips), 'flips_won_by_notional_party': sum(f['notional_party_won'] for f in flips)}
        res['redistributions'].append(summ)
        print(f"{t1}: {summ['seats']} seats, {len(summ['abolished'])} abolished, median {summ['median_from_namesake']} from namesake, mean shift {summ['mean_abs_shift_pts']} pts, "
              f"{len(flips)} notional flips ({summ['flips_won_by_notional_party']} won by the notional party); swing on notional {100 * swing:+.1f}")
        # members standing again for the same-named seat
        for h in hist:
            if h['to'] != t1 or h['category'] not in ('veteran', 'sophomore_gain', 'sophomore_held', 'sophomore_byelection', '') or h['party'] not in ('ALP', 'COAL'):
                continue
            s = N[t1].get(h['seat'])
            if not s or h['seat'] not in act or act[h['seat']][0] is None:
                continue
            sur = norm(h['member'].split()[-1]); sign = 1 if h['party'] == 'ALP' else -1
            own = sum(x['share'] for x in s['sources'] if norm(x['member'] or '').endswith(sur))
            other = sum(x['share'] for x in s['sources'] if x['holder'] != h['party'] and not norm(x['member'] or '').endswith(sur))
            same = 1 - own - other
            if own < 0.2:                      # the member's old seat is not really in it: they have moved
                continue
            terr.append({'for': t1, 'seat': h['seat'], 'member': h['member'], 'party': h['party'], 'category': h['category'] or 'unknown_tenure',
                         'own': round(own, 3), 'same_party': round(max(0.0, same), 3), 'other_party': round(other, 3),
                         'swing_rel': sign * ((act[h['seat']][0] - s['alp_2pp']) - swing), 'held': h['held'] == 'True'})
    # regression: relative swing ~ a + b_other * other_party + b_same * same_party
    y = np.array([t['swing_rel'] for t in terr]); X = np.column_stack([np.ones(len(terr)), [t['other_party'] for t in terr], [t['same_party'] for t in terr]])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    rng = np.random.default_rng(3); bs = []
    for _ in range(2000):
        i = rng.integers(0, len(y), len(y)); bs.append(np.linalg.lstsq(X[i], y[i], rcond=None)[0])
    bs = np.array(bs)
    ci = lambda j: [round(100 * float(np.percentile(bs[:, j], 5)), 2), round(100 * float(np.percentile(bs[:, j], 95)), 2)]
    groups = {}
    for lab, cond in (('mostly own (90%+)', lambda t: t['own'] >= .9), ('some new (70-90%)', lambda t: .7 <= t['own'] < .9), ('much new (<70%)', lambda t: t['own'] < .7)):
        s_ = [t for t in terr if cond(t)]
        groups[lab] = {'n': len(s_), 'mean_rel_swing_pts': round(100 * float(np.mean([t['swing_rel'] for t in s_])), 2) if s_ else None}
    res['territory'] = {'n': len(terr), 'intercept_pts': round(100 * float(b[0]), 2), 'other_party_pts_per_100pct': round(100 * float(b[1]), 2), 'other_ci': ci(1),
                        'same_party_pts_per_100pct': round(100 * float(b[2]), 2), 'same_ci': ci(2), 'by_own_share': groups,
                        'rows': sorted(terr, key=lambda t: t['own'])}
    print(f"new territory (n={len(terr)}): relative swing = {100 * b[0]:+.1f} {100 * b[1]:+.1f} x share from other party's seats [{ci(1)[0]:+.1f}, {ci(1)[1]:+.1f}] "
          f"{100 * b[2]:+.1f} x share from same-party colleagues [{ci(2)[0]:+.1f}, {ci(2)[1]:+.1f}] (pts per 100%)")
    print('   by share of the seat that is the member\'s own: ' + '; '.join(f"{k}: n={v['n']} {v['mean_rel_swing_pts']:+.1f}" for k, v in groups.items()))
    fl = res['flips']
    res['flips_summary'] = {'n': len(fl), 'won_by_notional_party': sum(f['notional_party_won'] for f in fl), 'expected_on_uniform_swing': round(sum(f['p_uniform'] for f in fl), 1),
                            'median_notional_margin_pts': round(float(np.median([f['notional_margin_pts'] for f in fl])), 2) if fl else None}
    print(f"notional flips: {res['flips_summary']}")
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/boundary_effects.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
