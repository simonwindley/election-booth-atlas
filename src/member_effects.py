"""Member effects: the personal vote of sitting members in Victorian state and federal seats, 1999-2025.

For every seat contested under the same name at two consecutive general elections of the same level, the party of the
member at dissolution (the winner last time, or a by-election winner since) is followed: its share of first preferences
then and now, and what happened to the member:

  veteran      the member was already the member before the previous election and is standing again (the baseline)
  sophomore    the member was first elected at the previous election (or at a by-election since) and is standing again;
               split into 'gain' (won the seat from another party) and 'held' (succeeded a retiring member of the same party)
  open         the member is not on the ballot (retired, lost preselection, moved, died) and the party stands someone new
  switched     the member stands again under another party label or as an independent (reported, not modelled)

The swing for the member's party in the seat is compared with the other seats the same party held at the same election
(an election x party fixed effect), so the statewide mood cancels and the category effects are relative to a veteran
recontesting. Uncertainty: a bootstrap over seats, resampling within each election.

Booth level (a boundary-robust check, and the first look at 'transferred voters'): ordinary booths at the same venue at
both elections. A booth whose voters had the standing member last time ('continuing') is compared with a booth that has
just been moved into that member's seat ('transferred'): the personal vote only reaches voters who have had the member.

Inputs  data/elections.sqlite
Outputs data/analysis/member_effects.json (summary + per-seat table), data/analysis/member_history.csv
Usage   python3 -m src.member_effects
"""
import os, re, json, csv, sqlite3
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUP = {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL'}
SERIES = {'state': ['vic1999', 'vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022'],
          'federal': ['fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025']}
# by-elections that changed the member mid-term and are not loaded as elections of their own
# (seat name, the general election after which it happened, new member's surname, party group)
BYELECTIONS = [
    ('Burwood', 'vic1999', 'Stensholt', 'ALP'), ('Benalla', 'vic1999', 'Allen', 'ALP'),
    ('Williamstown', 'vic2006', 'Noonan', 'ALP'), ('Albert Park', 'vic2006', 'Foley', 'ALP'), ('Kororoit', 'vic2006', 'Kairouz', 'ALP'),
    ('Altona', 'vic2006', 'Hennessy', 'ALP'),
    ('Broadmeadows', 'vic2010', 'McGuire', 'ALP'), ('Niddrie', 'vic2010', 'Carroll', 'ALP'), ('Melbourne', 'vic2010', 'Kanis', 'ALP'),
    ('Lyndhurst', 'vic2010', 'Pakula', 'ALP'),
    ('Gippsland South', 'vic2014', "O'Brien", 'COAL'), ('Polwarth', 'vic2014', 'Riordan', 'COAL'), ('South-West Coast', 'vic2014', 'Britnell', 'COAL'),
    ('Northcote', 'vic2014', 'Thorpe', 'GRN'),
    ('Gippsland', 'fed2007', 'Chester', 'COAL'), ('Higgins', 'fed2007', "O'Dwyer", 'COAL'), ('Batman', 'fed2016', 'Kearney', 'ALP'),
    ('Aston', 'fed2022', 'Doyle', 'ALP'),
]


def norm(s):
    return re.sub(r"[^a-z]", '', (s or '').lower())


def load(c):
    cands = defaultdict(list)       # (eid, contest_name) -> [(surname, given, group, elected)]
    name_of = {}
    for eid, cid, name in c.execute('select election_id, contest_id, contest_name from contests'):
        name_of[(eid, cid)] = name
    for eid, cid, cand, sur, giv, party, el in c.execute('select election_id, contest_id, candidate_id, surname, given_name, party, elected from candidates'):
        nm = name_of.get((eid, cid))
        if nm:
            cands[(eid, nm)].append({'id': cand, 'sur': norm(sur), 'giv': norm((giv or '').split()[0] if (giv or '').split() else '')[:3], 'name': f'{giv} {sur}', 'grp': GROUP.get(party, party), 'el': bool(el)})
    share = defaultdict(lambda: defaultdict(float))   # (eid, contest_name) -> group -> votes
    for eid, cid, cand, votes in c.execute('select election_id, contest_id, candidate_id, sum(votes) from fp_votes where candidate_id <> "INFORMAL" group by 1, 2, 3'):
        nm = name_of.get((eid, cid))
        if nm:
            share[(eid, nm)][cand] += votes or 0
    shares = {}
    for key, byc in share.items():
        grp = {x['id']: x['grp'] for x in cands[key]}
        tot = sum(byc.values())
        g = defaultdict(float)
        for cid, v in byc.items():
            g[grp.get(cid, 'OTH')] += v
        shares[key] = {k: v / tot for k, v in g.items()} if tot else {}
    return cands, shares


def same(a, b):
    return a['sur'] == b['sur'] and (not a['giv'] or not b['giv'] or a['giv'] == b['giv'])


def history(cands, shares):
    rows = []
    for level, ser in SERIES.items():
        for i in range(1, len(ser)):
            t0, t1 = ser[i - 1], ser[i]
            tm = ser[i - 2] if i >= 2 else None
            seats0 = {nm for (e, nm) in cands if e == t0}
            for (e, nm) in list(cands):
                if e != t1 or nm not in seats0:
                    continue
                win0 = [x for x in cands[(t0, nm)] if x['el']]
                if len(win0) != 1:
                    continue
                mem = dict(win0[0]); via = 'general'
                by = [b for b in BYELECTIONS if b[0] == nm and b[1] == t0]
                if by:
                    mem = {'sur': norm(by[0][2]), 'giv': '', 'name': by[0][2], 'grp': by[0][3]}; via = 'by-election'
                # was the member already the member before the previous election?
                first_term = via == 'by-election'
                prev_holder_grp = None
                if not first_term and tm and (tm, nm) in cands:
                    wm = [x for x in cands[(tm, nm)] if x['el']]
                    byp = [b for b in BYELECTIONS if b[0] == nm and b[1] == tm]
                    prior = {'sur': norm(byp[0][2]), 'giv': '', 'grp': byp[0][3]} if byp else (wm[0] if wm else None)
                    if prior is not None:
                        first_term = not same(prior, mem)
                        prev_holder_grp = prior['grp']
                elif not first_term:
                    first_term = None      # no record of the seat before the previous election
                stand = [x for x in cands[(t1, nm)] if same(x, mem)]
                if stand and stand[0]['grp'] != mem['grp']:
                    cat = 'switched'
                elif stand:
                    cat = 'veteran' if first_term is False else ('sophomore' if first_term else None)
                    if cat == 'sophomore' and via == 'general':
                        cat = 'sophomore_gain' if prev_holder_grp and prev_holder_grp != mem['grp'] else 'sophomore_held'
                    elif cat == 'sophomore':
                        cat = 'sophomore_byelection'
                else:
                    cat = 'open' if any(x['grp'] == mem['grp'] for x in cands[(t1, nm)]) else 'not_contested'
                # tenure: consecutive wins in this seat up to and including the previous election (a by-election win counts)
                wins, j, censored = 0, i - 1, False
                while j >= 0 and (ser[j], nm) in cands:
                    wj = [x for x in cands[(ser[j], nm)] if x['el']]
                    bj = [b for b in BYELECTIONS if b[0] == nm and b[1] == ser[j]]
                    mj = {'sur': norm(bj[0][2]), 'giv': ''} if bj else (wj[0] if wj else None)
                    if mj is None or not same(mj, mem):
                        break
                    wins += 1
                    if bj:                          # elected at that by-election: the general win before it was someone else's
                        break
                    j -= 1
                if j < 0:
                    censored = True                 # still the member at the start of the series: tenure is at least this
                s0, s1 = shares.get((t0, nm), {}).get(mem['grp']), shares.get((t1, nm), {}).get(mem['grp'])
                won = [x for x in cands[(t1, nm)] if x['el']]
                rows.append({'level': level, 'from': t0, 'to': t1, 'seat': nm, 'member': mem['name'], 'party': mem['grp'], 'via': via,
                             'category': cat, 'share_before': s0, 'share_after': s1, 'change': (s1 - s0) if s0 is not None and s1 is not None else None,
                             'held': bool(won and won[0]['grp'] == mem['grp']), 'wins': wins, 'tenure_censored': censored})
    return rows


CATS = ['sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'open']


def fit(rows, rng=None):
    """change = a[election, party] + sum_k b_k [category k]; baseline veteran. Returns b and the per-cell demeaned data."""
    use = [r for r in rows if r['category'] in CATS + ['veteran'] and r['change'] is not None and r['party'] in ('ALP', 'COAL', 'GRN', 'IND')]
    if rng is not None:   # bootstrap: resample seats within each election
        by = defaultdict(list)
        for r in use:
            by[r['to']].append(r)
        use = [by[k][j] for k in by for j in rng.integers(0, len(by[k]), len(by[k]))]
    cells = sorted({(r['to'], r['party']) for r in use})
    ci = {c: i for i, c in enumerate(cells)}
    X = np.zeros((len(use), len(cells) + len(CATS))); y = np.zeros(len(use))
    for n, r in enumerate(use):
        X[n, ci[(r['to'], r['party'])]] = 1
        if r['category'] in CATS:
            X[n, len(cells) + CATS.index(r['category'])] = 1
        y[n] = r['change']
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return dict(zip(CATS, beta[len(cells):])), len(use)


def summarise(rows, label):
    b, n = fit(rows)
    rng = np.random.default_rng(7)
    boots = [fit(rows, rng)[0] for _ in range(1000)]
    out = {'n': n, 'counts': {k: sum(1 for r in rows if r['category'] == k and r['change'] is not None) for k in CATS + ['veteran', 'switched', 'not_contested']}}
    for k in CATS:
        v = np.array([x[k] for x in boots])
        out[k] = {'pts': round(100 * b[k], 2), 'lo': round(100 * np.percentile(v, 5), 2), 'hi': round(100 * np.percentile(v, 95), 2)}
    print(f'{label}: n={n}  ' + '  '.join(f'{k} {out[k]["pts"]:+.1f} [{out[k]["lo"]:+.1f}, {out[k]["hi"]:+.1f}] (n={out["counts"][k]})' for k in CATS))
    return out


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    cands, shares = load(c)
    rows = history(cands, shares)
    res = {'method': __doc__.split('\n\n')[1].strip(), 'all': summarise(rows, 'all'),
           'state': summarise([r for r in rows if r['level'] == 'state'], 'state'),
           'federal': summarise([r for r in rows if r['level'] == 'federal'], 'federal')}
    for p in ('ALP', 'COAL'):
        res['party_' + p] = summarise([r for r in rows if r['party'] == p], p)
    res['leave_one_out'] = {}
    for e in sorted({r['to'] for r in rows}):
        b, n = fit([r for r in rows if r['to'] != e])
        res['leave_one_out'][e] = {k: round(100 * v, 2) for k, v in b.items()}
    lo = res['leave_one_out']
    print('leave one election out, range: ' + '  '.join(f"{k} {min(v[k] for v in lo.values()):+.1f}..{max(v[k] for v in lo.values()):+.1f}" for k in CATS))
    res['booth'] = booth_level(c, rows)
    res['tenure'] = tenure(rows)
    res['outlook_2026'] = outlook_2026(c, res, rows)
    os.makedirs(os.path.join(ROOT, 'data/analysis'), exist_ok=True)
    with open(os.path.join(ROOT, 'data/analysis/member_history.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/member_effects.json'), 'w'), indent=1)
    from collections import Counter
    print(Counter((r['level'], r['category']) for r in rows))



def booth_level(c, rows):
    """continuing vs transferred voters within the same seat, at booths whose venue was used at both elections"""
    name_of = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    geo = {}
    for e, bid, cid, vid, bt in c.execute("select election_id, booth_id, contest_id, venue_id, booth_type from booth_geo where booth_type = 'ordinary' and venue_id is not null"):
        geo[(e, bid)] = (cid, vid)
    sh = defaultdict(dict)   # (e, venue) -> {group: share}; (one booth per venue per election; duplicates dropped)
    seat_of = {}
    tot = defaultdict(float); grp_votes = defaultdict(lambda: defaultdict(float))
    party = {(e, k): GROUP.get(p, p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    for e, bid, cand, v in c.execute("select election_id, booth_id, candidate_id, votes from fp_votes where candidate_id <> 'INFORMAL'"):
        g = geo.get((e, bid))
        if not g:
            continue
        key = (e, g[1]); seat_of[key] = name_of.get((e, g[0]))
        tot[key] += v or 0; grp_votes[key][party.get((e, cand), 'OTH')] += v or 0
    for key, t in tot.items():
        if t > 0:
            sh[key] = {k: x / t for k, x in grp_votes[key].items()}
    # member at dissolution per (election, seat): winner, overridden by by-elections
    winner, wparty = {}, {}
    for e, cid, sur, giv, pty in c.execute('select election_id, contest_id, surname, given_name, party from candidates where elected = 1'):
        winner[(e, name_of.get((e, cid)))] = norm(sur); wparty[(e, name_of.get((e, cid)))] = GROUP.get(pty, pty)
    for nm, e, sur, g in BYELECTIONS:
        winner[(e, nm)] = norm(sur); wparty[(e, nm)] = g
    out = []
    for r in rows:
        if r['category'] not in ('veteran', 'sophomore_gain', 'sophomore_held', 'sophomore_byelection'):
            continue
        t0, t1, nm, P, mem = r['from'], r['to'], r['seat'], r['party'], norm(r['member'].split()[-1])
        cont, trans, trans_same, trans_other = [], [], [], []
        for (e, vid), s1 in sh.items():
            if e != t1 or seat_of.get((e, vid)) != nm or (t0, vid) not in sh or P not in s1:
                continue
            prev_seat = seat_of.get((t0, vid))
            sw = s1.get(P, 0) - sh[(t0, vid)].get(P, 0)
            if winner.get((t0, prev_seat)) == mem:
                cont.append(sw)
            else:
                trans.append(sw); (trans_same if wparty.get((t0, prev_seat)) == P else trans_other).append(sw)
        if len(cont) >= 3 and len(trans) >= 3:
            out.append({'to': t1, 'seat': nm, 'party': P, 'category': r['category'], 'continuing': float(np.mean(cont)), 'transferred': float(np.mean(trans)), 'n_c': len(cont), 'n_t': len(trans),
                        'transferred_same_party': float(np.mean(trans_same)) if len(trans_same) >= 3 else None, 'transferred_other_party': float(np.mean(trans_other)) if len(trans_other) >= 3 else None})
    d = np.array([x['continuing'] - x['transferred'] for x in out])
    rng = np.random.default_rng(11)
    bs = [rng.choice(d, len(d)).mean() for _ in range(2000)] if len(d) else [0]
    res = {'seats': len(out), 'gap_pts': round(100 * float(d.mean()), 2) if len(d) else None, 'lo': round(100 * float(np.percentile(bs, 5)), 2), 'hi': round(100 * float(np.percentile(bs, 95)), 2),
           'by_category': {k: round(100 * float(np.mean([x['continuing'] - x['transferred'] for x in out if x['category'] == k])), 2) for k in {x['category'] for x in out}}, 'seats_detail': out}
    for k in ('same_party', 'other_party'):
        dd = np.array([x['continuing'] - x['transferred_' + k] for x in out if x['transferred_' + k] is not None])
        bb = [rng.choice(dd, len(dd)).mean() for _ in range(2000)] if len(dd) else [0]
        res['gap_' + k] = {'seats': len(dd), 'pts': round(100 * float(dd.mean()), 2) if len(dd) else None, 'lo': round(100 * float(np.percentile(bb, 5)), 2), 'hi': round(100 * float(np.percentile(bb, 95)), 2)}
        print(f"   continuing minus transferred from a {k.replace('_', ' ')} member: {res['gap_' + k]}")
    print(f"booth level: {res['seats']} seats with both continuing and transferred booths; continuing minus transferred swing to the member's party {res['gap_pts']:+.1f} pts [{res['lo']:+.1f}, {res['hi']:+.1f}]  by category {res['by_category']}")
    return res



def outlook_2026(c, res, rows=()):
    """what the estimates imply for each 2026 district: the member at dissolution and whether they are standing again"""
    name_of = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    win22 = {}
    for e, cid, sur, giv, p in c.execute("select election_id, contest_id, surname, given_name, party from candidates where elected = 1 and election_id in ('vic2022', 'vic2023n')"):
        win22[name_of[(e, cid)]] = {'name': f'{giv} {sur}', 'sur': norm(sur), 'grp': GROUP.get(p, p), 'via': 'general'}
    for e, cid, sur, giv, p in c.execute("select k.election_id, k.contest_id, k.surname, k.given_name, k.party from candidates k join elections x on x.election_id = k.election_id where k.elected = 1 and x.level = 'state-by' order by x.date"):
        win22[name_of[(e, cid)]] = {'name': f'{giv} {sur}', 'sur': norm(sur), 'grp': GROUP.get(p, p), 'via': 'by-election'}
    win18_seat = {name_of[(e, cid)]: norm(sur) for e, cid, sur in c.execute("select election_id, contest_id, surname from candidates where elected = 1 and election_id = 'vic2018'")}
    win18_any = set(win18_seat.values())
    win18_grp = {name_of[(e, cid)]: GROUP.get(p, p) for e, cid, p in c.execute("select election_id, contest_id, party from candidates where elected = 1 and election_id = 'vic2018'")}
    ret = {r['seat']: r for r in csv.DictReader(open(os.path.join(ROOT, 'data/vic2026/retiring.csv'))) if r['house'] == 'LA'}
    cand26 = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(ROOT, 'data/vic2026/candidates.csv'))):
        cand26[r['contest_id']].append(r)
    cid_of = {nm: cid for (e, cid), nm in name_of.items() if e == 'vic2022'}
    st = res['state']
    eff = {'sophomore_gain': st['sophomore_gain']['pts'], 'sophomore_held': st['sophomore_held']['pts'], 'sophomore_byelection': st['sophomore_byelection']['pts'], 'open': st['open']['pts'], 'veteran': 0.0}
    prev22 = {r['seat']: r for r in rows if r['to'] == 'vic2022'}
    T = res.get('tenure', {}).get('all', {})
    open_by_tenure = {1: T.get('open_1', {}).get('pts'), 2: T.get('open_2', {}).get('pts'), 3: T.get('open_3', {}).get('pts'), 4: T.get('open_4plus', {}).get('pts')}
    out = []
    for seat, m in sorted(win22.items()):
        pr = prev22.get(seat)
        terms = 1 if m['via'] == 'by-election' else ((int(pr['wins']) + 1) if pr and norm(pr['member'].split()[-1]) == m['sur'][-len(norm(pr['member'].split()[-1])):] and pr['category'] not in ('open', None, '') else 1)
        censored = bool(pr and pr.get('tenure_censored') and terms > 1)
        standing = any(norm(x['name']).endswith(m['sur']) and x['incumbent'] == '1' for x in cand26.get(cid_of.get(seat) or 'vic-' + re.sub(r'[^a-z]+', '-', seat.lower()).strip('-'), []))
        if seat in ret or not standing:
            cat = 'open'
        elif m['via'] == 'by-election':
            cat = 'sophomore_byelection'
        elif win18_seat.get(seat) == m['sur'] or (seat not in win18_seat and m['sur'] in win18_any):
            cat = 'veteran'
        else:
            cat = 'sophomore_gain' if seat in win18_grp and win18_grp[seat] != m['grp'] else 'sophomore_held'
        exp = eff[cat]
        if cat == 'open' and open_by_tenure.get(min(terms, 4)) is not None:
            exp = open_by_tenure[min(terms, 4)]          # the penalty depends on how long the departing member served
        out.append({'seat': seat, 'contest_id': cid_of.get(seat), 'member': m['name'], 'party': m['grp'], 'via': m['via'], 'category': cat, 'terms': terms, 'terms_at_least': censored,
                    'retiring': seat in ret, 'not_on_declared_list': (not standing) and seat not in ret, 'expected_pts': exp, 'confidence': 'low' if cat == 'sophomore_byelection' else 'moderate'})
    from collections import Counter
    print('2026:', Counter(x['category'] for x in out))
    print('   open:', ', '.join(f"{x['seat']} ({x['party']})" for x in out if x['category'] == 'open'))
    print('   sophomore gain:', ', '.join(f"{x['seat']} ({x['member']}, {x['party']})" for x in out if x['category'] == 'sophomore_gain'))
    return out



LEADERS = [('vic2002', 'Williamstown', 'Premier'), ('vic2002', 'Malvern', 'Opposition leader'), ('vic2006', 'Williamstown', 'Premier'), ('vic2006', 'Hawthorn', 'Opposition leader'),
           ('vic2010', 'Broadmeadows', 'Premier'), ('vic2010', 'Hawthorn', 'Opposition leader'), ('vic2014', 'South-West Coast', 'Premier'), ('vic2014', 'Mulgrave', 'Opposition leader'),
           ('vic2018', 'Mulgrave', 'Premier'), ('vic2018', 'Bulleen', 'Opposition leader'), ('vic2022', 'Mulgrave', 'Premier'), ('vic2022', 'Bulleen', 'Opposition leader'),
           ('fed2016', 'Maribyrnong', 'Opposition leader'), ('fed2019', 'Maribyrnong', 'Opposition leader')]


def tenure_cat(r):
    w = int(r['wins'])
    if r['category'] in ('sophomore_gain', 'sophomore_held', 'sophomore_byelection'):
        return 'sophomore'
    if r['category'] == 'veteran':
        return 'stand_2' if w == 2 else 'stand_3' if w == 3 else 'stand_4' if w == 4 else 'stand_5plus'
    if r['category'] == 'open':
        return 'open_1' if w <= 1 else 'open_2' if w == 2 else 'open_3' if w == 3 else 'open_4plus'
    return None


TCATS = ['sophomore', 'stand_3', 'stand_4', 'stand_5plus', 'open_1', 'open_2', 'open_3', 'open_4plus']    # baseline stand_2


def fit_cats(rows, catf, cats, rng=None):
    use = [(r, catf(r)) for r in rows if r['change'] is not None and r['party'] in ('ALP', 'COAL', 'GRN', 'IND')]
    use = [(r, k) for r, k in use if k is not None]
    if rng is not None:
        by = defaultdict(list)
        for x in use:
            by[x[0]['to']].append(x)
        use = [by[k][j] for k in by for j in rng.integers(0, len(by[k]), len(by[k]))]
    cells = sorted({(r['to'], r['party']) for r, _ in use}); ci = {c: i for i, c in enumerate(cells)}
    X = np.zeros((len(use), len(cells) + len(cats))); y = np.zeros(len(use))
    for n, (r, k) in enumerate(use):
        X[n, ci[(r['to'], r['party'])]] = 1
        if k in cats:
            X[n, len(cells) + cats.index(k)] = 1
        y[n] = r['change']
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    return dict(zip(cats, beta[len(cells):])), use, resid, X, beta, cells


def tenure(rows):
    out = {}
    for label, sub in (('all', rows), ('uncensored', [r for r in rows if not r['tenure_censored']])):
        b, use, *_ = fit_cats(sub, tenure_cat, TCATS)
        rng = np.random.default_rng(5)
        boots = [fit_cats(sub, tenure_cat, TCATS, rng)[0] for _ in range(1000)]
        res = {'n': len(use), 'counts': {k: sum(1 for _, c in use if c == k) for k in TCATS + ['stand_2']}}
        for k in TCATS:
            v = np.array([x[k] for x in boots])
            res[k] = {'pts': round(100 * b[k], 2), 'lo': round(100 * np.percentile(v, 5), 2), 'hi': round(100 * np.percentile(v, 95), 2)}
        # value of keeping the member, by tenure: standing again minus open seat at the same tenure
        val = {}
        for k, (st, op) in {'2_terms': ('stand_2', 'open_2'), '3_terms': ('stand_3', 'open_3'), '4plus_terms': ('stand_4', 'open_4plus')}.items():
            g = lambda d: (d.get(st, 0.0) if st != 'stand_2' else 0.0) - d[op]
            vv = np.array([g(x) for x in boots])
            val[k] = {'pts': round(100 * g(b), 2), 'lo': round(100 * np.percentile(vv, 5), 2), 'hi': round(100 * np.percentile(vv, 95), 2)}
        res['member_value'] = val
        out[label] = res
        print(f'tenure ({label}, n={len(use)}): ' + '  '.join(f'{k} {res[k]["pts"]:+.1f} [{res[k]["lo"]:+.1f},{res[k]["hi"]:+.1f}] n={res["counts"][k]}' for k in TCATS))
        print('   value of the member standing (vs open seat at the same tenure): ' + '  '.join(f'{k} {v["pts"]:+.1f} [{v["lo"]:+.1f},{v["hi"]:+.1f}]' for k, v in val.items()))
    # leaders' own seats: residual against the same party's other seats at that election (all categories treated as in the main model)
    b, use, resid, *_ = fit_cats(rows, tenure_cat, TCATS)
    lead = []
    for (r, k), e in zip(use, resid):
        for le, seat, role in LEADERS:
            if r['to'] == le and r['seat'] == seat:
                lead.append({'election': le, 'seat': seat, 'member': r['member'], 'party': r['party'], 'role': role, 'residual_pts': round(100 * float(e), 2), 'change_pts': round(100 * float(r['change']), 2)})
    out['leaders'] = lead
    if lead:
        m = np.mean([x['residual_pts'] for x in lead]); prem = [x['residual_pts'] for x in lead if x['role'] == 'Premier']; opp = [x['residual_pts'] for x in lead if x['role'] != 'Premier']
        out['leaders_summary'] = {'n': len(lead), 'mean': round(float(m), 2), 'premier_mean': round(float(np.mean(prem)), 2), 'opposition_mean': round(float(np.mean(opp)), 2)}
        print(f"leaders' seats: n={len(lead)}, mean residual {m:+.1f} (premiers {np.mean(prem):+.1f}, opposition leaders {np.mean(opp):+.1f}): " + '; '.join(f"{x['election']} {x['seat']} {x['residual_pts']:+.1f}" for x in lead))
    return out


if __name__ == '__main__':
    main()
