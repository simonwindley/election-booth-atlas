"""Did 2022 local commitments (PBO post-election costing packs, item level) move the 2018->2022 booth swing? Booths keyed to their 2022 electorate."""
import json, numpy as np, pandas as pd, statsmodels.formula.api as smf
R = '/'.join(__file__.split('/')[:-3])
b = pd.read_csv(f'{R}/data/analysis/crime_swing_2018_2022.csv', index_col=0)   # booth swings + growth/income/age (2022 catchments)
n, m = {}, {}
for p in ('alp', 'lnp'):
    t = pd.read_csv(f'{R}/data/commitments/pbo_2022_{p}_items_tagged.csv')
    for _, r in t[t.places.notna() & (t.places != '')].iterrows():
        for d, f in json.loads(r.districts).items():
            n[(d, p)] = n.get((d, p), 0) + f; m[(d, p)] = m.get((d, p), 0) + (r.amount or 0) * f / 1e6 if pd.notna(r.amount) else m.get((d, p), 0)
for p in ('alp', 'lnp'):
    b[f'n_{p}'] = [n.get((d, p), 0) for d in b.dist]; b[f'l_{p}'] = np.log1p([m.get((d, p), 0) for d in b.dist])
b['margin18'] = b.COAL0 - b.ALP0
print('booths', len(b), 'electorates', b.dist.nunique(), '| electorates with Labor items', (b.groupby('dist').n_alp.first() > 0).sum(), 'Coalition items', (b.groupby('dist').n_lnp.first() > 0).sum())
for f in ['swing ~ n_alp + n_lnp', 'swing ~ n_alp + n_lnp + margin18 + growth + np.log(inc) + age', 'swing ~ l_alp + l_lnp + margin18 + growth + np.log(inc) + age']:
    mm = smf.wls(f, b.dropna(subset=['growth', 'inc', 'age']), weights=b.dropna(subset=['growth', 'inc', 'age']).tot1).fit(cov_type='cluster', cov_kwds={'groups': b.dropna(subset=['growth', 'inc', 'age']).dist.astype('category').cat.codes})
    print('\n', f); print(mm.summary2().tables[1].loc[[k for k in mm.params.index if k[:2] in ('n_', 'l_')], ['Coef.', '[0.025', '0.975]', 'P>|z|']].round(3).to_string())
g = b.assign(any_alp=b.n_alp > 0, any_lnp=b.n_lnp > 0).groupby(['any_alp', 'any_lnp']).apply(lambda x: pd.Series({'booths': len(x), 'swing': np.average(x.swing, weights=x.tot1)})).round(2)
print('\n', g.to_string())
