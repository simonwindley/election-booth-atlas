"""A prediction written down before the 2026 Victorian election, to be checked against the result.

The claim (src/econ_followup.py, seat level): where local unemployment rose in the year before polling day in a
seat that already had high unemployment, the Coalition does worse than its statewide swing; where it fell, or
unemployment was already low, better. Fitted on all seven elections (2014-2025), applied to the 87 districts
(the 2022 boundaries, which 2026 keeps), with Small Area Labour Markets data to June 2026 (the latest quarter
out before polling day).

  python3 -m src.econ_predict_2026            write data/analysis/econ_prediction_2026.json (once; refuses to overwrite)
  python3 -m src.econ_predict_2026 check      after the 2026 results are loaded: score the prediction

The test, fixed now: take each district's Coalition first-preference swing at ordinary polling places
(2022 -> 2026) minus the average district's swing; regress it on the prediction and the district's 2016-census
unemployment rate (the census mix gets its own slope, as in the fit). The prediction passes if its coefficient
is positive with one-sided p < 0.05. We also report the plain correlation. The sha256 of the predictions is
stored in the file so any later change shows.
"""
import sys, os, json, hashlib, sqlite3
import numpy as np, pandas as pd
from .econ_voting import ROOT, add_sa2, salm, rents, lxr_sites, measures
from .econ_groups import panel, census_2016, PARTY
from .econ_followup import seat_table, centred

OUT = os.path.join(ROOT, 'data', 'analysis', 'econ_prediction_2026.json')
M, G, O = 'unemp_12m', 'unemployment_rate', 'sdev_COAL'


def fit_all(con):
    """economy terms fitted on all seven elections, after the census mix's own swing in each election"""
    p = add_sa2(panel(con)); d = measures(p, salm(), rents(), lxr_sites()).merge(census_2016(con), left_on='venue_id', right_index=True, how='left')
    t = centred(seat_table(d, ['COAL'], [G]), M, G, O); parts = []
    for _, k in t.groupby('election_id'):
        A = np.column_stack([np.ones(len(k)), k.gc]); b = np.linalg.lstsq(A, k[O].values, rcond=None)[0]; parts.append(pd.Series(k[O].values - A @ b, index=k.index))
    t['r'] = pd.concat(parts)
    b = np.linalg.lstsq(np.column_stack([t.xc, t.xc * t.gc]), t.r.values, rcond=None)[0]
    return {'b_x': float(b[0]), 'b_xg': float(b[1]), 'n': int(len(t))}


def districts_2026(con):
    v = pd.read_sql("SELECT venue_id, lat, lon, contest_id, SUM(votes) votes FROM venue_party_share WHERE election_id = 'vic2022' AND booth_type = 'ordinary' GROUP BY 1, 2, 3, 4", con)
    v['election_id'] = 'vic2026'; v['date'] = '2026-11-28'; v['prev_date'] = '2022-11-26'
    v = add_sa2(v); v = measures(v, salm(), rents(), lxr_sites()).merge(census_2016(con), left_on='venue_id', right_index=True, how='left')
    w = lambda k, col: np.average(k[col].dropna(), weights=k.loc[k[col].notna(), 'votes']) if k[col].notna().any() else np.nan
    return v.groupby('contest_id').apply(lambda k: pd.Series({M: w(k, M), G: w(k, G)})).reset_index().dropna()


def write():
    if os.path.exists(OUT):
        sys.exit(f'{OUT} exists: the prediction is frozen. Delete it deliberately if you really mean to redo it.')
    con = sqlite3.connect(os.path.join(ROOT, 'data', 'elections.sqlite'))
    c = fit_all(con); s = districts_2026(con)
    names = dict(con.execute("SELECT contest_id, contest_name FROM contests WHERE election_id = 'vic2022'").fetchall()) if con.execute("SELECT name FROM sqlite_master WHERE name = 'contests'").fetchone() else {}
    xc = s[M] - s[M].mean(); gc = s[G] - s[G].mean(); s['pred'] = c['b_x'] * xc + c['b_xg'] * xc * gc
    rows = [{'contest_id': r.contest_id, 'name': names.get(r.contest_id, r.contest_id), 'unemp_change_12m': round(float(r[M]), 2),
             'unemployment_rate_2016': round(100 * float(r[G]), 1), 'coalition_vs_state_pts': round(float(r.pred), 2)} for _, r in s.sort_values('pred').iterrows()]
    body = json.dumps(rows, sort_keys=True)
    out = {'written': pd.Timestamp.now(tz='Australia/Melbourne').isoformat(timespec='minutes'), 'election': 'vic2026 (28 November 2026)',
           'claim': __doc__.split('\n\n')[1].replace('\n', ' '), 'test': __doc__.split('\n\n')[3].replace('\n', ' '),
           'coefficients': c, 'salm_latest_quarter': str(salm().columns.max().date()),
           'spread': {'sd': round(float(s.pred.std()), 2), 'max_abs': round(float(s.pred.abs().max()), 2), 'districts': int(len(s))},
           'sha256': hashlib.sha256(body.encode()).hexdigest(), 'predictions': rows}
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f"wrote {OUT}: {len(rows)} districts, sd {out['spread']['sd']} pts, max {out['spread']['max_abs']} pts, sha256 {out['sha256'][:16]}")
    for r in rows[:5] + rows[-5:]: print(f"  {r['name']:22s} unemployment {r['unemp_change_12m']:+.2f} at {r['unemployment_rate_2016']:.1f}% -> Coalition {r['coalition_vs_state_pts']:+.2f}")


def check():
    P = json.load(open(OUT)); rows = P['predictions']
    assert hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest() == P['sha256'], 'the predictions have changed since they were written'
    con = sqlite3.connect(os.path.join(ROOT, 'data', 'elections.sqlite'))
    v = pd.read_sql("SELECT election_id, contest_id, party, SUM(votes) votes FROM venue_party_share WHERE election_id IN ('vic2022', 'vic2026') AND booth_type = 'ordinary' GROUP BY 1, 2, 3", con)
    if not (v.election_id == 'vic2026').any():
        sys.exit('no vic2026 results in data/elections.sqlite yet')
    v['coal'] = v.party.isin(PARTY['COAL']) * v.votes
    s = v.groupby(['election_id', 'contest_id'])[['coal', 'votes']].sum(); s = (100 * s.coal / s.votes).unstack(0)
    sw = (s['vic2026'] - s['vic2022']).dropna(); sw = sw - sw.mean()
    p = pd.DataFrame(rows).set_index('contest_id').join(sw.rename('actual'), how='inner')
    X = np.column_stack([np.ones(len(p)), p.coalition_vs_state_pts, p.unemployment_rate_2016 - p.unemployment_rate_2016.mean()]); y = p.actual.values
    A = np.linalg.pinv(X.T @ X); b = A @ X.T @ y; u = y - X @ b; se = np.sqrt(np.diag(A @ (X.T * u ** 2) @ X @ A))
    from math import erf, sqrt
    t = b[1] / se[1]; p1 = 0.5 * (1 - erf(t / sqrt(2)))
    res = {'districts': int(len(p)), 'coef': round(float(b[1]), 2), 't': round(float(t), 2), 'p_one_sided': round(float(p1), 4),
           'corr': round(float(np.corrcoef(p.coalition_vs_state_pts, p.actual)[0, 1]), 3), 'passes': bool(b[1] > 0 and p1 < 0.05)}
    print(json.dumps(res, indent=1)); return res


if __name__ == '__main__':
    check() if sys.argv[1:2] == ['check'] else write()
