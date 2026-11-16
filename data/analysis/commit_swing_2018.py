"""Did 2018 local election commitments move the 2014->2018 swing? District level (2013 boundaries for both elections)."""
import json, sqlite3, numpy as np, pandas as pd, statsmodels.formula.api as smf
R = '/'.join(__file__.split('/')[:-3]); db = sqlite3.connect(f'{R}/data/elections.sqlite')
t = pd.read_csv(f'{R}/data/commitments/pbo_commitments_2018_tagged.csv'); t = t[t.amount.notna()]
dist = {v.replace(' District', '').strip(): k for k, v in db.execute("select contest_id, contest_name from contests where election_id='vic2018' and contest_id like 'vic-%'")}
money = {}
for _, r in t.iterrows():
    for d, f in json.loads(r.districts).items(): money[(dist[d], r.party)] = money.get((dist[d], r.party), 0) + r.amount * f
fp = pd.read_sql("select f.election_id e, f.contest_id d, c.party p, sum(f.votes) v from fp_votes f join candidates c using(election_id, contest_id, candidate_id) where f.election_id in ('vic2014','vic2018') group by 1,2,3", db)
fp['g'] = np.select([fp.p.eq('ALP'), fp.p.isin(['LIB', 'NAT', 'LNP', 'LP', 'NP'])], ['ALP', 'COAL'], 'OTH')
v = fp.pivot_table(index=['e', 'd'], columns='g', values='v', aggfunc='sum', fill_value=0); v = v.div(v.sum(axis=1), axis=0) * 100
a, b = v.xs('vic2014'), v.xs('vic2018'); d = a.join(b, lsuffix='14', rsuffix='18', how='inner')
d = d[(d.ALP14 > 0) & (d.ALP18 > 0) & (d.COAL14 > 0) & (d.COAL18 > 0)]
d['swing'] = (d.COAL18 - d.ALP18) - (d.COAL14 - d.ALP14); d['margin14'] = d.COAL14 - d.ALP14
d['alp_m'] = [money.get((i, 'ALP'), 0) / 1e6 for i in d.index]; d['coal_m'] = [money.get((i, 'COAL'), 0) / 1e6 for i in d.index]
d['alp_l'] = np.log1p(d.alp_m); d['coal_l'] = np.log1p(d.coal_m); d['close'] = (d.margin14.abs() < 10).astype(int)
print('districts', len(d), 'mean swing to Coalition (primary margin)', round(d.swing.mean(), 2))
print('districts with any local $: ALP', (d.alp_m > 0).sum(), 'COAL', (d.coal_m > 0).sum())
print(d[['alp_m', 'coal_m']].describe().round(1).to_string())
for f in ['swing ~ alp_l + coal_l', 'swing ~ alp_l + coal_l + margin14 + close']:
    m = smf.ols(f, d).fit(cov_type='HC1'); print('\n', f); print(m.summary2().tables[1][['Coef.', '[0.025', '0.975]', 'P>|z|']].round(3).to_string())
d['net'] = d.alp_m - d.coal_m
d['grp'] = np.select([d.net > 5, d.net < -5], ['Labor out-promised Coalition by $5m+', 'Coalition out-promised Labor by $5m+'], 'roughly even (within $5m)')
print(d.groupby('grp').agg(seats=('swing', 'size'), swing=('swing', 'mean'), margin14=('margin14', 'mean')).round(2).to_string())
d.to_csv(f'{R}/data/analysis/commit_swing_2018.csv')
