"""Two levels of government: how federal members, federal governments and election timing show up in Victorian state
votes (and the reverse), 2004-2025.

1. Split tickets at the same polling place. Each state election is paired with the federal election nearest in time
   (2006-2007, 2010-2010, 2014-2013, 2018-2019, 2022-2022). At venues used for both, the gap between a party's state and
   federal first-preference shares is modelled on who the local member is at each level: +1 if the sitting member standing
   again is from that party, -1 if from its main rival, 0 for an open seat or other member. A personal vote predicts a
   positive state-member effect and a negative federal-member effect (the federal member pulls the federal vote their way).
   Three versions: pooled with election-pair effects; within the same state district (identifies the federal member from
   districts split between divisions); within the same federal division (identifies the state member).

2. Federal seat changes and state swings. Venues used at consecutive state elections: the state swing for a party,
   against the change in the federal member over the same period (the winner of the last federal election before each
   state election), within the same state district and election (so state candidates and the statewide mood cancel).
   Asked twice: raw, and holding the federal swing at the venue fixed, to see whether the member matters beyond the vote.

3. Statewide: each state election's swing against the party in government federally, and the months since the last
   federal election. Only five to seven elections, so descriptive.

Inputs  data/elections.sqlite, data/analysis/member_history.csv (src.member_effects)
Output  data/analysis/cross_level.json
Usage   python3 -m src.cross_level
"""
import os, json, csv, sqlite3
from collections import defaultdict
from datetime import date
import numpy as np
from .member_effects import GROUP, BYELECTIONS, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = [('vic2006', 'fed2007', 'fed2004'), ('vic2010', 'fed2010', 'fed2010'), ('vic2014', 'fed2013', 'fed2013'), ('vic2018', 'fed2019', 'fed2016'), ('vic2022', 'fed2022', 'fed2022')]
#        state       federal vote compared   federal member in office at the state election (last federal election before it)
STATE = ['vic1999', 'vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022']
FED_BEFORE = {'vic2002': None, 'vic2006': 'fed2004', 'vic2010': 'fed2010', 'vic2014': 'fed2013', 'vic2018': 'fed2016', 'vic2022': 'fed2022'}
FED_GOV = {'vic1999': 'COAL', 'vic2002': 'COAL', 'vic2006': 'COAL', 'vic2010': 'ALP', 'vic2014': 'COAL', 'vic2018': 'COAL', 'vic2022': 'ALP'}   # party in federal government on state polling day
STATE_GOV_BEFORE = {'vic2002': 'ALP', 'vic2006': 'ALP', 'vic2010': 'ALP', 'vic2014': 'COAL', 'vic2018': 'ALP', 'vic2022': 'ALP'}            # party in state government going in
LAST_FED_DATE = {'vic1999': '1998-10-03', 'vic2002': '2001-11-10', 'vic2006': '2004-10-09', 'vic2010': '2010-08-21', 'vic2014': '2013-09-07', 'vic2018': '2016-07-02', 'vic2022': '2022-05-21'}


def venue_shares(c):
    """(election, venue) -> {'contest': id, 'share': {group: share}} for ordinary booths; venues split across contests dropped"""
    geo = {(e, b): (cid, v) for e, b, cid, v in c.execute("select election_id, booth_id, contest_id, venue_id from booth_geo where booth_type = 'ordinary' and venue_id is not null")}
    party = {(e, k): GROUP.get(p, p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    votes = defaultdict(lambda: defaultdict(float)); contests = defaultdict(set)
    for e, b, k, v in c.execute("select election_id, booth_id, candidate_id, votes from fp_votes where candidate_id <> 'INFORMAL'"):
        g = geo.get((e, b))
        if g:
            votes[(e, g[1])][party.get((e, k), 'OTH')] += v or 0; contests[(e, g[1])].add(g[0])
    out = {}
    for key, d in votes.items():
        t = sum(d.values())
        if t >= 100 and len(contests[key]) == 1:
            out[key] = {'contest': next(iter(contests[key])), 'share': {p: x / t for p, x in d.items()}, 'n': t}
    return out


def members(c):
    """(election, contest) -> {'party', 'standing'}: the member at dissolution going into that election, from the member history,
    and (election, contest) -> winner's party"""
    name_of = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    by_name = {(e, nm): cid for (e, cid), nm in name_of.items()}
    mem = {}
    for r in csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv'))):
        cid = by_name.get((r['to'], r['seat']))
        if cid:
            mem[(r['to'], cid)] = {'party': r['party'], 'standing': r['category'] in ('veteran', 'sophomore_gain', 'sophomore_held', 'sophomore_byelection'), 'category': r['category']}
    win = {}
    for e, cid, p in c.execute('select election_id, contest_id, party from candidates where elected = 1'):
        win[(e, cid)] = GROUP.get(p, p)
    for nm, e, sur, g in BYELECTIONS:      # a by-election after election e changes the member in office afterwards
        cid = by_name.get((e, nm))
        if cid:
            win[(e, cid)] = g
    return mem, win


def x_member(m, P, rival):
    if not m or not m['standing']:
        return 0.0
    return 1.0 if m['party'] == P else (-1.0 if m['party'] == rival else 0.0)


def ols(y, X, groups, rng_n=500, seed=3):
    """least squares with a cluster bootstrap over `groups`; returns coefficients and 90% intervals for the named columns"""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    g = np.array(groups); ug = np.unique(g); idx = {u: np.where(g == u)[0] for u in ug}
    rng = np.random.default_rng(seed); boots = []
    for _ in range(rng_n):
        pick = np.concatenate([idx[u] for u in rng.choice(ug, len(ug))])
        b, *_ = np.linalg.lstsq(X[pick], y[pick], rcond=None); boots.append(b)
    boots = np.array(boots)
    return beta, np.percentile(boots, 5, axis=0), np.percentile(boots, 95, axis=0)


def fe_fit(rows, fe_key, xs, ykey, cluster_key, rng_n=500, seed=3):
    """absorb the fixed effects by demeaning within each cell, then least squares on the few slopes; cluster bootstrap"""
    keys = [fe_key(r) for r in rows]
    y = np.array([r[ykey] for r in rows], float); X = np.array([[r[k] for k in xs] for r in rows], float)
    def demean(yv, Xv, ks):
        cell = defaultdict(list)
        for i, k in enumerate(ks):
            cell[k].append(i)
        yd, Xd = yv.copy(), Xv.copy()
        for ix in cell.values():
            yd[ix] -= yv[ix].mean(); Xd[ix] -= Xv[ix].mean(axis=0)
        return yd, Xd
    yd, Xd = demean(y, X, keys)
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    cl = np.array([cluster_key(r) for r in rows]); uc = np.unique(cl); idx = {u: np.where(cl == u)[0] for u in uc}
    rng = np.random.default_rng(seed); boots = []
    for _ in range(rng_n):
        pick = np.concatenate([idx[u] for u in rng.choice(uc, len(uc))])
        ydb, Xdb = demean(y[pick], X[pick], [keys[i] if False else (keys[i], n) for n, i in enumerate(pick)] if False else [keys[i] for i in pick])
        b, *_ = np.linalg.lstsq(Xdb, ydb, rcond=None); boots.append(b)
    boots = np.array(boots)
    return beta, np.percentile(boots, 5, axis=0), np.percentile(boots, 95, axis=0)


def fe_design(rows, fe_key, xs):
    cells = sorted({fe_key(r) for r in rows}); ci = {k: i for i, k in enumerate(cells)}
    X = np.zeros((len(rows), len(xs) + len(cells)))
    for n, r in enumerate(rows):
        for j, k in enumerate(xs):
            X[n, j] = r[k]
        X[n, len(xs) + ci[fe_key(r)]] = 1
    return X


def split_tickets(V, mem):
    out = {}
    for P, rival in (('ALP', 'COAL'), ('COAL', 'ALP')):
        rows = []
        for s, f, fmem in PAIRS:
            for (e, v), sv in V.items():
                if e != s or (f, v) not in V:
                    continue
                fv = V[(f, v)]
                if P not in sv['share'] or P not in fv['share']:
                    continue
                rows.append({'pair': s, 'district': sv['contest'], 'division': fv['contest'], 'gap': sv['share'][P] - fv['share'][P],
                             'xs': x_member(mem.get((s, sv['contest'])), P, rival), 'xf': x_member(mem.get((f, fv['contest'])), P, rival),
                             'ind_fed': 1.0 if (mem.get((f, fv['contest'])) or {}).get('party') == 'IND' and (mem.get((f, fv['contest'])) or {}).get('standing') else 0.0})
        y = np.array([r['gap'] for r in rows]); res = {'venues': len(rows), 'mean_gap_by_pair': {}}
        for s, *_ in PAIRS:
            g = [r['gap'] for r in rows if r['pair'] == s]
            res['mean_gap_by_pair'][s] = round(100 * float(np.mean(g)), 2) if g else None
        for label, fe, xs, cl in (('pooled', lambda r: r['pair'], ['xs', 'xf', 'ind_fed'], 'district'),
                                  ('within_state_district', lambda r: (r['pair'], r['district']), ['xf', 'ind_fed'], 'district'),
                                  ('within_federal_division', lambda r: (r['pair'], r['division']), ['xs'], 'division')):
            b, lo, hi = fe_fit(rows, fe, xs, 'gap', lambda r, cl=cl: r['pair'] + r[cl])
            res[label] = {k: {'pts': round(100 * b[j], 2), 'lo': round(100 * lo[j], 2), 'hi': round(100 * hi[j], 2)} for j, k in enumerate(xs)}
        out[P] = res
        print(f"split tickets ({P}, {len(rows)} venue-pairs): mean state-minus-federal gap by pair {res['mean_gap_by_pair']}")
        for label in ('pooled', 'within_state_district', 'within_federal_division'):
            print(f"   {label}: " + '  '.join(f"{k} {v['pts']:+.2f} [{v['lo']:+.2f},{v['hi']:+.2f}]" for k, v in res[label].items()))
    return out


def flips(V, win):
    """state swing at a venue against a change in its federal member's party between consecutive state elections"""
    out = {}
    for P, rival in (('ALP', 'COAL'), ('COAL', 'ALP')):
        rows = []
        for i in range(2, len(STATE)):
            s0, s1 = STATE[i - 1], STATE[i]
            f0, f1 = FED_BEFORE.get(s0), FED_BEFORE.get(s1)
            if not f0 or not f1 or f0 == f1:
                continue
            for (e, v), a in V.items():
                if e != s1 or (s0, v) not in V or (f0, v) not in V or (f1, v) not in V:
                    continue
                b = V[(s0, v)]
                m0, m1 = win.get((f0, V[(f0, v)]['contest'])), win.get((f1, V[(f1, v)]['contest']))
                code = lambda m: 1 if m == P else (-1 if m == rival else 0)
                if P not in a['share'] or P not in b['share']:
                    continue
                rows.append({'pair': s1, 'district': a['contest'], 'swing': a['share'][P] - b['share'][P], 'dmem': float(code(m1) - code(m0)),
                             'fswing': V[(f1, v)]['share'].get(P, 0) - V[(f0, v)]['share'].get(P, 0), 'flip': m0 != m1})
        y = np.array([r['swing'] for r in rows]); res = {'venues': len(rows), 'flipped': sum(r['flip'] for r in rows)}
        for label, xs in (('member_only', ['dmem']), ('member_and_federal_swing', ['dmem', 'fswing'])):
            bb, lo, hi = fe_fit(rows, lambda r: (r['pair'], r['district']), xs, 'swing', lambda r: r['pair'] + r['district'])
            res[label] = {k: {'pts' if k == 'dmem' else 'slope': round(100 * bb[j], 2) if k == 'dmem' else round(float(bb[j]), 3),
                              'lo': round(100 * lo[j], 2) if k == 'dmem' else round(float(lo[j]), 3), 'hi': round(100 * hi[j], 2) if k == 'dmem' else round(float(hi[j]), 3)} for j, k in enumerate(xs)}
        out[P] = res
        print(f"federal member changes ({P}): {len(rows)} venues, {res['flipped']} under a changed federal member; " + '; '.join(f"{lab}: " + ', '.join(f"{k} {list(v.values())[0]:+} [{v['lo']:+},{v['hi']:+}]" for k, v in res[lab].items()) for lab in ('member_only', 'member_and_federal_swing')))
    return out


def statewide(c):
    tot = defaultdict(lambda: defaultdict(float))
    party = {(e, k): GROUP.get(p, p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    for e, k, v in c.execute("select election_id, candidate_id, sum(votes) from fp_votes where candidate_id <> 'INFORMAL' group by 1, 2"):
        tot[e][party.get((e, k), 'OTH')] += v or 0
    sh = {e: {p: x / sum(d.values()) for p, x in d.items()} for e, d in tot.items()}
    dates = {e: d for e, d in c.execute('select election_id, date from elections')}
    rows = []
    for i in range(1, len(STATE)):
        s0, s1 = STATE[i - 1], STATE[i]
        fg = FED_GOV[s1]
        months = (date.fromisoformat(dates[s1]) - date.fromisoformat(LAST_FED_DATE[s1])).days / 30.44
        rows.append({'election': s1, 'federal_government': fg, 'state_government_going_in': STATE_GOV_BEFORE[s1], 'months_since_federal_election': round(months, 1),
                     'swing_to_federal_government_party': round(100 * (sh[s1].get(fg, 0) - sh[s0].get(fg, 0)), 2),
                     'ALP': round(100 * sh[s1].get('ALP', 0), 2), 'COAL': round(100 * sh[s1].get('COAL', 0), 2)})
    sw = [r['swing_to_federal_government_party'] for r in rows]
    print('statewide: swing at state elections to the party governing federally: ' + ', '.join(f"{r['election']} {r['federal_government']} {r['swing_to_federal_government_party']:+.1f} ({r['months_since_federal_election']:.0f} mo)" for r in rows) + f'; mean {np.mean(sw):+.1f}')
    return {'rows': rows, 'mean_swing_to_federal_government_party': round(float(np.mean(sw)), 2)}


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    V = venue_shares(c)
    mem, win = members(c)
    res = {'method': __doc__.split('\n\n')[1].strip(), 'split_tickets': split_tickets(V, mem), 'federal_member_changes': flips(V, win), 'statewide': statewide(c)}
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/cross_level.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
