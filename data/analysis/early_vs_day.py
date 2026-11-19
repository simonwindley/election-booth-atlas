"""Early (pre-poll) and postal votes v election-day votes, two-candidate-preferred, by seat. Which seats would have gone the other way on election-day votes alone?"""
import sqlite3, pandas as pd, numpy as np
R = '/'.join(__file__.split('/')[:-3]); db = sqlite3.connect(f'{R}/data/elections.sqlite')
rows = []
for el in ['vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022']:
    t = pd.read_sql(f"select t.contest_id c, t.candidate_id k, b.booth_type bt, sum(t.votes) v from tcp_votes t join booths b using(election_id, contest_id, booth_id) where t.election_id='{el}' group by 1,2,3", db)
    cand = pd.read_sql(f"select contest_id c, candidate_id k, party, surname, elected from candidates where election_id='{el}'", db)
    names = dict(pd.read_sql(f"select contest_id, contest_name from contests where election_id='{el}'", db).values)
    t['g'] = t.bt.map({'ordinary': 'day', 'early': 'early', 'postal': 'postal'}).fillna('other')
    for c, x in t.groupby('c'):
        if (x.bt == 'all_votes').any() or x.k.nunique() != 2: continue
        p = x.pivot_table(index='k', columns='g', values='v', aggfunc='sum', fill_value=0); p['all'] = p.sum(axis=1)
        if 'day' not in p or 'early' not in p: continue
        cc = cand[cand.c == c].set_index('k')
        el_ = [k for k in p.index if cc.loc[k, 'elected'] == 1]
        if len(el_) != 1: continue                      # booth 2CP pair is not the official final pair (e.g. Benambra 2018): skip
        w_all = el_[0]; w_day = p['day'].idxmax()
        sh = lambda col, k: 100 * p.loc[k, col] / p[col].sum() if col in p and p[col].sum() else np.nan
        rows.append(dict(election=el[3:], seat=names.get(c, c).replace(' District', ''), winner=f"{cc.loc[w_all, 'surname'].title()} ({cc.loc[w_all, 'party']})", runner=f"{cc.loc[[k for k in p.index if k != w_all][0], 'surname'].title()} ({cc.loc[[k for k in p.index if k != w_all][0], 'party']})",
                         winner_all=round(sh('all', w_all), 2), official_winner_trails_booth_sum=bool(p['all'].idxmax() != w_all), winner_day=round(sh('day', w_all), 2), winner_early=round(sh('early', w_all), 2), winner_postal=round(sh('postal', w_all), 2),
                         share_day=round(100 * p['day'].sum() / p['all'].sum(), 1), share_early=round(100 * p['early'].sum() / p['all'].sum(), 1), share_postal=round(100 * p.get('postal', pd.Series(0)).sum() / p['all'].sum(), 1), flipped=w_day != w_all))
d = pd.DataFrame(rows); d.to_csv(f'{R}/data/analysis/early_vs_day.csv', index=False)
print(d.groupby('election').agg(seats=('seat', 'size'), flipped=('flipped', 'sum'), early_share=('share_early', 'median'), day_share=('share_day', 'median')).to_string())
print('\nSeats where the election-day booths had the other candidate ahead:')
print(d[d.flipped][['election', 'seat', 'winner', 'runner', 'winner_day', 'winner_early', 'winner_postal', 'winner_all']].to_string(index=False))
d['early_gap'] = d.winner_early - d.winner_day
# Labor/Coalition contests: how did Labor's 2CP differ early v on the day?
def lab(r, col):
    return r[col] if '(ALP)' in r.winner else 100 - r[col]
lc = d[d.winner.str.contains(r'\((ALP|LIB|NAT)\)') & d.runner.str.contains(r'\((ALP|LIB|NAT)\)')].copy()
lc['alp_day'] = lc.apply(lambda r: lab(r, 'winner_day'), axis=1); lc['alp_early'] = lc.apply(lambda r: lab(r, 'winner_early'), axis=1); lc['alp_postal'] = lc.apply(lambda r: lab(r, 'winner_postal'), axis=1)
print('\nLabor v Coalition seats: Labor 2CP, median by vote type')
print(lc.groupby('election')[['alp_day', 'alp_early', 'alp_postal']].median().round(1).to_string())
print('\nBiggest early-v-day gaps (2022), Labor v Coalition seats:')
lc['gap'] = lc.alp_early - lc.alp_day
print(lc[lc.election == '2022'].sort_values('gap')[['seat', 'alp_day', 'alp_early', 'alp_postal', 'gap']].head(5).to_string(index=False)); print(lc[lc.election == '2022'].sort_values('gap')[['seat', 'alp_day', 'alp_early', 'alp_postal', 'gap']].tail(5).to_string(index=False))
