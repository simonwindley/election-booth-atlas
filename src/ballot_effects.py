"""Donkey voting and ballot-position effects, from two independent signals in the Atlas data.

1. First preferences: the candidate drawn first on the ballot gets a bonus. Measured within party x election
   (every candidate's share against their party's mean share that election, with the seat's size of the party
   vote controlled through the party's previous result there), by ballot position.

2. Preferences: when a candidate is excluded, a 1-2-3 voter's ballot goes to the next candidate still standing
   *below* the excluded one on the ballot (a reverse donkey goes to the next one above). The ballot draw is random,
   so "next below" is uncorrelated with party affinity: a fixed-effects regression of the share of the pile going
   to each remaining candidate on (from-party x to-party) effects, the registered card's pick (2022) and
   next-below / next-above indicators gives the donkey share of each pile directly. Done per election, by the
   excluded party, by the number of candidates, and per seat (the seat's excess flow to next-below), which is then
   correlated with the SA1-derived census profile of the seat.

Usage: python3 -m src.ballot_effects      -> raw/pref/ballot_effects.json, site/data/ballot_effects.json
"""
import os, sys, json, gzip, math
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.pref_flows import KEEP  # noqa: E402

ELECTIONS = ['vic2014', 'vic2018', 'vic2022', 'fed2016', 'fed2019', 'fed2022', 'fed2025']


def mparty(p):
    return p if p in KEEP else 'OTH'


def load():
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/dop.json.gz')))
    rows = [dict(zip(d['cols'], r)) for r in d['rows']]
    c = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz')))
    cands = {(r[0], r[2]): dict(zip(c['cols'], r)) for r in c['rows']}
    cc = json.load(gzip.open(os.path.join(ROOT, 'site/data/contest_cand.json.gz')))
    fp = {(r[0], r[2]): r[3] for r in cc['rows']}
    cards = {}
    p = os.path.join(ROOT, 'raw/htv/cards_vic2022.json')
    if os.path.exists(p):
        for reg, e in json.load(open(p))['cards'].items():
            for cid, r in e['contests'].items():
                if r.get('status') == 'complete' and r.get('owner'):
                    cards.setdefault((cid, r['owner']), r['order'])
    return rows, cands, fp, cards


# --------------------------------------------------------------------------- 1. first-preference position effect

def position_effect(cands, fp):
    """share deviation by ballot position, within party x election, for parties with >= 15 candidates"""
    out = {}
    by = defaultdict(list)
    tot = defaultdict(int)
    for (eid, cid_), v in fp.items():
        c = cands.get((eid, cid_))
        if c:
            tot[(eid, c['contest_id'])] += v
    for (eid, cid_), c in cands.items():
        v = fp.get((eid, cid_))
        t = tot.get((eid, c['contest_id']))
        if v is None or not t or not c.get('ballot_position'):
            continue
        n = sum(1 for (e2, x), c2 in cands.items() if e2 == eid and c2['contest_id'] == c['contest_id'])
        by[(eid, c['party'])].append((c['ballot_position'], n, v / t, c['contest_id']))
    for (eid, party), lst in by.items():
        if len(lst) < 15 or party in ('IND', 'OTH'):
            continue
        mean = sum(s for _, _, s, _ in lst) / len(lst)
        pos = defaultdict(list)
        for p, n, s, cid in lst:
            key = 'first' if p == 1 else 'last' if p == n else 'middle'
            pos[key].append(s - mean)
        out.setdefault(eid, {})[party] = {k: {'n': len(v), 'dev_pts': round(100 * sum(v) / len(v), 2)} for k, v in pos.items()}
    # pooled across minor parties (small personal vote), weighted by candidates
    pooled = {}
    for eid in out:
        acc = defaultdict(lambda: [0, 0.0])
        for party, d in out[eid].items():
            if party in ('ALP', 'LIB', 'NAT', 'GRN'):
                continue
            for k, v in d.items():
                acc[k][0] += v['n']; acc[k][1] += v['n'] * v['dev_pts']
        pooled[eid] = {k: {'n': a[0], 'dev_pts': round(a[1] / a[0], 2)} for k, a in acc.items() if a[0]}
    return out, pooled


# --------------------------------------------------------------------------- 2. exclusion-level donkey flow

def exclusions(rows, cands, eid):
    by = defaultdict(list)
    for r in rows:
        if r['election_id'] == eid:
            by[(r['contest_id'], r['count_no'])].append(r)
    for (cid, cn), rs in sorted(by.items()):
        if cn == 0:
            continue
        exc = [r for r in rs if r['transfer'] < 0]
        if len(exc) != 1:
            continue
        x = exc[0]['candidate_id']; out = -exc[0]['transfer']
        remaining = [r['candidate_id'] for r in rs if r['candidate_id'] != x and r['progressive_total'] > 0]
        to = {r['candidate_id']: r['transfer'] for r in rs if r['candidate_id'] != x and r['transfer'] > 0}
        if out > 0 and to and len(remaining) >= 2:
            yield cid, cn, x, out, remaining, to


def donkey_regression(rows, cands, cards, eid):
    """Residual of each remaining candidate's share of the pile against the fitted flow model (party affinity, number of
    candidates), regressed on: next below on the ballot, next above, top of the ballot, and (2022) the card's pick.
    Weighted by the pile. Breakdowns are the mean residual on next-below/next-above rows, net of the constant."""
    PF = json.load(open(os.path.join(ROOT, 'site/data/pref_flows.json')))
    W = (PF['per_election'].get(eid) or {}).get('weights') or PF['blend_2026']['weights']
    def luce(px, rem_parties, pr):
        w = W.get(px) or {}; s = sum(w.get(q, 0.3) for q in rem_parties); return (w.get(pr, 0.3) / s) if s > 0 else 1 / len(rem_parties)
    names = ['below', 'above', 'top', 'card']
    X, Y, Wt, meta = [], [], [], []
    for cid, cn, x, out, remaining, to in exclusions(rows, cands, eid):
        cx = cands.get((eid, x))
        if not cx or not cx.get('ballot_position'):
            continue
        pos = {r: cands[(eid, r)]['ballot_position'] for r in remaining if (eid, r) in cands and cands[(eid, r)].get('ballot_position')}
        if len(pos) < 2:
            continue
        px = cx['ballot_position']; pX = mparty(cx['party'])
        below = [r for r in remaining if pos.get(r, 0) > px]; above = [r for r in remaining if 0 < pos.get(r, 0) < px]
        ind = {'below': min(below, key=lambda r: pos[r]) if below else None, 'above': max(above, key=lambda r: pos[r]) if above else None, 'top': min(pos, key=pos.get)}
        order = cards.get((cid, x)) if eid == 'vic2022' else None
        ind['card'] = next((c for c in order if c != x and c in remaining), None) if order else None
        remP = [mparty(cands[(eid, r)]['party']) for r in remaining]; cnt = Counter(remP)
        n_ballot = sum(1 for (e2, _), c2 in cands.items() if e2 == eid and c2['contest_id'] == cid)
        for r in remaining:
            pr = mparty(cands[(eid, r)]['party'])
            base = luce(pX, set(remP), pr) / cnt[pr]
            X.append([1.0] + [1.0 if ind[k] == r else 0.0 for k in names]); Y.append(to.get(r, 0) / out - base); Wt.append(out)
            meta.append({'seat': cid, 'px': pX, 'n': n_ballot, 'below': ind['below'] == r, 'above': ind['above'] == r})
    k = len(names) + 1
    A = [[sum(w * x[i] * x[j] for x, w in zip(X, Wt)) for j in range(k)] for i in range(k)]; b = [sum(w * x[i] * y for x, y, w in zip(X, Y, Wt)) for i in range(k)]
    use = [i for i in range(k) if A[i][i] > 1e-9]
    sol = solve([[A[i][j] for j in use] for i in use], [b[i] for i in use])
    beta = dict(zip(['const'] + names, [None] * (k)))
    for i, v in zip(use, sol):
        beta[(['const'] + names)[i]] = v
    const = beta['const'] or 0.0
    def adj_excess(filter_fn, which=('below', 'above')):
        """mean residual (net of the constant) over the next-below and next-above rows: the adjacency share of the pile, both sides summed"""
        tot = 0.0; n = 0
        for key in which:
            num = den = 0.0
            for y, w, m in zip(Y, Wt, meta):
                if m[key] and filter_fn(m):
                    num += w * (y - const); den += w; n += 1
            if den:
                tot += num / den
        return (round(tot, 4), n) if n else (None, 0)
    by_party, by_size, by_seat = {}, {}, {}
    for px in sorted({m['px'] for m in meta}):
        v, n = adj_excess(lambda m, px=px: m['px'] == px)
        if n >= 16:
            by_party[px] = {'adjacency': v, 'n': n}
    for lo, hi, lab in ((2, 5, '2-5'), (6, 7, '6-7'), (8, 9, '8-9'), (10, 30, '10+')):
        v, n = adj_excess(lambda m, lo=lo, hi=hi: lo <= m['n'] <= hi)
        if n >= 16:
            by_size[lab] = {'adjacency': v, 'n': n}
    for cid in sorted({m['seat'] for m in meta}):
        v, n = adj_excess(lambda m, cid=cid: m['seat'] == cid)
        if n >= 4:
            by_seat[cid] = {'adjacency': v, 'n': n, 'votes': sum(w for w, m in zip(Wt, meta) if m['seat'] == cid and m['below'])}
    return {'below': round(beta['below'], 4) if beta['below'] is not None else None, 'above': round(beta['above'], 4) if beta['above'] is not None else None,
            'top': round(beta['top'], 4) if beta['top'] is not None else None, 'card': round(beta['card'], 4) if beta['card'] is not None else None,
            'rows': len(X), 'exclusions': sum(1 for m in meta if m['below']) + sum(1 for m in meta if m['above'] and not m['below']),
            'by_party': by_party, 'by_ballot_size': by_size, 'by_seat': by_seat}


def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        if abs(M[i][i]) < 1e-12:
            continue
        for r in range(n):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, n + 1):
                    M[r][c] -= f * M[i][c]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


# --------------------------------------------------------------------------- 3. seats and demographics

def demographics(by_seat_all):
    """pool the seat estimates over the state elections on the 2022 boundaries (2022 only, plus 2018 by name) and
    correlate with census indicators"""
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')))
    dist = d['districts']
    IND = ['english_not_well', 'other_language_home', 'born_overseas', 'bachelor_or_higher', 'year12', 'age_median', 'age_65_plus', 'adults_18_34',
           'income_household_median', 'income_household_under_1000', 'occupation_labourers', 'occupation_professionals', 'religion_no_religion_so_described', 'flat_apartment']
    seats = {}
    for cid, v in by_seat_all.items():
        if cid in dist:
            seats[cid] = v
    out = {'n_seats': len(seats), 'correlations': {}}
    xs = {cid: v['d'] for cid, v in seats.items()}
    for ind in IND:
        pairs = [(dist[cid].get(ind), xs[cid]) for cid in xs if dist[cid].get(ind) is not None]
        if len(pairs) < 20:
            continue
        r = corr([p[0] for p in pairs], [p[1] for p in pairs])
        out['correlations'][ind] = {'r': round(r, 3), 'n': len(pairs)}
    # top and bottom seats
    ranked = sorted(seats.items(), key=lambda kv: -kv[1]['d'])
    out['highest'] = [{'contest': cid, 'name': dist[cid]['name'], 'd': v['d'], 'n': v['n']} for cid, v in ranked[:12]]
    out['lowest'] = [{'contest': cid, 'name': dist[cid]['name'], 'd': v['d'], 'n': v['n']} for cid, v in ranked[-12:][::-1]]
    out['seats'] = {cid: {'d': v['d'], 'n': v['n'], 'name': dist[cid]['name']} for cid, v in seats.items()}
    return out


def corr(x, y):
    n = len(x); mx = sum(x) / n; my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x); syy = sum((b - my) ** 2 for b in y); sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0


def main():
    rows, cands, fp, cards = load()
    pos, pooled = position_effect(cands, fp)
    print('First-preference bonus by ballot position (minor parties pooled, points of the vote, against the party mean):')
    for eid, d in pooled.items():
        print(f"  {eid:8} first {d.get('first', {}).get('dev_pts', float('nan')):+.2f} (n={d.get('first', {}).get('n', 0)})  middle {d.get('middle', {}).get('dev_pts', float('nan')):+.2f}  last {d.get('last', {}).get('dev_pts', float('nan')):+.2f}")
    donkey = {}
    print('\nBallot-position flow at exclusions (share of the pile beyond what party affinity and the card explain):')
    for eid in ELECTIONS:
        if not any(r['election_id'] == eid for r in rows):
            continue
        res = donkey_regression(rows, cands, cards, eid)
        donkey[eid] = res
        print(f"  {eid:8} next below {res['below']:+.3f}  next above {res['above']:+.3f}  top of ballot {res['top']:+.3f}  card {res['card'] if res['card'] is not None else '–'}  ({res['rows']} candidate-exclusions)  adjacency by ballot size: " + ', '.join(f"{k} {v['adjacency']:+.3f}" for k, v in res['by_ballot_size'].items()))
        print('           adjacency by excluded party: ' + ', '.join(f"{k} {v['adjacency']:+.3f} (n={v['n']})" for k, v in sorted(res['by_party'].items(), key=lambda kv: -kv[1]['n'])[:9]))
    # seat pooling over the state elections on the 2022 boundaries: 2022 (own), 2018 by seat name
    pool = defaultdict(lambda: {'num': 0.0, 'den': 0, 'votes': 0})
    for eid in ('vic2022', 'vic2018', 'vic2014'):
        for cid, v in donkey.get(eid, {}).get('by_seat', {}).items():
            pool[cid]['num'] += v['adjacency'] * v['n']; pool[cid]['den'] += v['n']; pool[cid]['votes'] += v['votes']
    by_seat_all = {cid: {'d': round(v['num'] / v['den'], 4), 'n': v['den'], 'votes': v['votes']} for cid, v in pool.items() if v['den'] >= 8}
    demo = demographics(by_seat_all)
    print(f"\nSeat-level ballot-adjacency share (state elections pooled, {demo['n_seats']} seats): correlations with the census profile")
    for k, v in sorted(demo['correlations'].items(), key=lambda kv: -abs(kv[1]['r'])):
        print(f"  {k:36} r = {v['r']:+.2f}")
    print('  highest: ' + ', '.join(f"{s['name']} {100 * s['d']:.1f}%" for s in demo['highest'][:8]))
    print('  lowest:  ' + ', '.join(f"{s['name']} {100 * s['d']:.1f}%" for s in demo['lowest'][:8]))
    num = {'below': 0.0, 'above': 0.0, 'top': 0.0}; den = 0
    for eid, r in donkey.items():
        for k in num:
            num[k] += (r[k] or 0) * r['rows']
        den += r['rows']
    model = {k: round(num[k] / den, 4) for k in num}   # pooled over every election, weighted by observations: what the browser model applies
    print('\nModel terms (pooled):', model)
    out = {'position': {'by_party': pos, 'pooled_minor': pooled}, 'donkey': donkey, 'seats': demo, 'model': model,
           'note': 'below/above/top: the share of an excluded candidate\'s pile that goes to the next candidate below (above) on the ballot, or the top of the ballot, beyond what the fitted flows (party affinity) and the registered card explain. Seat values are the adjacency share (below plus above), pooling the state elections.'}
    os.makedirs(os.path.join(ROOT, 'raw/pref'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'raw/pref/ballot_effects.json'), 'w'), indent=0)
    slim = {'position': pooled, 'donkey': {e: {k: v for k, v in r.items() if k != 'by_seat'} for e, r in donkey.items()}, 'seats': demo, 'note': out['note'], 'model': model,
            'model_note': 'share of an excluded candidate\'s pile given to the next candidate below / above on the ballot and to the top of the ballot, beyond the fitted flows; pooled over every election, weighted by observations'}
    json.dump(slim, open(os.path.join(ROOT, 'site/data/ballot_effects.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
