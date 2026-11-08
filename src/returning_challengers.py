"""Returning challengers: candidates who lost a seat and come back to contest it again, sometimes again and again.

For every seat contested at two consecutive general elections of the same level (state 2002-2022, federal 2007-2025),
each party that lost the seat last time and stands again is followed. Its candidate is either:

  new         someone else
  second go   the same person who lost last time (same surname and given name, same party group)
  third+ go   the same person, who had also lost the time before (or more)

Opponent: the sitting member standing again ('v member') or not ('open seat': retired, lost preselection, moved).
Whether that member is a first-termer (who enjoys the sophomore surge) is controlled for.

  1. Vote: the challenging party's first-preference change in the seat (notional where boundaries changed), against the
     same party's other seats it was challenging at that election (election x party effects), by candidate type and
     opponent, with a bootstrap over seats.
  2. Winning: Labor and Coalition challengers in Labor v Coalition seats, chance of winning given the two-party
     margin they faced and the statewide swing, with and without a returning candidate.
  3. The other side: does the sitting member's vote move differently when the same challenger comes back?
  4. Independents and Greens who stand again: what happens to their own vote on the second and later tries.
  Former members (lost the seat last time, after holding it) trying to win it back are flagged separately.
  5. 2026: who is coming back (declared candidates against the 2022 and earlier ballots).

Inputs  data/elections.sqlite, data/analysis/member_history.csv, data/analysis/notionals.json, data/vic2026/candidates.csv
Output  data/analysis/returning_challengers.json
Usage   python3 -m src.returning_challengers
"""
import os, re, csv, json, sqlite3, math
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES = {'state': ['vic1999', 'vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022'],
          'federal': ['fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025']}
GROUP = {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL'}


def norm(s):
    return re.sub(r'[^a-z]', '', (s or '').lower())


def key(sur, giv):
    g = norm((giv or '').split()[0] if (giv or '').split() else '')
    return (norm(sur), g[:3])


def load(c):
    """cand[(eid, seat)] = [{key, name, grp, party, el, share}] ; formal by seat"""
    name = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    votes = defaultdict(float); tot = defaultdict(float)
    for e, cid, k, v in c.execute("select election_id, contest_id, candidate_id, sum(votes) from fp_votes where candidate_id <> 'INFORMAL' group by 1, 2, 3"):
        votes[(e, k)] += v or 0; tot[(e, name.get((e, cid)))] += v or 0
    cand = defaultdict(list)
    for e, cid, k, sur, giv, p, el in c.execute('select election_id, contest_id, candidate_id, surname, given_name, party, elected from candidates'):
        s = name.get((e, cid))
        if not s:
            continue
        cand[(e, s)].append({'key': key(sur, giv), 'name': f'{giv} {sur}'.strip(), 'grp': GROUP.get(p, p) or 'OTH', 'party': p, 'el': bool(el), 'votes': votes[(e, k)]})
    for (e, s), L in cand.items():
        t = tot[(e, s)] or 1
        for x in L:
            x['share'] = x['votes'] / t
    return cand


def notional_group(c):
    out = {}
    for rd in json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']:
        for s in rd['seats']:
            g = defaultdict(float)
            for p, v in s['fp'].items():
                g[GROUP.get(p, p)] += v
            out[(rd['for'], s['seat'])] = (dict(g), s['alp_2pp'])
    return out


def tcp(c):
    name = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    party = {(e, k): GROUP.get(p, p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    t = defaultdict(lambda: defaultdict(float))
    for e, cid, k, v in c.execute('select election_id, contest_id, candidate_id, sum(votes) from tcp_votes group by 1, 2, 3'):
        t[(e, name.get((e, cid)))][party.get((e, k), 'OTH')] += v or 0
    return {k: d['ALP'] / (d['ALP'] + d['COAL']) for k, d in t.items() if set(d) == {'ALP', 'COAL'}}


def build(c):
    cand = load(c); NOT = notional_group(c); T = tcp(c)
    hist = {(h['to'], h['seat']): h for h in csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv')))}
    rows, ind_rows = [], []
    for level, ser in SERIES.items():
        for i in range(1, len(ser)):
            t0, t1 = ser[i - 1], ser[i]
            # statewide two-party swing to Labor (classic seats both times; notional where redrawn)
            sw = [T[(t1, s)] - (NOT[(t1, s)][1] if (t1, s) in NOT else T.get((t0, s), np.nan)) for (e, s) in T if e == t1]
            sw = float(np.nanmean(sw)) if sw else 0.0
            for (e, s), L1 in list(cand.items()):
                if e != t1 or (t0, s) not in cand:
                    continue
                L0 = cand[(t0, s)]
                win0 = next((x for x in L0 if x['el']), None)
                if not win0:
                    continue
                g0 = NOT[(t1, s)][0] if (t1, s) in NOT else defaultdict(float)
                if (t1, s) not in NOT:
                    for x in L0:
                        g0[x['grp']] += x['share']
                h = hist.get((t1, s)); cat = (h['category'] or 'unknown') if h else 'unknown'
                opp = 'member' if cat in ('veteran', 'sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'unknown') else ('open' if cat == 'open' else None)
                mem_grp = h['party'] if h else win0['grp']
                for x1 in L1:
                    P = x1['grp']
                    if P == mem_grp or P in ('OTH',):
                        continue
                    if P == 'IND':
                        # independents: the same person standing again in the seat
                        prev = next((x for x in L0 if x['grp'] == 'IND' and x['key'] == x1['key']), None)
                        if prev and not prev['el']:
                            former = i >= 2 and any(x['key'] == x1['key'] and x['el'] for x in cand.get((ser[i - 2], s), []))
                            n = 1; j = i - 2
                            while j >= 0 and any(x['grp'] == 'IND' and x['key'] == x1['key'] and not x['el'] for x in cand.get((ser[j], s), [])):
                                n += 1; j -= 1
                            ind_rows.append({'level': level, 'from': t0, 'to': t1, 'seat': s, 'name': x1['name'], 'try': n + 1, 'share0': prev['share'], 'share1': x1['share'], 'won': x1['el'], 'opp': opp, 'former_member': former})
                        continue
                    lost0 = [x for x in L0 if x['grp'] == P and not x['el']]
                    if not lost0:
                        continue
                    same = next((x for x in lost0 if x['key'] == x1['key']), None)
                    tries = 0
                    if same:
                        tries = 1; j = i - 2
                        while j >= 0 and any(x['grp'] == P and x['key'] == x1['key'] and not x['el'] for x in cand.get((ser[j], s), [])):
                            tries += 1; j -= 1
                    former = bool(same) and i >= 2 and any(x['key'] == x1['key'] and x['el'] for x in cand.get((ser[i - 2], s), []))
                    s1 = sum(x['share'] for x in L1 if x['grp'] == P)
                    r = {'level': level, 'from': t0, 'to': t1, 'seat': s, 'party': P, 'candidate': x1['name'], 'type': 'new' if not tries else ('second' if tries == 1 else 'third_plus'),
                         'tries_before': tries, 'opp': opp, 'opp_category': cat, 'share0': g0.get(P, 0), 'share1': s1, 'change': s1 - g0.get(P, 0), 'won': x1['el'], 'member_party': mem_grp, 'former_member': former,
                         'redrawn': (t1, s) in NOT}
                    # two-party margin faced (Labor v Coalition seats), and the swing to the challenger's party
                    if P in ('ALP', 'COAL') and mem_grp in ('ALP', 'COAL'):
                        a0 = NOT[(t1, s)][1] if (t1, s) in NOT else T.get((t0, s))
                        if a0 is not None:
                            r['deficit'] = (0.5 - a0) if P == 'ALP' else (a0 - 0.5)
                            r['swing'] = sw if P == 'ALP' else -sw
                    rows.append(r)
    return rows, ind_rows, cand


def fe_fit(rows, xs, rng=None):
    """change = a[election, party] + sum b_k x_k ; returns b"""
    if rng is not None:
        by = defaultdict(list)
        for r in rows:
            by[r['to']].append(r)
        rows = [by[k][j] for k in by for j in rng.integers(0, len(by[k]), len(by[k]))]
    cells = sorted({(r['to'], r['party']) for r in rows}); ci = {k: i for i, k in enumerate(cells)}
    X = np.zeros((len(rows), len(cells) + len(xs))); y = np.array([r['change'] for r in rows])
    for n, r in enumerate(rows):
        X[n, ci[(r['to'], r['party'])]] = 1
        for j, f in enumerate(xs):
            X[n, len(cells) + j] = f(r)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b[len(cells):]


def boot(rows, xs, names, n=1000, seed=4):
    b = fe_fit(rows, xs); rng = np.random.default_rng(seed)
    B = np.array([fe_fit(rows, xs, rng) for _ in range(n)])
    return {nm: {'pts': round(100 * float(b[j]), 2), 'lo': round(100 * float(np.percentile(B[:, j], 5)), 2), 'hi': round(100 * float(np.percentile(B[:, j], 95)), 2)} for j, nm in enumerate(names)}


def logit(X, y, ridge=1e-3):
    b = np.zeros(X.shape[1]); R = ridge * np.eye(X.shape[1]); R[0, 0] = 0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        step = np.linalg.solve((X * (p * (1 - p))[:, None]).T @ X + R, X.T @ (y - p) - R @ b); b += step
        if np.abs(step).max() < 1e-9:
            break
    return b


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    rows, ind_rows, cand = build(c)
    res = {'method': __doc__.split('\n\n')[1].strip()}
    from collections import Counter
    res['counts'] = {f'{p} {t} v {o}': n for (p, t, o), n in Counter((r['party'], r['type'], r['opp']) for r in rows if r['opp']).items()}
    print('challengers:', Counter((r['type'], r['opp']) for r in rows))
    out = {}
    for lab, sub in (('ALP+COAL', [r for r in rows if r['party'] in ('ALP', 'COAL') and r['opp']]), ('GRN', [r for r in rows if r['party'] == 'GRN' and r['opp']]),
                     ('ALP+COAL state', [r for r in rows if r['party'] in ('ALP', 'COAL') and r['opp'] and r['level'] == 'state']),
                     ('ALP+COAL federal', [r for r in rows if r['party'] in ('ALP', 'COAL') and r['opp'] and r['level'] == 'federal'])):
        xs = [lambda r: r['type'] == 'second' and r['opp'] == 'member', lambda r: r['type'] == 'third_plus' and r['opp'] == 'member',
              lambda r: r['opp'] == 'open', lambda r: r['type'] != 'new' and r['opp'] == 'open',
              lambda r: r['opp_category'] == 'sophomore_gain', lambda r: r['opp_category'] in ('sophomore_held', 'sophomore_byelection')]
        names = ['second_v_member', 'third_plus_v_member', 'open_seat', 'returning_in_open_seat', 'v_first_term_member_who_won_it', 'v_other_first_term_member']
        out[lab] = {'n': len(sub), 'n_second': sum(r['type'] == 'second' for r in sub), 'n_third_plus': sum(r['type'] == 'third_plus' for r in sub),
                    'n_open': sum(r['opp'] == 'open' for r in sub), 'n_returning_open': sum(r['type'] != 'new' and r['opp'] == 'open' for r in sub), **boot(sub, xs, names)}
        print(f"{lab} (n={len(sub)}): " + '  '.join(f"{k} {out[lab][k]['pts']:+.1f} [{out[lab][k]['lo']:+.1f},{out[lab][k]['hi']:+.1f}]" for k in names))
    res['vote'] = out
    # by whether the returning candidate came close last time
    maj = [r for r in rows if r['party'] in ('ALP', 'COAL') and r['opp'] == 'member' and 'deficit' in r]
    close = boot([dict(r) for r in maj], [lambda r: r['type'] != 'new' and r['deficit'] < 0.04, lambda r: r['type'] != 'new' and r['deficit'] >= 0.04],
                 ['returning_close_last_time', 'returning_not_close'])
    res['vote_by_closeness'] = close
    fm = boot([r for r in rows if r['party'] in ('ALP', 'COAL') and r['opp']], [lambda r: r['former_member'], lambda r: r['type'] != 'new' and not r['former_member'], lambda r: r['opp_category'] == 'sophomore_gain',
              lambda r: r['opp_category'] in ('sophomore_held', 'sophomore_byelection'), lambda r: r['opp'] == 'open'], ['former_member_back', 'other_returning', 'v_first_term_member_who_won_it', 'v_other_first_term_member', 'open_seat'])
    fm['n_former'] = sum(r['former_member'] and r['party'] in ('ALP', 'COAL') for r in rows); fm['former_won'] = sum(r['former_member'] and r['won'] and r['party'] in ('ALP', 'COAL') for r in rows)
    fm['cases'] = [{k: r[k] for k in ('to', 'seat', 'candidate', 'party', 'won')} | {'change_pts': round(100 * r['change'], 1)} for r in rows if r['former_member']]
    res['former_members'] = fm
    print('   former members trying to win back their seat:', {k: v for k, v in fm.items() if k != 'cases'})
    print('   by closeness last time (v member): ' + '  '.join(f"{k} {v['pts']:+.1f} [{v['lo']:+.1f},{v['hi']:+.1f}]" for k, v in close.items()))
    # 2. winning: logit on deficit, swing, returning, open
    W = [r for r in rows if r['party'] in ('ALP', 'COAL') and 'deficit' in r and r['opp']]
    y = np.array([r['won'] for r in W], float)
    X = np.column_stack([np.ones(len(W)), [100 * r['deficit'] for r in W], [100 * r['swing'] for r in W], [r['type'] != 'new' for r in W], [r['opp'] == 'open' for r in W]]).astype(float)
    b = logit(X, y)
    rng = np.random.default_rng(9); bs = []
    for _ in range(600):
        i = rng.integers(0, len(W), len(W)); bs.append(logit(X[i], y[i]))
    bs = np.array(bs)
    res['winning'] = {'n': len(W), 'wins': int(y.sum()), 'per_pt_deficit': round(float(b[1]), 3), 'per_pt_swing': round(float(b[2]), 3),
                      'returning_odds_ratio': round(math.exp(b[3]), 2), 'returning_ci': [round(math.exp(float(np.percentile(bs[:, 3], 5))), 2), round(math.exp(float(np.percentile(bs[:, 3], 95))), 2)],
                      'returning_worth_pts': round(float(b[3] / -b[1]), 2), 'open_odds_ratio': round(math.exp(b[4]), 2),
                      'open_ci': [round(math.exp(float(np.percentile(bs[:, 4], 5))), 2), round(math.exp(float(np.percentile(bs[:, 4], 95))), 2)]}
    print('winning:', res['winning'])
    # win rates by type and opponent, within 6 points
    res['win_rates'] = []
    for t in ('new', 'second', 'third_plus'):
        for o in ('member', 'open'):
            s = [r for r in W if r['type'] == t and r['opp'] == o and r['deficit'] < 0.06]
            res['win_rates'].append({'type': t, 'opp': o, 'n': len(s), 'won': sum(r['won'] for r in s)})
    # 3. the member's side: member party change when the same challenger returns (members standing again)
    mem = []
    seen = set()
    for r in rows:
        if r['opp'] != 'member' or r['party'] not in ('ALP', 'COAL') or r['member_party'] not in ('ALP', 'COAL') or (r['to'], r['seat']) in seen:
            continue
        seen.add((r['to'], r['seat']))
        mem.append(r)
    # member party's own change: from the opposite numbers in the rows' seats
    mrows = []
    for r in mem:
        L1 = cand[(r['to'], r['seat'])]
        s1 = sum(x['share'] for x in L1 if x['grp'] == r['member_party'])
        g0 = r['share0']  # challenger's; need member's: recompute
        mrows.append({'to': r['to'], 'party': r['member_party'], 'change': None, 'returning': r['type'] != 'new', 'seat': r['seat'], 's1': s1})
    NOT = notional_group(c)
    for m in mrows:
        ser = SERIES['federal' if m['to'].startswith('fed') else 'state']; t0 = ser[ser.index(m['to']) - 1]
        if (m['to'], m['seat']) in NOT:
            s0 = NOT[(m['to'], m['seat'])][0].get(m['party'], 0)
        else:
            s0 = sum(x['share'] for x in cand[(t0, m['seat'])] if x['grp'] == m['party'])
        m['change'] = m['s1'] - s0
    res['member_side'] = boot(mrows, [lambda r: r['returning']], ['returning_challenger'])
    print('member party change when the challenger returns:', res['member_side'])
    # 4. independents standing again
    res['independents'] = []
    for t in (2, 3):
        s = [r for r in ind_rows if (r['try'] == t if t == 2 else r['try'] >= 3)]
        if s:
            d = np.array([r['share1'] - r['share0'] for r in s])
            res['independents'].append({'try': '2nd' if t == 2 else '3rd+', 'n': len(s), 'mean_change_pts': round(100 * float(d.mean()), 2), 'median_change_pts': round(100 * float(np.median(d)), 2),
                                        'share_up': round(float((d > 0).mean()), 2), 'won': sum(r['won'] for r in s),
                                        'strong_10plus': {'n': sum(r['share0'] >= .1 for r in s), 'mean_change_pts': round(100 * float(np.mean([r['share1'] - r['share0'] for r in s if r['share0'] >= .1])), 2) if any(r['share0'] >= .1 for r in s) else None,
                                                          'won': sum(r['won'] for r in s if r['share0'] >= .1)}})
    res['independent_rows'] = sorted([dict(r, share0=round(r['share0'], 4), share1=round(r['share1'], 4)) for r in ind_rows if r['share0'] >= .08], key=lambda r: -r['share0'])
    print('independents again:', res['independents'])
    # 5. 2026
    res['returning_2026'] = outlook_2026(c, cand, res)
    res['rows'] = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows if r['type'] != 'new']
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/returning_challengers.json'), 'w'), indent=1)


def outlook_2026(c, cand, res):
    me = {m['seat']: m for m in json.load(open(os.path.join(ROOT, 'data/analysis/member_effects.json')))['outlook_2026']}
    cid_name = {cid: nm for cid, nm in c.execute("select contest_id, contest_name from contests where election_id = 'vic2022'")}
    ser = SERIES['state']; out = []
    for r in csv.DictReader(open(os.path.join(ROOT, 'data/vic2026/candidates.csv'))):
        if r['incumbent'] == '1':
            continue
        s = cid_name.get(r['contest_id']) or r['contest_id']
        parts = r['name'].split(); k = key(parts[-1], parts[0])
        grp = GROUP.get(r['party'], r['party'])
        tries, hist = 0, []
        for e in reversed(ser):
            hit = next((x for x in cand.get((e, s), []) if x['key'] == k), None)
            if not hit:
                break
            hist.append({'election': e, 'party': hit['party'], 'share': round(hit['share'], 4), 'won': hit['el']})
            if hit['el']:
                break
            tries += 1
        if not tries:
            # anywhere else in the 2022 or 2018 ballots? (moved seats)
            other = [(e, s2) for (e, s2), L in cand.items() if e in ('vic2022', 'vic2018') and s2 != s and any(x['key'] == k and x['grp'] == grp for x in L)]
            if other:
                out.append({'seat': s, 'candidate': r['name'], 'party': r['party'], 'tries_in_seat': 0, 'previously_stood': sorted(set(f'{s2} {e[-4:]}' for e, s2 in other)), 'opponent': opp_label(me.get(s), grp)})
            continue
        out.append({'seat': s, 'candidate': r['name'], 'party': r['party'], 'tries_in_seat': tries, 'history': hist, 'last_share': hist[0]['share'] if hist else None, 'opponent': opp_label(me.get(s), grp)})
    print(f"2026: {sum(1 for o in out if o['tries_in_seat'])} declared candidates coming back to the same seat ({sum(1 for o in out if o['tries_in_seat'] >= 2)} for a third or later go); {sum(1 for o in out if not o['tries_in_seat'])} who stood elsewhere before")
    return sorted(out, key=lambda o: (-(o.get('last_share') or 0)))


def opp_label(m, grp):
    if not m:
        return None
    if GROUP.get(m['party'], m['party']) == grp:
        return 'own party holds'
    return 'open seat' if m['category'] == 'open' else 'member standing again'


if __name__ == '__main__':
    main()
