"""Footy and mood: when a club is going well, do particular groups swing towards (or away from) the government?
(the afl question in analysis/questions.json, second pass; supporters are spread across the state, so this works
across elections rather than across home areas)

Step 1, group swings: at each pair of consecutive elections (state 2006-2022, federal 2007-2025), three margins at each
polling place (Labor v Coalition; government v opposition; the sitting member's party) are regressed on the census
groups of the booth area (standardised; district effects absorb the local swing). The coefficient is how much more that group's
areas swung that election.
Step 2, form: each club's win rate in that calendar year's matches up to election day (the whole season, finals
included, for elections after the grand final), from every AFL match (raw/afl, tools/fetch_afl.py).
Step 3: for every club x group, the correlation across elections between form and the group's swing.

Inference: a permutation test (shuffling which season goes with which election), and placebo clubs: the interstate
clubs' form should not move Victorian voters, so the share of 'significant' club x group pairs among them is what
chance produces; the Victorian clubs have to beat it.

Usage: python3 -m src.afl_mood  -> data/analysis/afl_mood.json
"""
import os, json, gzip, datetime as dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIC = ['Carlton', 'Collingwood', 'Essendon', 'Geelong', 'Hawthorn', 'Melbourne', 'North Melbourne', 'Richmond', 'St Kilda', 'Western Bulldogs']
INTER = ['Adelaide', 'Brisbane Lions', 'Fremantle', 'Port Adelaide', 'Sydney', 'West Coast']


def group_swings():
    import sys
    sys.path.insert(0, ROOT)
    import pyfixest as pf
    from src.weather_mood import panel
    P, X, XL = panel()
    out = {}
    for e, d in P.groupby('election_id'):
        r = {}
        for y in ('d_lab_coal', 'd_gov_opp', 'd_inc'):
            m = pf.feols(f"{y} ~ {' + '.join(X)} | contest_id", data=d.dropna(subset=[y])); t = m.tidy()
            r[y] = {XL[k]: float(t.loc[k, 'Estimate']) for k in X}
        out[e] = r
    return out, [XL[k] for k in X]


def form(elections):
    import sys
    sys.path.insert(0, ROOT)
    from src.afl_effects import games
    G = games()
    E = {r[0]: dt.date.fromisoformat(r[2]) for r in json.load(gzip.open(os.path.join(ROOT, 'site/data/elections.json.gz')))['rows']}
    out = {}
    for e in elections:
        when = dt.datetime.combine(E[e], dt.time(8))
        g = G[(G.year == E[e].year) & (G.when < when)]
        f = {}
        for c in VIC + INTER:
            m = g[(g.hteam == c) | (g.ateam == c)]
            if len(m) < 4:
                continue
            f[c] = float(np.mean([1.0 if r.winner == c else 0.5 if not r.winner else 0.0 for r in m.itertuples()]))
        out[e] = f
    return out


def main():
    S, groups = group_swings()
    els = sorted(S)
    F = form(els)
    rng = np.random.default_rng(26)
    rows = []
    for c in VIC + INTER:
        es = [e for e in els if c in F[e]]
        if len(es) < 8:
            continue
        f = np.array([F[e][c] for e in es])
        perms = [rng.permutation(len(es)) for _ in range(5000)]
        for y in ('d_lab_coal', 'd_gov_opp', 'd_inc'):
            for g in groups:
                s = np.array([S[e][y][g] for e in es])
                r = float(np.corrcoef(f, s)[0, 1])
                null = np.array([np.corrcoef(f[p], s)[0, 1] for p in perms])
                rows.append({'club': c, 'interstate': c in INTER, 'outcome': y, 'group': g, 'r': round(r, 3), 'p': round(float(np.mean(np.abs(null) >= abs(r))), 4), 'elections': len(es)})
    R = pd.DataFrame(rows)
    summ = {}
    for lab, sub in (('victorian', R[~R.interstate]), ('interstate', R[R.interstate])):
        summ[lab] = {'pairs': int(len(sub)), 'p_below_05': int((sub.p < 0.05).sum()), 'share_below_05': round(float((sub.p < 0.05).mean()), 3),
                     'mean_abs_r': round(float(sub.r.abs().mean()), 3)}
    # BH false-discovery control among the Victorian clubs
    v = R[~R.interstate].sort_values('p').reset_index(drop=True); m = len(v)
    v['q'] = (v.p * m / (np.arange(m) + 1))[::-1].cummin()[::-1].clip(upper=1)
    res = {'about': __doc__.split('\n\n')[0], 'elections': els, 'groups': groups, 'form': F, 'summary': summ,
           'top_victorian': v.head(8).to_dict('records'), 'top_interstate': R[R.interstate].sort_values('p').head(5).to_dict('records'),
           'surviving_fdr': v[v.q < 0.1].to_dict('records'), 'all': rows}
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/afl_mood.json'), 'w'), indent=1)
    print(summ)
    print('top Victorian:'); print(v.head(8)[['club', 'outcome', 'group', 'r', 'p', 'q']].to_string())
    print('top interstate:'); print(R[R.interstate].sort_values('p').head(5)[['club', 'outcome', 'group', 'r', 'p']].to_string())


if __name__ == '__main__':
    main()
