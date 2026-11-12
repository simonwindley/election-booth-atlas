"""What makes a seat swing more or less than the state? Victorian state 2002-2022 and federal (Victorian divisions) 2007-2025.

The outcome is each seat's deviation from the statewide two-party swing: the change in Labor's share of the final two at
the seat, minus the statewide swing (src.seat_loss.tpp_swing). Seats that were Labor v Coalition both times only; where the
boundaries changed, the starting point is the notional Labor two-party share on the new boundaries (src.notional). The
continuous version of seat_loss: every seat counts, not just the ones that change hands.

Predictors, all signed so that positive means "towards Labor":
  sophomore      a first-term member standing again: +1 Labor, -1 Coalition (the sophomore surge)
  open           the sitting member retired: +1 if a Coalition member retired, -1 if a Labor one did (the open-seat penalty)
  veteran        a member of 3+ terms standing again (+1 Labor, -1 Coalition)
  margin         Labor's two-party margin last time (regression to the mean predicts a negative coefficient)
  momentum       last time's deviation (does a seat that over-swung keep going, or swing back?)
  regional       median booth more than 60 km from the GPO; and regional x statewide swing (do regional seats swing less?)
  demographics   within-election z-scores of degree holders, renters, aged 65+, born overseas, unemployment: each as a trend
                 (a steady drift towards one side) and as elasticity (z x statewide swing: seats that amplify the tide)
Judged out of sample: each election predicted from a model fitted to the others (leave one election out), against the
uniform-swing baseline (every seat swings with the state, deviation 0).

usage: python3 -m src.seat_swing_deviation   -> data/analysis/seat_swing_deviation.json
"""
import os, json, csv, gzip, math, sqlite3
import numpy as np
from src.seat_loss import load, tpp_swing, SERIES

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEMOG_FOR = {'vic2002': 'vic_la_2001', 'vic2006': 'vic_la_2001', 'vic2010': 'vic_la_2001', 'vic2014': 'vic_la_2013', 'vic2018': 'vic_la_2013',
             'vic2022': 'vic_la_2022', 'fed2007': 'fed_2003', 'fed2022': 'fed_2021', 'fed2025': 'fed_2024'}
DEMOG_KEYS = ['bachelor_or_higher', 'rented', 'age_65_plus', 'born_overseas', 'unemployment_rate']


def ols(X, y, ridge=1e-6):
    A = X.T @ X + ridge * np.eye(X.shape[1]); A[0, 0] -= ridge
    return np.linalg.solve(A, X.T @ y)


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    D = load(c)
    sw = {}
    for ser in SERIES.values():
        for i in range(1, len(ser)):
            sw[(ser[i - 1], ser[i])] = tpp_swing(D, ser[i - 1], ser[i])
    NOT = {}
    for rd in json.load(open(os.path.join(ROOT, 'data/analysis/notionals.json')))['redistributions']:
        for st in rd['seats']:
            NOT[(rd['for'], st['seat'])] = st['alp_2pp']
    mem = {}
    for h in csv.DictReader(open(os.path.join(ROOT, 'data/analysis/member_history.csv'))):
        if h['via'] == 'general': mem[(h['to'], h['seat'])] = h
    demog = {}
    for e, b in DEMOG_FOR.items():
        d = json.load(gzip.open(os.path.join(ROOT, f'site/data/demog_{b}.json.gz')))
        demog[e] = {v['name']: v for v in d['districts'].values()}
    classic = lambda T: T is not None and set(T) == {'ALP', 'COAL'}
    rows = []
    for level, ser in SERIES.items():
        for i in range(1, len(ser)):
            t0, t1 = ser[i - 1], ser[i]; S = sw.get((t0, t1))
            if S is None: continue
            tm = ser[i - 2] if i >= 2 else None
            for (e, nm), T1 in D['tcp'].items():
                if e != t1 or not classic(T1): continue
                if (t1, nm) in NOT: a0 = NOT[(t1, nm)]
                elif classic(D['tcp'].get((t0, nm))): a0 = D['tcp'][(t0, nm)]['ALP']
                else: continue
                dev = (T1['ALP'] - a0) - S
                h = mem.get((t1, nm)); sgn = {'ALP': 1, 'COAL': -1}.get(h['party'], 0) if h else 0
                cat = h['category'] if h else ''
                r = dict(level=level, frm=t0, to=t1, seat=nm, swing=S, dev=dev, margin=a0 - 0.5,
                         sophomore=sgn * int(cat.startswith('sophomore')), open=-sgn * int(cat == 'open'),
                         veteran=sgn * int(cat == 'veteran'))
                # momentum: last time's deviation, if the seat was classic and unchanged then
                Tm, T0 = D['tcp'].get((tm, nm)) if tm else None, D['tcp'].get((t0, nm))
                swm = sw.get((tm, t0)) if tm else None
                r['momentum'] = (T0['ALP'] - Tm['ALP'] - swm) if (classic(Tm) and classic(T0) and swm is not None and (t0, nm) not in NOT) else None
                dist = D['dist'].get((t1, nm)); r['regional'] = int(dist > 60) if dist is not None else None
                dm = demog.get(t1, {}).get(nm)
                for k in DEMOG_KEYS: r['raw_' + k] = dm.get(k) if dm else None
                rows.append(r)
    # within-election z-scores of demographics
    for e in {r['to'] for r in rows}:
        for k in DEMOG_KEYS:
            v = np.array([r['raw_' + k] for r in rows if r['to'] == e and r['raw_' + k] is not None], float)
            if len(v) < 10: continue
            m, s = v.mean(), v.std() or 1
            for r in rows:
                if r['to'] == e and r['raw_' + k] is not None: r['z_' + k] = (r['raw_' + k] - m) / s
    print(f'{len(rows)} seat-elections ({sum(r["level"] == "state" for r in rows)} state); deviation SD {100 * np.std([r["dev"] for r in rows]):.2f} pts')

    def design(rs, keys):
        cols = [np.ones(len(rs))]
        for k in keys:
            if k == 'regional_x_swing': cols.append(np.array([r['regional'] * r['swing'] * 100 for r in rs], float))
            elif k.startswith('el_'): cols.append(np.array([r['z_' + k[3:]] * r['swing'] * 100 for r in rs], float))
            else: cols.append(np.array([r[k] * (100 if k in ('margin', 'momentum') else 1) for r in rs], float))
        return np.column_stack(cols)

    def evaluate(rs, keys):
        need = [('z_' + k[3:]) if k.startswith('el_') else ('regional' if k == 'regional_x_swing' else k) for k in keys]
        rs = [r for r in rs if all(r.get(k) is not None for k in need)]
        X0 = design(rs, keys); keep = [j for j in range(1, X0.shape[1]) if X0[:, j].std() > 0]
        if len(keep) < len(keys): print('   dropped constant:', [keys[j - 1] for j in range(1, X0.shape[1]) if j not in keep])
        keys = [keys[j - 1] for j in keep]
        y = np.array([100 * r['dev'] for r in rs]); X = design(rs, keys); b = ols(X, y)
        resid = y - X @ b
        # bootstrap CI, resampling seats within elections
        rng = np.random.default_rng(11); B = []
        idx_by = {}
        for i, r in enumerate(rs): idx_by.setdefault(r['to'], []).append(i)
        for _ in range(300):
            ix = np.concatenate([rng.choice(v, len(v)) for v in idx_by.values()])
            B.append(ols(X[ix], y[ix]))
        B = np.array(B)
        # leave one election out
        se_model, se_uniform = [], []
        for e, ix in idx_by.items():
            tr = np.array([i for i in range(len(rs)) if rs[i]['to'] != e]); te = np.array(ix)
            bb = ols(X[tr], y[tr]); se_model += list((y[te] - X[te] @ bb) ** 2); se_uniform += list(y[te] ** 2)
        return dict(n=len(rs), coef={k: [round(float(b[j + 1]), 3), round(float(np.percentile(B[:, j + 1], 5)), 3), round(float(np.percentile(B[:, j + 1], 95)), 3)] for j, k in enumerate(keys)},
                    intercept=round(float(b[0]), 3), r2=round(1 - resid.var() / y.var(), 3),
                    loeo_rmse=round(math.sqrt(np.mean(se_model)), 3), uniform_rmse=round(math.sqrt(np.mean(se_uniform)), 3))

    core = ['sophomore', 'open', 'veteran', 'margin', 'regional', 'regional_x_swing']
    res = {'method': __doc__.split('\n\n')[1].strip(), 'swing_by_pair': {f'{a}->{b}': round(100 * v, 2) for (a, b), v in sw.items() if v is not None}}
    res['core_all'] = evaluate(rows, core)
    res['core_state'] = evaluate([r for r in rows if r['level'] == 'state'], core)
    res['core_federal'] = evaluate([r for r in rows if r['level'] == 'federal'], core)
    res['with_momentum'] = evaluate(rows, core + ['momentum'])
    dem = ['z_' + k for k in DEMOG_KEYS] + ['el_' + k for k in DEMOG_KEYS]
    res['with_demography'] = evaluate([r for r in rows if r.get('z_bachelor_or_higher') is not None], core + dem)
    res['demography_only_rows_baseline'] = evaluate([r for r in rows if r.get('z_bachelor_or_higher') is not None], core)
    # biggest unexplained deviations (for reading, not modelling)
    res['largest_deviations'] = [dict(seat=r['seat'], election=r['to'], dev_pts=round(100 * r['dev'], 1)) for r in sorted(rows, key=lambda r: -abs(r['dev']))[:15]]
    os.makedirs(os.path.join(ROOT, 'data/analysis'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/seat_swing_deviation.json'), 'w'), indent=1)
    for k in ('core_all', 'core_state', 'core_federal', 'with_momentum', 'demography_only_rows_baseline', 'with_demography'):
        v = res[k]; print(f'\n{k}: n={v["n"]} R2={v["r2"]} LOEO RMSE {v["loeo_rmse"]} vs uniform {v["uniform_rmse"]} (pts)')
        for kk, (b, lo, hi) in v['coef'].items(): print(f'   {kk:22s} {b:+7.3f}  [{lo:+.3f}, {hi:+.3f}]')


if __name__ == '__main__':
    main()
