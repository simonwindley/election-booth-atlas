"""Primary swings: what first-preference swings tell us seat by seat, when a two-party swing may not.

1. Uniform or proportional? For Labor, the Coalition, the Greens and everyone else, at every pair of consecutive
   elections (state 2002-2022, federal 2007-2025; notional first preferences where boundaries changed), a seat's
   change is compared with two rules: uniform (every seat moves by the statewide change) and proportional (every seat
   moves by the same ratio, so more where the party was stronger). lambda = 0 is uniform, 1 is proportional, fitted
   per party group; each rule is scored by how well it predicts seats from the true statewide result, one election
   held out at a time.
2. Where do minor-party surges land? The same test for One Nation, using its Senate vote at every booth (2019, 2022,
   2025 federal), where it stood everywhere; and One Nation's 2022 Legislative Council vote by district, its only
   statewide state result, as the map of where it starts.
3. From primaries to seats. 2026 seat primaries are projected from 2022 by the rule each party follows, to the
   latest polls; then a preference count is run in each seat (lowest excluded first, votes passed on by the Atlas's
   preference-flow model) to find the final two and the winner. Backtested first: 2018->2022 state and 2022->2025
   federal, given the true statewide primaries, against a uniform two-party swing given the true two-party swing.
   Both are run with and without the member effects (sophomore surge, open-seat penalty), and an independent's vote
   is carried forward only if the same independent stands again (known once nominations close).

Inputs  data/elections.sqlite, data/analysis/notionals.json, site/data/pref_flows.json, site/data/polls_vic2026.json
Output  data/analysis/primary_swings.json
Usage   python3 -m src.primary_swings
"""
import os, json, sqlite3, datetime as dt, math
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES = {'state': ['vic1999', 'vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022'],
          'federal': ['fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025']}
GROUPS = ['ALP', 'COAL', 'GRN', 'OTHERS']                     # OTHERS = everyone else
COUNT_GROUPS = ['ALP', 'LIB', 'NAT', 'GRN', 'ONP', 'IND', 'OTH']


def g4(p):
    return {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL'}.get(p, p) if p in ('ALP', 'LIB', 'NAT', 'LCP', 'GRN') else 'OTHERS'


def g7(p):
    return 'LIB' if p == 'LCP' else (p if p in COUNT_GROUPS else 'OTH')


def seat_fp(c, eid):
    """{seat name: {party: votes}}"""
    name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (eid,))}
    party = {k: p for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (eid,))}
    out = defaultdict(lambda: defaultdict(float)); best_ind = defaultdict(lambda: defaultdict(float))
    for cid, k, v in c.execute("select contest_id, candidate_id, sum(votes) from fp_votes where election_id = ? and candidate_id <> 'INFORMAL' group by 1, 2", (eid,)):
        p = party.get(k) or 'OTH'
        out[name.get(cid)][p] += v or 0
        if p == 'IND':
            best_ind[name.get(cid)][k] += v or 0
    # keep the strongest independent as IND and fold the rest into OTH (a seat's IND vote is one candidate's, not a bloc)
    for nm, d in out.items():
        if best_ind[nm]:
            top = max(best_ind[nm].values()); d['OTH'] += d['IND'] - top; d['IND'] = top
    return out


def ind_names(c, eid):
    """{seat: (surname of the strongest independent, set of independents' surnames)}"""
    name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (eid,))}
    v = defaultdict(dict)
    for cid, sur, k in c.execute("select k.contest_id, k.surname, sum(f.votes) from candidates k join fp_votes f on f.election_id = k.election_id and f.candidate_id = k.candidate_id where k.election_id = ? and k.party = 'IND' group by k.candidate_id", (eid,)):
        v[name.get(cid)][(sur or '').lower()] = k or 0
    return {s_: (max(d, key=d.get), set(d)) for s_, d in v.items() if d}


def drop_ind(base, keep):
    """an independent who is not standing again: their vote is spread over everyone else"""
    if keep or not base.get('IND'):
        return base
    b = dict(base); v = b.pop('IND'); t = sum(b.values())
    return {g: x + v * x / t for g, x in b.items()}             # spread over everyone else in proportion


def member_adjust(pr, party, cat, eff):
    """add the member effect (pts of first preferences) to the member's party, then renormalise"""
    if not party or cat not in eff:
        return pr
    k = party if party in pr else ({'COAL': next((g for g in ('LIB', 'NAT') if g in pr), None)}.get(party))
    if not k:
        return pr
    p = dict(pr); p[k] = max(0.0, p[k] + eff[cat] / 100); t = sum(p.values())
    return {g: v / t for g, v in p.items()}


def shares(d, grp):
    tot = sum(d.values()); g = defaultdict(float)
    for p, v in d.items():
        g[grp(p)] += v / tot if tot else 0
    return g


def pairs(c):
    """(t0, t1, {seat: (s0 by party votes, s1 by party votes)}) with notional t0 where boundaries changed"""
    NOT = {}
    for rd in json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']:
        NOT[rd['for']] = {s['seat']: {p: v * s['formal'] for p, v in s['fp'].items()} for s in rd['seats']}
    out = []
    for ser in SERIES.values():
        for i in range(1, len(ser)):
            t0, t1 = ser[i - 1], ser[i]
            a = NOT.get(t1) or seat_fp(c, t0); b = seat_fp(c, t1)
            out.append((t0, t1, {s: (a[s], b[s]) for s in b if s in a}))
    return out


def statewide(seats, k, grp):
    S = defaultdict(float); T = 0
    for s, d in seats.items():
        x = d[k]; t = sum(x.values()); T += t
        for p, v in x.items():
            S[grp(p)] += v
    return {g: v / T for g, v in S.items()}


def uniform_vs_proportional(P):
    res = {}
    for g in GROUPS + ['MINOR']:
        rows = []                    # (election, s0, s1, S0, S1)
        for t0, t1, seats in P:
            grp = (lambda p: 'MINOR' if g7(p) == 'OTH' else p) if g == 'MINOR' else g4
            S0, S1 = statewide(seats, 0, grp), statewide(seats, 1, grp)
            if S0.get(g, 0) < 0.01:
                continue
            for s, (a, b) in seats.items():
                x0, x1 = shares(a, grp).get(g, 0), shares(b, grp).get(g, 0)
                if g in ('ALP', 'COAL', 'GRN') and (x0 <= 0 or x1 <= 0):
                    continue         # party did not stand at one of the two elections
                rows.append((t1, x0, x1, S0[g], S1.get(g, 0)))
        e = np.array([r[0] for r in rows]); x0, x1, S0, S1 = (np.array([r[i] for r in rows]) for i in range(1, 5))
        uni = x0 + (S1 - S0); pro = x0 * S1 / S0
        lam = float(np.sum((x1 - uni) * (pro - uni)) / np.sum((pro - uni) ** 2))
        # leave one election out: lambda fitted on the others
        pred = np.zeros(len(rows))
        for el in set(e):
            m = e != el
            l_ = float(np.sum((x1[m] - uni[m]) * (pro[m] - uni[m])) / np.sum((pro[m] - uni[m]) ** 2))
            pred[~m] = uni[~m] + l_ * (pro[~m] - uni[~m])
        rm = lambda p: round(100 * float(np.sqrt(np.mean((x1 - p) ** 2))), 2)
        per = {}
        for el in sorted(set(e)):
            m = e == el
            d = (pro[m] - uni[m])
            per[el] = round(float(np.sum((x1[m] - uni[m]) * d) / np.sum(d ** 2)), 2) if np.sum(d ** 2) > 1e-6 else None
        res[g] = {'n': len(rows), 'lambda': round(lam, 2), 'rmse_uniform': rm(uni), 'rmse_proportional': rm(pro), 'rmse_lambda_out_of_sample': rm(pred), 'lambda_by_election': per}
        print(f"{g:7s} n={len(rows):4d}  lambda {lam:+.2f}  seat error (pts): uniform {rm(uni)}  proportional {rm(pro)}  fitted mix {rm(pred)}")
    return res


def onp_senate(c):
    """One Nation's Senate share at every booth (venue), consecutive federal elections: is growth proportional?"""
    sh = {}
    for e in ('fed2019', 'fed2022', 'fed2025'):
        tot = defaultdict(float); onp = defaultdict(float)
        for bid, party, v in c.execute('select booth_id, party, sum(votes) from sen_groups where election_id = ? group by 1, 2', (e,)):
            tot[bid] += v or 0
            if party == 'ONP':
                onp[bid] += v or 0
        ven = {b: vid for b, vid in c.execute('select booth_id, venue_id from aec_booth_venue where election_id = ?', (e,))}
        vt = defaultdict(float); vo = defaultdict(float)
        for b, t in tot.items():
            if ven.get(b) and t > 0:
                vt[ven[b]] += t; vo[ven[b]] += onp[b]
        sh[e] = {v: (vo[v] / vt[v], vt[v]) for v in vt if vt[v] >= 200}
    out = {}
    for a, b in (('fed2019', 'fed2022'), ('fed2022', 'fed2025')):
        common = [v for v in sh[a] if v in sh[b]]
        x0 = np.array([sh[a][v][0] for v in common]); x1 = np.array([sh[b][v][0] for v in common]); w = np.array([sh[b][v][1] for v in common])
        S0, S1 = np.average(x0, weights=w), np.average(x1, weights=w)
        uni = x0 + S1 - S0; pro = x0 * S1 / S0
        lam = float(np.sum(w * (x1 - uni) * (pro - uni)) / np.sum(w * (pro - uni) ** 2))
        rm = lambda p: round(100 * float(np.sqrt(np.average((x1 - p) ** 2, weights=w))), 2)
        out[f'{a}->{b}'] = {'venues': len(common), 'statewide_from': round(100 * S0, 2), 'statewide_to': round(100 * S1, 2), 'lambda': round(lam, 2),
                            'rmse_uniform': rm(uni), 'rmse_proportional': rm(pro), 'correlation': round(float(np.corrcoef(x0, x1)[0, 1]), 3)}
        print(f"One Nation Senate {a}->{b}: {len(common)} venues, {100 * S0:.1f}% -> {100 * S1:.1f}%, lambda {lam:+.2f}, error uniform {rm(uni)} proportional {rm(pro)}")
    return out


def onp_lc_2022(c):
    """One Nation's 2022 Legislative Council share in each Assembly district"""
    party = {k: p for k, p in c.execute("select candidate_id, party from lc_candidates where election_id = 'vic2022'")}
    name = {cid: nm for cid, nm in c.execute("select contest_id, contest_name from contests where election_id = 'vic2022'")}
    tot = defaultdict(float); onp = defaultdict(float)
    for d, k, v in c.execute("select district_id, candidate_id, sum(votes) from lc_votes where election_id = 'vic2022' group by 1, 2"):
        tot[d] += v or 0
        if party.get(k) == 'ONP':
            onp[d] += v or 0
    return {name.get(d, d): onp[d] / tot[d] for d in tot if tot[d] > 0}


# ---- the preference count --------------------------------------------------------------------------------------
def count(fp, W, default=1.0):
    """fp: {group: share}. Exclude the lowest (the minor-candidate bloc OTH first), pass its votes on by Luce strengths W[from][to]. Returns final two."""
    live = {g: v for g, v in fp.items() if v > 0.0005}
    while len(live) > 2:
        # OTH is many small candidates, not one: it is always excluded first
        lo = 'OTH' if 'OTH' in live else min(live, key=live.get); v = live.pop(lo)
        frm = W.get(lo) or W.get('OTH', {})
        s = {g: frm.get(g, default) for g in live}; t = sum(s.values())
        for g in live:
            live[g] += v * s[g] / t
    (a, va), (b, vb) = sorted(live.items(), key=lambda x: -x[1])
    return a, b, va / (va + vb)


def project(base, S0, S_new, lam):
    """seat shares by count group from base (dict of shares), statewide S0 -> S_new by group, rule lambda per group"""
    out = {}
    for g, x0 in base.items():
        G = 'COAL' if g in ('LIB', 'NAT') else g
        L = lam.get('MINOR' if G == 'OTH' else G, lam.get('OTHERS', 0.5))
        s0, s1 = S0.get(G, 0), S_new.get(G, 0)
        if s0 <= 0:
            out[g] = x0; continue
        uni = x0 + (s1 - s0) * (x0 / max(base_group(base, G), 1e-9) if G == 'COAL' else 1)
        pro = x0 * s1 / s0
        out[g] = max(0.0, uni + L * (pro - uni))
    t = sum(out.values())
    return {g: v / t for g, v in out.items()}


def base_group(base, G):
    return sum(v for g, v in base.items() if ('COAL' if g in ('LIB', 'NAT') else g) == G)


def backtest(c, P, lam, flows):
    import csv as _csv
    hist = {(h['to'], h['seat']): h for h in _csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv')))}
    me = json.load(open(os.path.join(ROOT, 'data/analysis/member_effects.json')))
    out = {}
    for t0, t1 in (('vic2014', 'vic2018'), ('vic2018', 'vic2022'), ('fed2019', 'fed2022'), ('fed2022', 'fed2025')):
        seats = next(s for a, b, s in P if a == t0 and b == t1)
        level = 'federal' if t1.startswith('fed') else 'state'
        eff = {k: me[level][k]['pts'] for k in ('sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'open')}; eff['veteran'] = 0.0
        W = flows['per_election'].get(t0, {}).get('weights') or flows['blend_2026']['weights']
        G = lambda p: 'COAL' if g7(p) in ('LIB', 'NAT') else g7(p)
        S0, S1 = statewide(seats, 0, G), statewide(seats, 1, G)
        name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (t1,))}
        win = {name.get(cid): g7(p) for cid, p in c.execute('select contest_id, party from candidates where election_id = ? and elected = 1', (t1,))}
        i0, i1 = ind_names(c, t0), ind_names(c, t1)
        pp0, pp1 = two_party(c, t0, t1)
        sw = float(np.mean([pp1[s] - pp0[s] for s in pp1 if s in pp0])) if pp1 else 0.0
        tally = defaultdict(int); misses = []
        for s, (a, b) in seats.items():
            if s not in win:
                continue
            w = 'COAL' if win[s] in ('LIB', 'NAT') else win[s]
            keep = s in i0 and i0[s][0] in i1.get(s, (None, set()))[1]
            h = hist.get((t1, s)); cat = (h['category'] or None) if h else None; mp = h['party'] if h else None
            base = drop_ind(shares(a, g7), keep)
            for adj in (False, True):
                pr = project(base, S0, S1, lam)
                if adj:
                    pr = member_adjust(pr, mp, cat, eff)
                f1, f2, m = count(pr, W)
                f1 = 'COAL' if f1 in ('LIB', 'NAT') else f1
                tally['primaries' + ('_member' if adj else '')] += f1 == w
                if adj and f1 != w:
                    misses.append({'seat': s, 'projected': f1, 'actual': w})
                if s in pp0:
                    x = pp0[s] + sw + ((eff.get(cat, 0) / 100 * (1 if mp == 'ALP' else -1)) if adj and mp in ('ALP', 'COAL') else 0)
                    tally['two_party' + ('_member' if adj else '')] += ('ALP' if x >= 0.5 else 'COAL') == w
            tally['seats'] += 1
        out[f'{t0}->{t1}'] = dict(tally, misses=misses)
        print(f"backtest {t0}->{t1} ({tally['seats']} seats): primaries {tally['primaries']}, +member {tally['primaries_member']}; uniform two-party {tally['two_party']}, +member {tally['two_party_member']}")
    tot = defaultdict(int)
    for v in out.values():
        for k, x in v.items():
            if k != 'misses':
                tot[k] += x
    out['total'] = dict(tot); print('backtest total:', dict(tot))
    return out


def two_party(c, t0, t1):
    """ALP two-party by seat: t0 notional if boundaries changed, else from the two-candidate count (classic seats)"""
    NOT = {rd['for']: {s['seat']: s['alp_2pp'] for s in rd['seats']} for rd in json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']}
    def tcp(e):
        name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (e,))}
        party = {k: g7(p) for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (e,))}
        t = defaultdict(lambda: defaultdict(float))
        for cid, k, v in c.execute('select contest_id, candidate_id, sum(votes) from tcp_votes where election_id = ? group by 1, 2', (e,)):
            p = party.get(k, 'OTH'); t[name.get(cid)]['COAL' if p in ('LIB', 'NAT') else p] += v or 0
        return {s: d['ALP'] / (d['ALP'] + d['COAL']) for s, d in t.items() if set(d) == {'ALP', 'COAL'}}
    return NOT.get(t1) or tcp(t0), tcp(t1)


def polls_now():
    d = json.load(open(os.path.join(ROOT, 'site/data/polls_vic2026.json')))
    e22 = next(p for p in d['polls'] if p.get('election'))['primary']
    ps = [p for p in d['polls'] if not p.get('election') and p.get('primary', {}).get('ALP')]
    last = max(dt.date.fromisoformat(p['date']) for p in ps)
    rec = [p for p in ps if (last - dt.date.fromisoformat(p['date'])).days <= 42]
    avg = {k: float(np.mean([p['primary'].get(k) or 0 for p in rec])) for k in ('ALP', 'COAL', 'GRN', 'ONP')}
    rest = float(np.mean([100 - sum(p['primary'].get(k) or 0 for k in ('ALP', 'COAL', 'GRN', 'ONP')) for p in rec]))   # polls differ on listing independents
    r22 = e22['IND'] / (e22['IND'] + e22['OTH'])
    avg['IND'], avg['OTH'] = rest * r22, rest * (1 - r22)
    return e22, avg, len(rec), last.isoformat()


def outlook_2026(c, lam, lam_onp, flows):
    e22, avg, npoll, last = polls_now()
    fp22 = seat_fp(c, 'vic2022'); fp22['Narracan'] = seat_fp(c, 'vic2023n').get('Narracan', fp22.get('Narracan'))
    base = {s: shares(d, g7) for s, d in fp22.items() if d}
    onp_lc = onp_lc_2022(c)
    G = lambda g: 'COAL' if g in ('LIB', 'NAT') else g
    S0 = defaultdict(float); T = sum(sum(d.values()) for d in fp22.values())
    for d in fp22.values():
        for p, v in d.items():
            S0[G(g7(p))] += v / T
    # statewide targets: the 2022 result moved by the poll change (polls' own 2022 baseline), group by group
    S1 = {g: max(0.0, S0[g] + (avg[g] - e22[g]) / 100) for g in ('ALP', 'COAL', 'GRN', 'IND', 'OTH')}
    S1['ONP'] = avg['ONP'] / 100
    lam7 = {'ALP': lam['ALP'], 'COAL': lam['COAL'], 'GRN': lam['GRN'], 'IND': lam['OTHERS'], 'OTH': lam['MINOR']}
    W = flows['blend_2026']['weights']
    lc_state = float(np.mean(list(onp_lc.values())))
    import csv as _csv
    cid_name = {cid: nm for cid, nm in c.execute("select contest_id, contest_name from contests where election_id = 'vic2022'")}
    ind26 = defaultdict(set)
    for r in _csv.DictReader(open(os.path.join(ROOT, 'data/vic2026/candidates.csv'))):
        if r['party'] == 'IND':
            ind26[cid_name.get(r['contest_id'], r['contest_id'])].add(r['name'].split()[-1].lower())
    i22 = ind_names(c, 'vic2022')
    me = json.load(open(os.path.join(ROOT, 'data/analysis/member_effects.json')))
    eff = {k: me['state'][k]['pts'] for k in ('sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'open')}; eff['veteran'] = 0.0
    mem = {m['seat']: m for m in me['outlook_2026']}
    seats = []
    for s, b in sorted(base.items()):
        b = drop_ind(dict(b), s in i22 and i22[s][0] in ind26.get(s, set()))
        # One Nation: it stood in few Assembly seats in 2022, so its starting map is its Legislative Council vote there
        b_onp_lc = onp_lc.get(s, lc_state)
        b['ONP'] = 0.0
        pr = project({k: v for k, v in b.items() if k != 'ONP'}, S0, S1, lam7)
        onp = S1['ONP'] * ((1 - lam_onp) + lam_onp * b_onp_lc / lc_state) if lam_onp is not None else S1['ONP']
        pr = {k: v * (1 - onp) for k, v in pr.items()}; pr['ONP'] = onp
        m_ = mem.get(s)
        if m_:
            pr = member_adjust(pr, m_['party'], m_['category'], dict(eff, open=m_.get('expected_pts', eff['open'])) if m_['category'] == 'open' else eff)
        f1, f2, m = count(pr, W)
        seats.append({'seat': s, '_pr': pr, 'member': (m_ or {}).get('member'), 'member_party': (m_ or {}).get('party'), 'member_category': (m_ or {}).get('category'),
                      'onp_lc_2022': round(b_onp_lc, 4), 'final_two': [f1, f2], 'winner_share': round(m, 4), 'winner': f1})
    # uncertainty: statewide poll error (2.5 pts per party, independent) and seat-level scatter (the out-of-sample
    # errors above; One Nation's scales with its vote, 0.31 x its share, from its 2022->2025 Senate growth)
    rng = np.random.default_rng(26); NS = 2000
    sd_seat = {'ALP': 0.044, 'LIB': 0.047, 'NAT': 0.047, 'GRN': 0.025, 'IND': 0.03, 'OTH': 0.02}
    wins = defaultdict(lambda: defaultdict(int)); totals = defaultdict(list)
    for _ in range(NS):
        shift = {g: rng.normal(0, 0.025) for g in ('ALP', 'COAL', 'GRN', 'ONP')}
        tot = defaultdict(int)
        for x in seats:
            pr = dict(x['_pr'])
            for g in pr:
                G = 'COAL' if g in ('LIB', 'NAT') else g
                sd = 0.31 * pr[g] if g == 'ONP' else sd_seat.get(g, 0.02)
                pr[g] = max(0.0, pr[g] + shift.get(G, 0) * (pr[g] / max(base_group(x['_pr'], G), 1e-9) if G == 'COAL' else 1) + rng.normal(0, sd))
            f1 = count(pr, W)[0]; f1 = 'COAL' if f1 in ('LIB', 'NAT') else f1
            wins[x['seat']][f1] += 1; tot[f1] += 1
        for g in ('ALP', 'COAL', 'GRN', 'ONP', 'IND'):
            totals[g].append(tot.get(g, 0))
    for x in seats:
        x['p_win'] = {g: round(v / NS, 3) for g, v in sorted(wins[x['seat']].items(), key=lambda kv: -kv[1])}
        x['primaries'] = {k: round(v, 4) for k, v in sorted(x.pop('_pr').items(), key=lambda kv: -kv[1]) if v >= 0.005}
    seat_totals = {g: {'median': int(np.median(v)), 'lo': int(np.percentile(v, 10)), 'hi': int(np.percentile(v, 90))} for g, v in totals.items()}
    print('   simulated seats (median, 80% range): ' + ', '.join(f"{g} {t['median']} ({t['lo']}-{t['hi']})" for g, t in seat_totals.items()))
    # against a uniform two-party swing at the polls' two-party figure
    tpp = [p_['tpp']['ALP'] for p_ in json.load(open(os.path.join(ROOT, 'site/data/polls_vic2026.json')))['polls'] if not p_.get('election') and (p_.get('tpp') or {}).get('ALP')][-6:]
    sw = float(np.mean(tpp)) / 100 - 0.55
    pp22 = two_party(c, 'vic2018', 'vic2022')[1]
    for x in seats:
        if x['seat'] in pp22:
            x['two_party_winner'] = 'ALP' if pp22[x['seat']] + sw >= 0.5 else 'COAL'
    from collections import Counter
    # sensitivity: how Liberal and National voters rank One Nation against Labor is not in the data (strength 1 = neutral)
    sens = {}
    for k in (0.5, 1.0, 2.0, 4.0):
        W2 = {f: dict(t) for f, t in W.items()}
        for f in ('LIB', 'NAT'):
            W2.setdefault(f, {})['ONP'] = k
        cnt = Counter()
        for x in seats:
            f1 = count({g: v for g, v in x['primaries'].items()}, W2)[0]; cnt['COAL' if f1 in ('LIB', 'NAT') else f1] += 1
        sens[str(k)] = dict(cnt)
    print('   Coalition-to-One Nation preference strength (vs Labor ~0.5):', sens)
    tally = Counter('COAL' if x['winner'] in ('LIB', 'NAT') else x['winner'] for x in seats)
    finals = Counter(tuple(sorted('COAL' if g in ('LIB', 'NAT') else g for g in x['final_two'])) for x in seats)
    print(f"2026 from primaries ({npoll} polls to {last}: " + ', '.join(f'{k} {v:.1f}' for k, v in avg.items()) + f"): winners {dict(tally)}; final twos {dict(finals)}")
    return {'polls': {k: round(v, 1) for k, v in avg.items()}, 'polls_2022_baseline': e22, 'polls_n': npoll, 'polls_to': last,
            'statewide_2022': {k: round(100 * v, 2) for k, v in S0.items()}, 'statewide_target': {k: round(100 * v, 2) for k, v in S1.items()},
            'winners': dict(tally), 'final_twos': {' v '.join(k): v for k, v in finals.items()}, 'seats': seats, 'simulated_seats': seat_totals, 'sensitivity_coalition_to_onp': sens,
            'two_party_swing_from_polls_pts': round(100 * sw, 1), 'two_party_seats': dict(Counter(x['two_party_winner'] for x in seats if 'two_party_winner' in x)),
            'assumptions': ['One Nation stands in every seat (check against the 2026 ballot draw)', 'Liberal and National voters\' preferences to One Nation are not in the flow model (they were rarely excluded with One Nation still in the count); set to the neutral default',
                            'Independents keep their 2022 vote scaled by the statewide change; new independents are not known until nominations']}


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    P = pairs(c)
    res = {'method': __doc__.split('\n\n')[1].strip()}
    res['rules'] = uniform_vs_proportional(P)
    res['onp_senate'] = onp_senate(c)
    lam = {g: res['rules'][g]['lambda'] for g in GROUPS + ['MINOR']}
    lam_onp = float(np.mean([v['lambda'] for v in res['onp_senate'].values()]))
    flows = json.load(open(os.path.join(ROOT, 'site/data/pref_flows.json')))
    res['backtest'] = backtest(c, P, lam, flows)
    res['outlook_2026'] = outlook_2026(c, lam, min(1.0, max(0.0, lam_onp)), flows)
    res['generated'] = dt.date.today().isoformat()
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/primary_swings.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
