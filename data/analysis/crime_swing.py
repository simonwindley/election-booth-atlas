"""Does local crime move the vote? Booth-level swing 2018->2022 v. change in recorded criminal incidents (CSA, year ending June) in the booth's suburb.
Inputs: data/crime/suburb_year_incidents.csv (from CSA Table 03), data/elections.sqlite, site/data/booths.json.gz, site/data/demog_booth_vic2022.json.gz"""
import ast, json, gzip, sqlite3, csv, collections, math, sys
import numpy as np, pandas as pd, statsmodels.formula.api as smf
R = '/'.join(__file__.split('/')[:-3]) or '.'
db = sqlite3.connect(f'{R}/data/elections.sqlite')
Y0, Y1, E0, E1 = int(sys.argv[1]) if len(sys.argv) > 1 else 2018, int(sys.argv[2]) if len(sys.argv) > 2 else 2022, None, None
E0, E1 = f'vic{Y0}', f'vic{Y1}'
# crime by (postcode, suburb) and by postcode
cr = pd.read_csv(f'{R}/data/crime/suburb_year_incidents.csv'); cr['sub'] = cr.suburb.str.lower().str.strip()
cs = cr.groupby(['year', 'postcode', 'sub'])[['total', 'A_person', 'B_property']].sum()
cp = cr.groupby(['year', 'postcode'])[['total', 'A_person', 'B_property']].sum()
# venues -> suburb/postcode
ven = pd.read_sql('select venue_id, suburb, postcode from venues where venue_id is not null', db).drop_duplicates('venue_id')
ven['sub'] = ven.suburb.str.lower().str.strip(); ven['postcode'] = ven.postcode.astype('Int64')
# votes per venue
bj = json.load(gzip.open(f'{R}/site/data/booths.json.gz')); bt = pd.DataFrame(bj['rows'], columns=bj['cols'])
bt = bt[(bt.booth_type == 'ordinary') & bt.election_id.isin([E0, E1]) & bt.venue_id.notna()]
fp = pd.read_sql(f"select f.election_id, f.contest_id, f.booth_id, c.party, f.votes from fp_votes f join candidates c using(election_id, contest_id, candidate_id) where f.election_id in ('{E0}','{E1}')", db)
fp = fp.merge(bt[['election_id', 'contest_id', 'booth_id', 'venue_id']], on=['election_id', 'contest_id', 'booth_id'])
fp['g'] = np.select([fp.party.eq('ALP'), fp.party.isin(['LIB', 'NAT', 'LNP', 'COAL', 'LP', 'NP'])], ['ALP', 'COAL'], 'OTH')
v = fp.pivot_table(index=['election_id', 'venue_id'], columns='g', values='votes', aggfunc='sum', fill_value=0)
v['tot'] = v.sum(axis=1); v = v[v.tot >= 200]
sh = (v[['ALP', 'COAL']].div(v.tot, axis=0) * 100); sh['tot'] = v.tot
a, b = sh.xs(E0), sh.xs(E1); j = a.join(b, lsuffix='0', rsuffix='1', how='inner')
j = j[(j.ALP0 > 0) & (j.ALP1 > 0) & (j.COAL0 > 0) & (j.COAL1 > 0)]
j['swing'] = (j.COAL1 - j.ALP1) - (j.COAL0 - j.ALP0)          # + = towards the Coalition, primary-margin points
# district (as at the later election) for fixed effects
dist = bt[bt.election_id == E1].groupby('venue_id').contest_id.first(); j = j.join(dist.rename('dist'))
# demography (2022 catchments): population growth 2016->2021 and 2021 controls
dm = json.load(gzip.open(f'{R}/site/data/demog_booth_vic2022.json.gz')); DC = dm['cols']; H = dm['hcols']
rows = {}
for vid, rec in dm['booths'].items():
    h = rec.get('h'); h = ast.literal_eval(h) if isinstance(h, str) else h
    p21 = rec['v'][DC.index('population')]; p16 = (h or {}).get('2016', [None])[H.index('population')] if h else None
    rows[vid] = dict(pop21=p21, growth=math.log(p21 / p16) if p16 and p21 else np.nan, inc=rec['v'][DC.index('income_household_median')], age=rec['v'][DC.index('age_median')])
j = j.join(pd.DataFrame.from_dict(rows, orient='index'))
# crime change for the booth's suburb (fallback: postcode)
j = j.join(ven.set_index('venue_id')[['sub', 'postcode']])
def crime(r, y, col):
    try: return cs.loc[(y, int(r.postcode), r['sub']), col]
    except Exception:
        try: return cp.loc[(y, int(r.postcode)), col] if pd.notna(r.postcode) else np.nan
        except Exception: return np.nan
for col in ['total', 'B_property', 'A_person']:
    j[f'{col}0'] = j.apply(lambda r: crime(r, Y0, col), axis=1); j[f'{col}1'] = j.apply(lambda r: crime(r, Y1, col), axis=1)
j = j[(j.total0 >= 30)].dropna(subset=['total1', 'dist'])
for col in ['total', 'B_property', 'A_person']: j[f'd_{col}'] = np.log((j[f'{col}1'] + 1) / (j[f'{col}0'] + 1))
out = {'pair': f'{Y0}->{Y1}', 'venues': len(j), 'mean_swing': round(float(np.average(j.swing, weights=j.tot1)), 2), 'median_crime_change_pct': round(float(np.expm1(j.d_total.median()) * 100), 1)}
for col in ['total', 'B_property', 'A_person']:
    for spec, f in [('raw', f'swing ~ d_{col}'), ('district FE', f'swing ~ d_{col} + C(dist)'), ('district FE + growth', f'swing ~ d_{col} + growth + C(dist)'), ('FE + growth + income + age', f'swing ~ d_{col} + growth + np.log(inc) + age + C(dist)')]:
        m = smf.wls(f, data=j.dropna(subset=['growth', 'inc', 'age']), weights=j.dropna(subset=['growth', 'inc', 'age']).tot1).fit(cov_type='cluster', cov_kwds={'groups': j.dropna(subset=['growth', 'inc', 'age']).dist.astype('category').cat.codes})
        k = f'd_{col}'; out[f'{col} | {spec}'] = f'{m.params[k] * 0.1:+.2f} pts per +10% crime (95% CI {m.conf_int().loc[k, 0] * 0.1:+.2f} to {m.conf_int().loc[k, 1] * 0.1:+.2f}), n={int(m.nobs)}'
# within-district terciles
j['sw_w'] = j.swing - j.groupby('dist').swing.transform('mean'); j['q'] = pd.qcut(j.d_total, 3, labels=['crime fell most', 'middle', 'crime rose most'])
t = j.groupby('q', observed=True).agg(venues=('swing', 'size'), crime_change_pct=('d_total', lambda s: round(float(np.expm1(s.median()) * 100), 1)), swing_vs_district=('sw_w', lambda s: round(float(s.mean()), 2)))
print(json.dumps(out, indent=1)); print(t.to_string())
j.to_csv(f'{R}/data/analysis/crime_swing_{Y0}_{Y1}.csv')
