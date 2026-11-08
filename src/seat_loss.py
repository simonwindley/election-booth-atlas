"""Seat loss: what predicts a sitting member losing their seat? Victorian state 2002-2022 and federal (Victorian divisions) 2007-2025.

Every sitting member who stands again for the same seat at the next general election of the same level (the rows of
member_history.csv with category veteran, sophomore_* or unknown tenure). The outcome is losing: the member's party does
not win the seat. Two things decide most losses and are fitted first, as the base model:

  margin      the member's two-candidate-preferred margin last time (share of the final two minus 50%)
  swing       the statewide swing to the member's party, two-party (mean change in ALP's share of the final two across
              seats that were Labor v Coalition both times; the Coalition's swing is its negative). It applies only where
              the member's last final two was Labor v Coalition; elsewhere (v Greens, v independent) it is set to zero
              and the non_classic predictor carries the difference. This is hindsight:
              for a coming election it is a scenario, taken from the polls.

Every other candidate predictor is then added to the base model one at a time, and judged three ways: its coefficient (per
standard deviation for continuous predictors) with a bootstrap interval (seats resampled within each election), the
likelihood-ratio improvement, and out-of-sample: the log loss when each election is predicted from a model fitted to the
others (leave one election out). A predictor that only helps in-sample does not survive the last test.

Predictors (all known before polling day, except the statewide swing):
  tenure, sophomore_gain, government (member's party governs at that level), fp (member's party first preferences last time),
  pref_reliance (final-two share minus first preferences: how much of the margin came from preferences), minor (first
  preferences for everyone but Labor and the Coalition last time), minor_trend (change in that since the election before),
  greens, momentum (the seat's two-party swing last time relative to the statewide swing), non_classic (last final two was
  not Labor v Coalition), regional (median booth more than 60 km from Melbourne's GPO), distance (log km), redistribution
  (boundaries changed before this election, so the margin is on old boundaries), enrolment_growth, candidates (number on
  the ballot), leader (premier, prime minister or opposition leader), federal (level).

Members of the Greens and independents are listed but not modelled (too few, and no two-party swing applies).

Where boundaries changed before the election, the margin is the notional one on the new boundaries (src.notional,
data/analysis/notionals.json) for Labor v Coalition contests; notional_check compares that with old-boundary margins.

Inputs  data/elections.sqlite, data/analysis/member_history.csv (src.member_effects), data/analysis/notionals.json (src.notional), site/data/polls_vic2026.json,
        data/analysis/member_effects.json (2026 outlook: who is standing again)
Outputs data/analysis/seat_loss.json, data/analysis/seat_loss_rows.csv
Usage   python3 -m src.seat_loss
"""
import os, csv, json, math, sqlite3, datetime as dt
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUP = {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL'}
SERIES = {'state': ['vic1999', 'vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022'],
          'federal': ['fed2004', 'fed2007', 'fed2010', 'fed2013', 'fed2016', 'fed2019', 'fed2022', 'fed2025']}
GOV_BEFORE = {'vic2002': 'ALP', 'vic2006': 'ALP', 'vic2010': 'ALP', 'vic2014': 'COAL', 'vic2018': 'ALP', 'vic2022': 'ALP', 'vic2026': 'ALP',
              'fed2007': 'COAL', 'fed2010': 'ALP', 'fed2013': 'ALP', 'fed2016': 'COAL', 'fed2019': 'COAL', 'fed2022': 'COAL', 'fed2025': 'ALP'}
REDISTRIBUTION = {'vic2002', 'vic2014', 'vic2022', 'fed2010', 'fed2019', 'fed2022', 'fed2025'}   # new boundaries at this election
LEADERS = {('vic2002', 'Williamstown'), ('vic2002', 'Malvern'), ('vic2006', 'Williamstown'), ('vic2006', 'Hawthorn'), ('vic2010', 'Broadmeadows'),
           ('vic2010', 'Hawthorn'), ('vic2014', 'South-West Coast'), ('vic2014', 'Mulgrave'), ('vic2018', 'Mulgrave'), ('vic2018', 'Bulleen'),
           ('vic2022', 'Mulgrave'), ('vic2022', 'Bulleen'), ('fed2016', 'Maribyrnong'), ('fed2019', 'Maribyrnong')}
GPO = (-37.8136, 144.9631)
BYELECTION_IDS = {'vicby-mulgrave-2023', 'vicby-warrandyte-2023', 'vicby-prahran-2025', 'vicby-werribee-2025', 'vicby-nepean-2026', 'vic2023n'}

PREDICTORS = [   # (key, label, continuous)
    ('tenure', 'Terms already served', True), ('sophomore_gain', 'Won the seat from another party last time', False),
    ('government', "Member's party governs at that level", False), ('fp', 'First-preference share last time', True),
    ('pref_reliance', 'Reliance on preferences last time', True), ('minor', 'Minor-party and independent vote last time', True),
    ('minor_trend', 'Change in that vote last time', True), ('greens', 'Greens vote last time', True),
    ('momentum', 'Seat swung against the state last time', True), ('non_classic', 'Last final two not Labor v Coalition', False),
    ('regional', 'Regional seat (more than 60 km out)', False), ('distance', 'Distance from Melbourne (log)', True),
    ('redistribution', 'New boundaries this election', False), ('enrolment_growth', 'Enrolment growth', True),
    ('candidates', 'Candidates on the ballot', True), ('leader', 'Leader of a major party', False), ('federal', 'Federal seat', False)]


def km(a, b):
    p = math.pi / 180
    x = (b[1] - a[1]) * p * math.cos((a[0] + b[0]) / 2 * p); y = (b[0] - a[0]) * p
    return 6371 * math.hypot(x, y)


def load(c):
    name_of = {(e, cid): nm for e, cid, nm in c.execute('select election_id, contest_id, contest_name from contests')}
    grp = {(e, k): GROUP.get(p, p) for e, k, p in c.execute('select election_id, candidate_id, party from candidates')}
    ncand = defaultdict(int)
    for e, cid in c.execute('select election_id, contest_id from candidates'):
        ncand[(e, name_of.get((e, cid)))] += 1
    tcp = defaultdict(lambda: defaultdict(float))
    for e, cid, k, v in c.execute('select election_id, contest_id, candidate_id, sum(votes) from tcp_votes group by 1, 2, 3'):
        tcp[(e, name_of.get((e, cid)))][grp.get((e, k), 'OTH')] += v or 0
    tcp = {key: {g: v / sum(d.values()) for g, v in d.items()} for key, d in tcp.items() if sum(d.values()) > 0}
    fp = defaultdict(lambda: defaultdict(float)); fptot = defaultdict(lambda: defaultdict(float))
    for e, cid, k, v in c.execute("select election_id, contest_id, candidate_id, sum(votes) from fp_votes where candidate_id <> 'INFORMAL' group by 1, 2, 3"):
        g = grp.get((e, k), 'OTH'); fp[(e, name_of.get((e, cid)))][g] += v or 0; fptot[e][g] += v or 0
    fp = {key: {g: v / sum(d.values()) for g, v in d.items()} for key, d in fp.items() if sum(d.values()) > 0}
    enrol = {(e, name_of.get((e, cid))): en for e, cid, en in c.execute('select election_id, contest_id, enrolment from contests')}
    pts = defaultdict(list)
    for e, cid, lat, lon in c.execute("select election_id, contest_id, lat, lon from booth_geo where booth_type = 'ordinary' and lat is not null"):
        pts[(e, name_of.get((e, cid)))].append((lat, lon))
    dist = {key: km(GPO, (float(np.median([p[0] for p in v])), float(np.median([p[1] for p in v])))) for key, v in pts.items() if v}
    winner = {(e, name_of.get((e, cid))): GROUP.get(p, p) for e, cid, p in c.execute('select election_id, contest_id, party from candidates where elected = 1')}
    return dict(name_of=name_of, tcp=tcp, fp=fp, ncand=ncand, enrol=enrol, dist=dist, winner=winner)


def tpp_swing(D, t0, t1):
    """statewide two-party swing to Labor: mean change in its share of the final two, seats Labor v Coalition both times"""
    d = [D['tcp'][(t1, nm)]['ALP'] - D['tcp'][(t0, nm)]['ALP'] for (e, nm) in D['tcp'] if e == t1 and (t0, nm) in D['tcp']
         and set(D['tcp'][(t1, nm)]) == {'ALP', 'COAL'} and set(D['tcp'][(t0, nm)]) == {'ALP', 'COAL'}]
    return float(np.mean(d)) if d else None


def features(D, P, nm, t0, t1, tm, wins, cat):
    """predictor values for a member of party P in seat nm, last elected at t0 (the election before, tm), facing t1"""
    T0 = D['tcp'].get((t0, nm), {}); F0 = D['fp'].get((t0, nm), {})
    if P not in T0:
        return None
    sw = D['swing'].get((t0, t1)); sw = sw if P == 'ALP' else (-sw if sw is not None else None)
    minor0 = 1 - F0.get('ALP', 0) - F0.get('COAL', 0)
    classic = set(T0) == {'ALP', 'COAL'}
    f = {'margin': T0[P] - 0.5, 'swing': (sw if classic else 0.0) if sw is not None else None, 'tenure': wins, 'sophomore_gain': int(cat == 'sophomore_gain'),
         'government': int(GOV_BEFORE.get(t1) == P), 'fp': F0.get(P, 0), 'pref_reliance': T0[P] - F0.get(P, 0), 'minor': minor0,
         'greens': F0.get('GRN', 0), 'non_classic': int(set(T0) != {'ALP', 'COAL'}), 'redistribution': int(t1 in REDISTRIBUTION),
         'candidates': D['ncand'].get((t1, nm)), 'leader': int((t1, nm) in LEADERS), 'federal': int(t1.startswith('fed'))}
    Fm = D['fp'].get((tm, nm)) if tm else None
    f['minor_trend'] = (minor0 - (1 - Fm.get('ALP', 0) - Fm.get('COAL', 0))) if Fm else None
    Tm = D['tcp'].get((tm, nm)) if tm else None; swm = D['swing'].get((tm, t0)) if tm else None
    if Tm and P in Tm and swm is not None:
        f['momentum'] = (Tm[P] - T0[P]) + (swm if P == 'ALP' else -swm)        # positive = the seat swung against P relative to the state
    else:
        f['momentum'] = None
    d = D['dist'].get((t0, nm))
    f['regional'] = int(d > 60) if d is not None else None
    f['distance'] = math.log(max(d, 1)) if d is not None else None
    e0, e1 = D['enrol'].get((t0, nm)), D['enrol'].get((t1, nm))
    f['enrolment_growth'] = (e1 / e0 - 1) if e0 and e1 else None
    return f


def logit_fit(X, y, ridge=1e-3, w=None):
    b = np.zeros(X.shape[1]); w = np.ones(len(y)) if w is None else w
    R = ridge * np.eye(X.shape[1]); R[0, 0] = 0
    for _ in range(60):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        g = X.T @ (w * (y - p)) - R @ b
        H = (X * (w * p * (1 - p))[:, None]).T @ X + R
        step = np.linalg.solve(H, g); b += step
        if np.abs(step).max() < 1e-8:
            break
    return b


def loglik(X, y, b):
    p = np.clip(1 / (1 + np.exp(-np.clip(X @ b, -30, 30))), 1e-9, 1 - 1e-9)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(p, y):
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    return float(np.mean([(x > neg).mean() + 0.5 * (x == neg).mean() for x in pos]))


def design(rows, keys, scale):
    X = np.ones((len(rows), 1 + len(keys)))
    for j, k in enumerate(keys):
        mu, sd = scale[k]
        X[:, j + 1] = [(r[k] - mu) / sd for r in rows]
    return X


def loeo(rows, keys, scale):
    """leave one election out: total log loss and AUC of out-of-sample predictions"""
    p = np.zeros(len(rows)); y = np.array([r['lost'] for r in rows], float)
    for e in sorted({r['to'] for r in rows}):
        tr = [i for i, r in enumerate(rows) if r['to'] != e]; te = [i for i, r in enumerate(rows) if r['to'] == e]
        X = design(rows, keys, scale); b = logit_fit(X[tr], y[tr])
        p[te] = 1 / (1 + np.exp(-np.clip(X[te] @ b, -30, 30)))
    pc = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.sum(y * np.log(pc) + (1 - y) * np.log(1 - pc))), auc(p, y), p


BASE = ['margin', 'swing']


def assess(rows, scale, extra, rng, nboot=400):
    sub = [r for r in rows if all(r.get(k) is not None for k in BASE + extra)]
    y = np.array([r['lost'] for r in sub], float)
    Xb, Xf = design(sub, BASE, scale), design(sub, BASE + extra, scale)
    bb, bf = logit_fit(Xb, y), logit_fit(Xf, y)
    ll_b, ll_f = loglik(Xb, y, bb), loglik(Xf, y, bf)
    lo_b, auc_b, _ = loeo(sub, BASE, scale); lo_f, auc_f, _ = loeo(sub, BASE + extra, scale)
    by = defaultdict(list)
    for i, r in enumerate(sub):
        by[r['to']].append(i)
    boots = []
    for _ in range(nboot):
        idx = np.concatenate([rng.choice(v, len(v)) for v in by.values()])
        boots.append(logit_fit(Xf[idx], y[idx])[len(BASE) + 1:])
    boots = np.array(boots)
    return {'n': len(sub), 'losses': int(y.sum()), 'coef': [round(float(x), 3) for x in bf[len(BASE) + 1:]],
            'odds_ratio': [round(math.exp(float(x)), 2) for x in bf[len(BASE) + 1:]],
            'lo': [round(math.exp(float(x)), 2) for x in np.percentile(boots, 5, axis=0)], 'hi': [round(math.exp(float(x)), 2) for x in np.percentile(boots, 95, axis=0)],
            'lr': round(2 * (ll_f - ll_b), 2), 'loeo_gain': round(lo_b - lo_f, 2), 'auc_base': round(auc_b, 3), 'auc_with': round(auc_f, 3)}


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    D = load(c)
    D['swing'] = {}
    for ser in SERIES.values():
        for i in range(1, len(ser)):
            D['swing'][(ser[i - 1], ser[i])] = tpp_swing(D, ser[i - 1], ser[i])
    print('statewide two-party swing to Labor: ' + '  '.join(f'{b} {100 * v:+.1f}' for (a, b), v in D['swing'].items() if v is not None))
    hist = list(csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv'))))
    rows, other = [], []
    for h in hist:
        if h['category'] not in ('veteran', 'sophomore_gain', 'sophomore_held', 'sophomore_byelection', ''):
            continue
        ser = SERIES[h['level']]; i = ser.index(h['to']); tm = ser[i - 2] if i >= 2 else None
        base = {'level': h['level'], 'from': h['from'], 'to': h['to'], 'seat': h['seat'], 'member': h['member'], 'party': h['party'],
                'category': h['category'] or 'unknown_tenure', 'lost': int(h['held'] != 'True')}
        if base['lost']:
            w = D['winner'].get((h['to'], h['seat']))
            base['lost_to'] = 'major' if w in ('ALP', 'COAL') else ('GRN' if w == 'GRN' else 'IND/other')
        if h['party'] not in ('ALP', 'COAL'):
            other.append(base); continue
        f = features(D, h['party'], h['seat'], h['from'], h['to'], tm, int(h['wins']), h['category'])
        if f is None:
            other.append(dict(base, note='party not in last final two')); continue
        rows.append({**base, **f})
    # where boundaries changed, use the notional margin on the new boundaries (src.notional) when the contest was Labor v Coalition
    NOT = {}
    npath = os.path.join(ROOT, 'data/analysis/notionals.json')
    if os.path.exists(npath):
        for rd in json.load(open(npath))['redistributions']:
            for st in rd['seats']:
                NOT[(rd['for'], st['seat'])] = st
    for r in rows:
        r['margin_old'] = r['margin']; r['margin_source'] = 'last result'
        st = NOT.get((r['to'], r['seat']))
        if st and not r['non_classic']:
            r['margin'] = (st['alp_2pp'] - 0.5) * (1 if r['party'] == 'ALP' else -1); r['margin_source'] = 'notional'
    print(f'{len(rows)} Labor/Coalition members recontesting, {sum(r["lost"] for r in rows)} lost; not modelled: {len(other)}')
    keys = BASE + [k for k, _, _ in PREDICTORS]
    scale = {}
    for k in keys:
        v = np.array([r[k] for r in rows if r.get(k) is not None], float)
        cont = k in BASE or dict((a, b) for a, _, b in PREDICTORS)[k]
        scale[k] = (float(v.mean()), float(v.std()) or 1.0) if cont else (0.0, 1.0)
    # base model, in natural units (per percentage point) for reading
    y = np.array([r['lost'] for r in rows], float)
    Xn = np.column_stack([np.ones(len(rows)), [100 * r['margin'] for r in rows], [100 * r['swing'] for r in rows]])
    bn = logit_fit(Xn, y)
    lo_base, auc_base, p_base = loeo(rows, BASE, scale)
    res = {'method': __doc__.split('\n\n')[1].strip(), 'n': len(rows), 'losses': int(y.sum()), 'not_modelled': other,
           'swing_by_election': {b: round(100 * v, 2) for (a, b), v in D['swing'].items() if v is not None},
           'base': {'intercept': round(float(bn[0]), 3), 'per_pt_margin': round(float(bn[1]), 3), 'per_pt_swing': round(float(bn[2]), 3),
                    'swing_worth_margin': round(float(bn[2] / bn[1]), 2),
                    # read as a uniform-swing model: the member loses when margin + swing + e < 0; the logistic scale
                    # converts to a normal spread of e (x1.7) and the intercept to how far members beat uniform swing
                    'seat_sd_pts': round(1.7 / abs(float(bn[1])), 2), 'members_beat_uniform_by_pts': round(float(-bn[0] / bn[1]) * -1, 2), 'loeo_logloss': round(lo_base, 2), 'loeo_auc': round(auc_base, 3)}}
    # how much do notional margins help, against the last result on the old boundaries?
    old_rows = [dict(r, margin=r['margin_old']) for r in rows]
    red = [r for r in rows if r['margin_source'] == 'notional']
    res['notional_check'] = {'rows_with_notional_margin': len(red), 'mean_abs_change_pts': round(100 * float(np.mean([abs(r['margin'] - r['margin_old']) for r in red])), 2) if red else None,
                             'loeo_auc_old_margins': round(loeo(old_rows, BASE, scale)[1], 3), 'loeo_auc_notional': round(auc_base, 3),
                             'loeo_logloss_old_margins': round(loeo(old_rows, BASE, scale)[0], 2), 'loeo_logloss_notional': round(lo_base, 2),
                             'redistribution_odds_ratio_old': assess(old_rows, scale, ['redistribution'], np.random.default_rng(7))['odds_ratio'][0]}
    print('   notional margins:', res['notional_check'])
    print(f"   as uniform swing: seat-level spread about {res['base']['seat_sd_pts']} pts (SD); a member's 50:50 point is margin + swing = {-res['base']['members_beat_uniform_by_pts']:+.2f} pts")
    print(f"base: logit = {bn[0]:+.2f} {bn[1]:+.3f}*margin {bn[2]:+.3f}*swing (pts); a point of swing is worth {bn[2] / bn[1]:.2f} pts of margin; out-of-sample AUC {auc_base:.3f}")
    # loss rate by margin band and swing direction
    bands = [(0, 2), (2, 4), (4, 6), (6, 10), (10, 100)]
    res['by_margin'] = []
    for a, b in bands:
        for lab, cond in (('against', lambda r: r['swing'] < 0), ('towards', lambda r: r['swing'] >= 0)):
            s = [r for r in rows if a <= 100 * r['margin'] < b and cond(r)]
            res['by_margin'].append({'band': f'{a}-{b}' if b < 100 else f'{a}+', 'swing': lab, 'n': len(s), 'lost': sum(r['lost'] for r in s)})
    # each predictor on top of the base
    rng = np.random.default_rng(7)
    res['predictors'] = []
    for k, label, cont in PREDICTORS:
        a = assess(rows, scale, [k], rng)
        res['predictors'].append({'key': k, 'label': label, 'continuous': cont, 'per': ('1 SD = ' + fmt_sd(k, scale[k][1])) if cont else 'yes v no',
                                  **{x: (v[0] if isinstance(v, list) else v) for x, v in a.items()}})
        print(f"  {k:17s} n={a['n']:3d} OR {a['odds_ratio'][0]:5.2f} [{a['lo'][0]:5.2f},{a['hi'][0]:5.2f}]  LR {a['lr']:5.1f}  out-of-sample gain {a['loeo_gain']:+5.2f}  AUC {a['auc_base']:.3f}->{a['auc_with']:.3f}")
    # forward selection on out-of-sample log loss (rows complete for every candidate)
    cand = [k for k, _, _ in PREDICTORS if k not in ('distance',)]
    comp = [{**r, **{k: (r[k] if r.get(k) is not None else scale[k][0]) for k in cand}} for r in rows]   # missing values at the mean
    chosen, cur, _ = [], *loeo(comp, BASE, scale)[:2]
    cur_ll = loeo(comp, BASE, scale)[0]; path = [{'added': None, 'loeo_logloss': round(cur_ll, 2)}]
    while True:
        trial = [(loeo(comp, BASE + chosen + [k], scale)[0], k) for k in cand if k not in chosen]
        if not trial:
            break
        ll, k = min(trial)
        if ll > cur_ll - 1.0:            # require a real gain (1 nat) to add a predictor
            break
        chosen.append(k); cur_ll = ll; path.append({'added': k, 'loeo_logloss': round(ll, 2)})
    yc = np.array([r['lost'] for r in comp], float); Xc = design(comp, BASE + chosen, scale); bc = logit_fit(Xc, yc)
    _, auc_final, _ = loeo(comp, BASE + chosen, scale)
    res['final'] = {'n': len(comp), 'losses': int(yc.sum()), 'predictors': BASE + chosen, 'path': path, 'loeo_auc': round(auc_final, 3),
                    'loeo_auc_base_same_rows': round(loeo(comp, BASE, scale)[1], 3),
                    'odds_ratios': {k: round(math.exp(float(b)), 2) for k, b in zip(BASE + chosen, bc[1:])}}
    print(f"final model (n={len(comp)}): {BASE + chosen}  out-of-sample AUC {auc_final:.3f} (base on same rows {res['final']['loeo_auc_base_same_rows']})")
    # upsets: out-of-sample probabilities from the final model, all rows with the predictors
    full = comp
    _, _, pf = loeo(full, BASE + chosen, scale)
    for r, r0, p in zip(full, rows, pf):
        r['p_lose'] = r0['p_lose'] = float(p)
    res['upsets_lost'] = [slim(r) for r in sorted([r for r in full if r['lost']], key=lambda r: r['p_lose'])[:12]]
    res['upsets_held'] = [slim(r) for r in sorted([r for r in full if not r['lost']], key=lambda r: -r['p_lose'])[:12]]
    # who took the seat: the major-party rival, or a Greens/independent challenger the pendulum cannot see
    lost = [r for r in full if r['lost']]
    res['lost_to'] = {}
    for lab, cond in (('all', lambda r: True), ('expected (p >= 0.5)', lambda r: r['p_lose'] >= .5), ('surprise (p < 0.2)', lambda r: r['p_lose'] < .2)):
        s_ = [r for r in lost if cond(r)]
        res['lost_to'][lab] = {'n': len(s_), 'major': sum(r.get('lost_to') == 'major' for r in s_), 'GRN': sum(r.get('lost_to') == 'GRN' for r in s_), 'IND/other': sum(r.get('lost_to') == 'IND/other' for r in s_)}
    print('lost to:', res['lost_to'])
    # calibration
    res['calibration'] = []
    for a, b in ((0, .05), (.05, .15), (.15, .35), (.35, .65), (.65, 1.01)):
        s = [r for r in full if a <= r['p_lose'] < b]
        res['calibration'].append({'band': f'{int(100 * a)}-{min(100, int(100 * b))}%', 'n': len(s), 'predicted': round(sum(r['p_lose'] for r in s), 1), 'lost': sum(r['lost'] for r in s)})
    # 2026: members standing again, under swing scenarios
    res['outlook_2026'] = outlook_2026(c, D, scale, full, chosen)
    with open(os.path.join(ROOT, 'data/analysis/seat_loss_rows.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ['lost_to', 'p_lose'], extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    res['generated'] = dt.date.today().isoformat()
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/seat_loss.json'), 'w'), indent=1)


def fmt_sd(k, sd):
    if k in ('tenure', 'candidates'):
        return f'{sd:.1f}'
    if k == 'distance':
        return f'x{math.exp(sd):.1f} distance'
    return f'{100 * sd:.1f} pts'


def slim(r):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k in
            ('to', 'seat', 'member', 'party', 'category', 'lost_to', 'tenure', 'margin', 'swing', 'momentum', 'minor', 'redistribution', 'government', 'p_lose', 'lost')}


def poll_tpp():
    d = json.load(open(os.path.join(ROOT, 'site/data/polls_vic2026.json')))
    ps = [p for p in d['polls'] if not p.get('election') and (p.get('tpp') or {}).get('ALP')]
    last = max(dt.date.fromisoformat(p['date']) for p in ps)
    rec = [p['tpp']['ALP'] for p in ps if (last - dt.date.fromisoformat(p['date'])).days <= 42]
    return float(np.mean(rec)), len(rec), last.isoformat()


def outlook_2026(c, D, scale, full, chosen):
    me = json.load(open(os.path.join(ROOT, 'data/analysis/member_effects.json')))['outlook_2026']
    tpp, npoll, last = poll_tpp()
    # the last general/by-election for each seat, for the margin
    by_seat = {}
    for e, cid, nm in c.execute("select c.election_id, c.contest_id, c.contest_name from contests c join elections x using (election_id) where x.election_id in ('vic2022', 'vic2023n') or x.level = 'state-by' order by x.date"):
        by_seat[nm] = e
    hist = {(h['seat'], h['to']): h for h in csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv')))}
    # extend the series with 2026 so features() can work: margin from the latest contest, trend from 2018
    D['swing'][('vic2022', 'vic2026')] = 0.0
    for e in BYELECTION_IDS:
        D['swing'][(e, 'vic2026')] = 0.0
    y = np.array([r['lost'] for r in full], float); X = design(full, BASE + chosen, scale); b = logit_fit(X, y)
    s22 = 0.55     # Labor's statewide two-party share in 2022 (VEC)
    scen = {'polls': tpp / 100 - s22, '-3': -0.03, '-6': -0.06, '-9': -0.09}
    out = []
    for m in me:
        if m['category'] == 'open' or m['party'] not in ('ALP', 'COAL'):
            if m['category'] != 'open':
                out.append({'seat': m['seat'], 'member': m['member'], 'party': m['party'], 'category': m['category'], 'note': 'not modelled (not Labor or Coalition)'})
            continue
        t0 = by_seat.get(m['seat'], 'vic2022')
        f = features(D, m['party'], m['seat'], t0, 'vic2026', 'vic2018' if t0 == 'vic2022' else None, m['terms'], m['category'])
        if f is None:
            out.append({'seat': m['seat'], 'member': m['member'], 'party': m['party'], 'category': m['category'], 'note': 'party not in last final two'}); continue
        f['candidates'] = f['candidates'] or float(np.mean([r['candidates'] for r in full]))
        row = {'seat': m['seat'], 'member': m['member'], 'party': m['party'], 'category': m['category'], 'terms': m['terms'], 'margin_pts': round(100 * f['margin'], 1), 'last_contest': t0,
               'vs': next((g for g in D['tcp'][(t0, m['seat'])] if g != m['party']), None)}
        for name, sw in scen.items():
            g = dict(f); g['swing'] = (sw if m['party'] == 'ALP' else -sw) if not f['non_classic'] else 0.0   # a two-party swing does not apply v Greens / independents
            for k in BASE + chosen:
                if g.get(k) is None:
                    g[k] = scale[k][0]
            p = 1 / (1 + math.exp(-float(design([g], BASE + chosen, scale)[0] @ b)))
            row['p_' + name] = round(p, 3)
        out.append(row)
    print(f"2026: {len([o for o in out if 'p_polls' in o])} Labor/Coalition members standing again; polls two-party Labor {tpp:.1f} ({npoll} polls to {last}): swing {100 * scen['polls']:+.1f}")
    risky = sorted([o for o in out if 'p_polls' in o], key=lambda o: -o['p_-6'])[:15]
    print('   most at risk at a 6-pt swing against Labor: ' + ', '.join(f"{o['seat']} {o['p_-6']:.2f}" for o in risky))
    return {'polls_tpp_alp': round(tpp, 1), 'polls_n': npoll, 'polls_to': last, 'scenarios': {k: round(100 * v, 1) for k, v in scen.items()},
            'largest_swing_in_history_pts': round(100 * max(abs(v) for v in D['swing'].values() if v is not None), 1),
            'members': out}


if __name__ == '__main__':
    main()
