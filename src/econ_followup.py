"""Economy follow-up: (1) does the unemployment x group pattern move whole seats? (2) exposure tests:
who is exposed to a change, not just where it happened.

1. Between seats. Each electorate's swing for a party minus that party's statewide swing, against the
   electorate's vote-weighted unemployment change over the last 12 / 6 months, its census mix, and the two
   multiplied, compared only within each election (the census mix's own slope is free in every election), on
   the same discover (2014/2018 state, 2016/2019 federal) / confirm (2022 state, 2022/2025 federal) split,
   with wrong-term and shuffled placebos. The booth-level interactions from src.econ_groups are re-run the
   same within-election way (pooling across elections let a year-wide fall in unemployment stand in for
   that year's group swing).
2. Exposure, at the booth (venue minus the rest of its electorate):
   - mortgage holders and owner-occupier mortgage rates (RBA F5 standard variable rate): the change in the
     rate over the term / 12 months / 6 months, which is the same everywhere at one election, times each
     venue's share of households with a mortgage (2016 census). Only the elections where rates moved can
     speak, so the result is shown election by election as well as pooled.
   - renters and local rent growth (DFFH), times the renter share.
   - low-income households and CPI inflation (eight capitals, seasonally adjusted).
   - over-65s (savers) and the cash rate.
Usage: python3 -m src.econ_followup [db] [out_json]
"""
import sys, os, re, csv, json, sqlite3, warnings
import numpy as np, pandas as pd
from .econ_voting import GOV, DISCOVER, CONFIRM, ROOT, add_sa2, salm, rents, lxr_sites, measures
from .econ_groups import panel, census_2016, ols_cl, z
warnings.filterwarnings('ignore')
RAW = os.path.join(ROOT, 'raw', 'econ')
ALL = DISCOVER + CONFIRM


def rba_series(fname, sid):
    rows = list(csv.reader(open(os.path.join(RAW, 'rba', fname), encoding='latin-1')))
    hdr = next(r for r in rows if r and r[0] == 'Series ID'); j = hdr.index(sid)
    out = {}
    for r in rows:
        if r and len(r) > j and r[j].strip():
            for pat, fmt in [(r'\d{2}-[A-Za-z]{3}-\d{4}$', '%d-%b-%Y'), (r'\d{2}/\d{2}/\d{4}$', '%d/%m/%Y')]:
                if re.match(pat, r[0]): out[pd.to_datetime(r[0], format=fmt)] = float(r[j])
    return pd.Series(out).sort_index()


def cpi_index():
    c = pd.read_csv(os.path.join(RAW, 'abs', 'cpi_q.csv'), usecols=['Measure', 'Index', 'Adjustment Type', 'Region', 'TIME_PERIOD', 'OBS_VALUE'])
    c = c[(c.Measure == 'Index Numbers') & (c.Index.str.startswith('All groups CPI'))]   # the file holds the eight-capital average (seasonally adjusted)
    if 'Melbourne' in set(c.Region): c = c[c.Region == 'Melbourne']
    q = c.TIME_PERIOD.str.extract(r'(\d{4})-Q(\d)').astype(int)
    c.index = [pd.Timestamp(y, 3 * k, 28) for y, k in zip(q[0], q[1])]
    return c.OBS_VALUE.astype(float).sort_index()


def at(s, when):
    s = s[s.index <= when]; return float(s.iloc[-1]) if len(s) else np.nan


def national(d):
    rate = rba_series('f5-data.csv', 'FILRHLBVS'); cash = rba_series('f1.1-data.csv', 'FIRMMCRT'); cpi = cpi_index()
    out = {}
    for eid in ALL:
        r = d[d.election_id == eid].iloc[0]; e, pe = pd.Timestamp(r.date), pd.Timestamp(r.prev_date)
        row = {}
        for win, start in [('term', pe), ('12m', e - pd.DateOffset(months=12)), ('6m', e - pd.DateOffset(months=6))]:
            row[f'mrate_{win}'] = at(rate, e) - at(rate, start)
            row[f'cash_{win}'] = at(cash, e) - at(cash, start)
            a, b = at(cpi, e), at(cpi, start); row[f'cpi_{win}'] = 100 * (a / b - 1) if a and b else np.nan
        out[eid] = row
    return pd.DataFrame(out).T


def seat_table(d, outcomes, groups):
    """one row per electorate and election: vote-weighted measures and census mix, and the swing against the statewide one"""
    def wavg(g, c):
        m = g[c].notna(); return np.average(g.loc[m, c], weights=g.loc[m, 'votes']) if m.any() else np.nan
    cols = ['unemp_12m', 'unemp_6m'] + groups + [f'sw_{o}' for o in outcomes]
    s = d.groupby(['election_id', 'contest_id']).apply(lambda g: pd.Series({c: wavg(g, c) for c in cols} | {'votes': g.votes.sum()})).reset_index()
    for o in outcomes:
        s[f'sdev_{o}'] = s[f'sw_{o}'] - s.groupby('election_id')[f'sw_{o}'].transform('mean')
    return s


def hc0(y, X):
    X1 = np.column_stack([np.ones(len(y)), X]); b = np.linalg.lstsq(X1, y, rcond=None)[0]; u = y - X1 @ b
    A = np.linalg.pinv(X1.T @ X1); V = A @ (X1.T * u ** 2) @ X1 @ A
    return b, np.sqrt(np.diag(V))


def centred(t, m, g, o, key=('election_id',)):
    """measure and census share centred within each election (or electorate-election), each scaled to one sd"""
    t = t.dropna(subset=[m, g, o]).copy(); key = list(key)
    t['xc'] = t[m] - t.groupby(key)[m].transform('mean'); t['gc'] = t[g] - t.groupby(key)[g].transform('mean')
    t['x_s'], t['g_s'] = t.xc / t.xc.std(), t.gc / t.gc.std()
    return t


def strict_fit(t, m, g, o, key=('election_id',), cl=None, scaled=True):
    """o ~ x + x*g + g (its slope free in every election). Comparing only within elections, so a year in which
    unemployment fell everywhere and a year in which some group swung everywhere can't masquerade as each other."""
    t = centred(t, m, g, o, key); x, gg = (t.x_s, t.g_s) if scaled else (t.xc, t.gc)
    E = pd.get_dummies(t.election_id).values.astype(float)
    X = np.column_stack([x, x * gg] + [E[:, i] * gg for i in range(E.shape[1])] + [E[:, i] for i in range(1, E.shape[1])])
    if cl is None:
        b, se = hc0(t[o].values, X); n = len(t)
    else:
        r = ols_cl(t[o].values, X, cl(t)); b, se, n = r
    return {'b': round(float(b[2]), 3), 'se': round(float(se[2]), 3), 't': round(float(b[2] / se[2]), 2), 'n': int(n), 'b_main': round(float(b[1]), 3)}


def seat_level(d, outcomes, groups):
    """electorate swing minus the statewide swing, against local unemployment change x census mix, within elections"""
    s = seat_table(d, outcomes, groups)
    res = []
    for o in outcomes:
        for m in ['unemp_12m', 'unemp_6m']:
            for g in groups:
                row = {'outcome': o, 'measure': m, 'group': g}
                for split, ids in [('discover', DISCOVER), ('confirm', CONFIRM)]:
                    t = s[s.election_id.isin(ids)]
                    row[split] = strict_fit(t, m, g, f'sdev_{o}') if t[m].notna().sum() >= 60 else None
                dd, cc = row['discover'], row['confirm']
                row['found'] = bool(dd and abs(dd['t']) >= 2); row['holds'] = bool(row['found'] and cc and abs(cc['t']) >= 2 and np.sign(cc['b']) == np.sign(dd['b']))
                res.append(row)
    return res, s


def seat_check(s, o, m, g, wrong):
    """for a seat-level result that held: each election alone, leave one out, shuffled placebo, wrong-term placebo,
    held-out prediction, and its size in real units"""
    y = f'sdev_{o}'; out = {'outcome': o, 'measure': m, 'group': g, 'all': strict_fit(s, m, g, y)}
    out['each_election'] = {}
    for eid in ALL:
        t = s[s.election_id == eid].dropna(subset=[m, g, y]); x, gz = z(t[m].values), z(t[g].values); b, se = hc0(t[y].values, np.column_stack([x, gz, x * gz]))
        out['each_election'][eid] = {'b': round(float(b[3]), 3), 't': round(float(b[3] / se[3]), 2), 'n': int(len(t))}
    out['without'] = {eid: strict_fit(s[s.election_id != eid], m, g, y)['t'] for eid in ALL}
    rng = np.random.default_rng(11); real = abs(out['all']['t']); ts = []
    for _ in range(1000):
        sh = s.copy(); sh[m] = sh.groupby('election_id')[m].transform(lambda v: rng.permutation(v.values)); ts.append(strict_fit(sh, m, g, y)['t'])
    ts = np.abs(np.array(ts)); out['shuffle'] = {'p': round(float((ts >= real).mean()), 3), 'share_t2': round(float((ts >= 2).mean()), 3)}
    out['wrong_term'] = strict_fit(wrong, m, g, y)
    # held out: take out the census mix's own swing in each election, fit the economy terms on the discovery
    # elections, and predict the confirmation elections
    t = centred(s, m, g, y); parts = []
    for eid, k in t.groupby('election_id'):
        A = np.column_stack([np.ones(len(k)), k.gc]); bb = np.linalg.lstsq(A, k[y].values, rcond=None)[0]; parts.append(pd.Series(k[y].values - A @ bb, index=k.index))
    t['r'] = pd.concat(parts); tr, te = t[t.election_id.isin(DISCOVER)], t[t.election_id.isin(CONFIRM)]
    A = lambda q: np.column_stack([q.xc, q.xc * q.gc]); bb = np.linalg.lstsq(A(tr), tr.r.values, rcond=None)[0]; pred = A(te) @ bb
    out['heldout'] = {'rmse_census': round(float(np.sqrt((te.r ** 2).mean())), 3), 'rmse_with_economy': round(float(np.sqrt(((te.r - pred) ** 2).mean())), 3),
                      'pred_sd': round(float(pred.std()), 2), 'pred_max': round(float(np.abs(pred).max()), 2), 'corr': round(float(np.corrcoef(pred, te.r)[0, 1]), 2), 'n': int(len(te))}
    f = strict_fit(s, m, g, y, scaled=False); bx, bi = f['b_main'], f['b']
    q = np.percentile(t.gc, [10, 90]); mean_rate = float(s[g].mean())
    out['size'] = {'per_point_main': bx, 'per_point_per_rate': bi, 'rate_mean': round(100 * mean_rate, 1),
                   'rate_p10': round(100 * (mean_rate + q[0]), 1), 'rate_p90': round(100 * (mean_rate + q[1]), 1),
                   'per_point_at_p10': round(float(bx + bi * q[0]), 2), 'per_point_at_p90': round(float(bx + bi * q[1]), 2),
                   'change_sd': round(float(t.xc.std()), 2)}
    out['_coef'] = {'b_x': float(bb[0]), 'b_xg': float(bb[1])}
    return out


def booth_recheck(d, rows):
    """the booth-level interactions that held in src.econ_groups, re-run within elections"""
    out = []
    for o, m, g in rows:
        r = {'outcome': o, 'measure': m, 'group': g}
        for split, ids in [('discover', DISCOVER), ('confirm', CONFIRM)]:
            t = d[d.election_id.isin(ids)]
            r[split] = strict_fit(t, m, g, f'dev_{o}', key=('election_id', 'contest_id'), cl=lambda q: (q.election_id + '|' + q.contest_id).values)
        r['holds'] = bool(abs(r['discover']['t']) >= 2 and abs(r['confirm']['t']) >= 2 and np.sign(r['discover']['b']) == np.sign(r['confirm']['b']))
        out.append(r)
    return out


def implied_2026(con, c, m='unemp_12m', g='unemployment_rate'):
    """the held-out coefficients applied to the 2026 districts (2022 boundaries and venues), SALM to the latest quarter"""
    v = pd.read_sql("SELECT venue_id, lat, lon, contest_id, SUM(votes) votes FROM venue_party_share WHERE election_id = 'vic2022' AND booth_type = 'ordinary' GROUP BY 1, 2, 3, 4", con)
    v['election_id'] = 'vic2026'; v['date'] = '2026-11-28'; v['prev_date'] = '2022-11-26'
    v = add_sa2(v); v = measures(v, salm(), rents(), lxr_sites()).merge(census_2016(con), left_on='venue_id', right_index=True, how='left')
    w = lambda k, col: np.average(k[col].dropna(), weights=k.loc[k[col].notna(), 'votes']) if k[col].notna().any() else np.nan
    s = v.groupby('contest_id').apply(lambda k: pd.Series({m: w(k, m), g: w(k, g)})).reset_index().dropna()
    xc = s[m] - s[m].mean(); gc = s[g] - s[g].mean(); s['adj'] = c['b_x'] * xc + c['b_xg'] * xc * gc
    return {'sd': round(float(s.adj.std()), 2), 'max_abs': round(float(s.adj.abs().max()), 2), 'n': int(len(s)),
            'change_mean': round(float(s[m].mean()), 2), 'change_range': [round(float(s[m].min()), 2), round(float(s[m].max()), 2)]}


def exposure(d, N):
    """national change x the venue's exposure share, by election and pooled; plus local rents x renters"""
    tests = [('mrate', 'owned_mortgage', 'Mortgage rates x mortgage holders'), ('cash', 'age_65_plus', 'Cash rate x over-65s'),
             ('cpi', 'income_household_under_1000', 'Inflation x low-income households'), ('rent', 'rented', 'Local rent growth x renters')]
    out = []
    for nat, grp, label in tests:
        for win in ['term', '12m', '6m']:
            col = f'{nat}_{win}'
            for o in ['GOV', 'ALP', 'COAL']:
                per = {}
                for eid in ALL:
                    s = d[(d.election_id == eid)].dropna(subset=[grp, f'dev_{o}'])
                    if nat == 'rent':
                        s = s.dropna(subset=[col]); x = z(s[col].values); g = z(s[grp].values)
                        r = ols_cl(s[f'dev_{o}'].values, np.column_stack([x, g, x * g]), s.contest_id.values); k = 3
                    else:
                        r = ols_cl(s[f'dev_{o}'].values, z(s[grp].values)[:, None], s.contest_id.values); k = 1
                    if r: b, se, n = r; per[eid] = {'b': round(float(b[k]), 3), 'se': round(float(se[k]), 3), 'shock': None if nat == 'rent' else round(float(N.loc[eid, col]), 3), 'n': int(n)}
                row = {'test': label, 'outcome': o, 'window': win, 'by_election': per}
                if nat != 'rent' and len(per) >= 4:
                    # does the group's swing move with the size of the shock across elections? weighted slope, with its spread under shuffled shocks
                    ks = sorted(per); xs = np.array([per[k]['shock'] for k in ks]); ys = np.array([per[k]['b'] for k in ks]); w = 1 / np.array([per[k]['se'] for k in ks]) ** 2
                    if np.ptp(xs) > 0:
                        sl = lambda xx: np.sum(w * (xx - np.average(xx, weights=w)) * (ys - np.average(ys, weights=w))) / np.sum(w * (xx - np.average(xx, weights=w)) ** 2)
                        real = sl(xs); rng = np.random.default_rng(7); perm = np.array([sl(rng.permutation(xs)) for _ in range(5000)])
                        row['slope'] = round(float(real), 3); row['p_perm'] = round(float((np.abs(perm) >= abs(real)).mean()), 3)
                if nat == 'rent':
                    for split, ids in [('discover', DISCOVER), ('confirm', CONFIRM)]:
                        s = d[d.election_id.isin(ids)].dropna(subset=[col, grp, f'dev_{o}'])
                        x, g = z(s[col].values), z(s[grp].values); r = ols_cl(s[f'dev_{o}'].values, np.column_stack([x, g, x * g]), (s.election_id + '|' + s.contest_id).values)
                        if r: b, se, n = r; row[split] = {'b': round(float(b[3]), 3), 'se': round(float(se[3]), 3), 't': round(float(b[3] / se[3]), 2), 'n': int(n)}
                out.append(row)
    return out


def main(db=os.path.join(ROOT, 'data', 'elections.sqlite'), out=os.path.join(ROOT, 'data', 'analysis', 'econ_followup.json')):
    con = sqlite3.connect(db)
    p = add_sa2(panel(con)); d = measures(p, salm(), rents(), lxr_sites()).merge(census_2016(con), left_on='venue_id', right_index=True, how='left')
    N = national(d)
    groups = ['rented', 'born_overseas', 'unemployment_rate', 'owned_mortgage']
    seat, S = seat_level(d, ['GOV', 'ALP', 'COAL'], groups)
    # wrong-term placebo: each venue's measure from the previous term
    nxt = {prev: e for e, (prev, _) in GOV.items()}
    k = d[['venue_id', 'election_id', 'unemp_12m', 'unemp_6m']].copy(); k['election_id'] = k.election_id.map(nxt); k = k.dropna(subset=['election_id'])
    dw = d.drop(columns=['unemp_12m', 'unemp_6m']).merge(k, on=['venue_id', 'election_id'])
    seat_pl, Sw = seat_level(dw, ['GOV', 'ALP', 'COAL'], groups)
    checks = [seat_check(S, r['outcome'], r['measure'], r['group'], Sw) for r in seat if r['holds']]
    booth = booth_recheck(d, [('COAL', 'unemp_12m', 'rented'), ('COAL', 'unemp_12m', 'born_overseas'), ('COAL', 'unemp_12m', 'unemployment_rate'), ('COAL', 'unemp_6m', 'unemployment_rate'), ('COAL', 'unemp_12m', 'owned_mortgage')])
    imp = implied_2026(con, checks[0]['_coef']) if checks else None
    ex = exposure(d, N)
    res = {'national_shocks': N.round(3).to_dict(orient='index'), 'seats': {'electorate_elections': int(len(S)), 'tests': len(seat), 'found': sum(r['found'] for r in seat), 'holds': sum(r['holds'] for r in seat),
           'placebo_found': sum(r['found'] for r in seat_pl), 'placebo_holds': sum(r['holds'] for r in seat_pl), 'results': seat, 'checks': checks, 'implied_2026': imp}, 'booth_recheck': booth, 'exposure': ex}
    res = json.loads(json.dumps(res, default=str).replace('NaN', 'null'))
    json.dump(res, open(out, 'w'), indent=1)
    print('national shocks:\n', N.round(2).to_string())
    print('\nseats:', {k2: v for k2, v in res['seats'].items() if k2 != 'results'})
    f = lambda q: f"{q['b']:+.2f} (t {q['t']:+.1f})" if q else '–'
    for r in seat:
        if r['found'] or (r['confirm'] and abs(r['confirm']['t']) >= 2):
            print(f"  {'HOLDS' if r['holds'] else '     '} {r['outcome']:4s} {r['measure']:9s} x {r['group']:18s} discover {f(r.get('discover')):16s} confirm {f(r.get('confirm'))}")
    for c in checks: print('\ncheck', json.dumps(c))
    print('\n2026:', imp)
    for r in booth: print('booth', r['outcome'], r['measure'], r['group'], f(r['discover']), f(r['confirm']), 'HOLDS' if r['holds'] else '')
    print('\nexposure:')
    for r in ex:
        if 'slope' in r:
            print(f"  {r['test']:36s} {r['outcome']:4s} {r['window']:4s} slope {r['slope']:+.3f} perm p {r['p_perm']:.3f}  per election: " + ', '.join(f"{e[-4:]} {v['b']:+.2f}@{v['shock']:+.2f}" for e, v in sorted(r['by_election'].items())))
        elif r.get('discover'):
            print(f"  {r['test']:36s} {r['outcome']:4s} {r['window']:4s} discover {f(r.get('discover')):16s} confirm {f(r.get('confirm'))}")


if __name__ == '__main__':
    main(*sys.argv[1:3])
