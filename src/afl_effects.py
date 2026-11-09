"""Does the footy move the vote? (the afl question in analysis/questions.json)

Results: every AFL match 1998-2026 from the Squiggle API (tools/fetch_afl.py -> raw/afl/). Club home areas: polling
places within 25 km of Kardinia Park for Geelong (a clear home region), and for the Melbourne clubs within 4 km of
their traditional suburban grounds (nearest club where they overlap; Melbourne, whose ground is the MCG, has no
heartland and is left out). Approximate, deliberately: suburban support is spread far wider than this.

Treatments, for each club area at each Victorian state or federal general election:
  premier            the club won the grand final that year, before the election
  lost_grand_final   lost the grand final that year, before the election
  won_last_game      in-season elections (federal, May-September): won its last match in the 10 days before
  top_four           top four on the ladder at the election (in-season) or at the end of the home-and-away season
Outcome: the change in the government's first-preference margin over the main opposition (points) at the same polling
place since the previous election of that level. Model: area and election effects, so a club area's swing in a good footy year is set against
the same area's swing in other years and against the rest of the state that election. Clustered by area x election.
The study that started this (Healy, Malhotra and Mo, 2010) found a home-team win helped incumbents in the US; a later
re-analysis (Fowler and Montagnes, 2015) found it was very likely a false positive.

Usage: python3 -m src.afl_effects  -> data/analysis/afl_effects.json
"""
import os, json, glob, math, datetime as dt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUNDS = {'Geelong': (-38.1580, 144.3546, 25.0), 'Collingwood': (-37.7998, 144.9958, 4.0), 'Richmond': (-37.8236, 144.9837, 4.0),
           'Essendon': (-37.7487, 144.9174, 4.0), 'Western Bulldogs': (-37.7930, 144.8800, 4.0), 'Hawthorn': (-37.8229, 145.0342, 4.0),
           'St Kilda': (-37.9343, 145.0582, 4.0), 'Carlton': (-37.7840, 144.9617, 4.0), 'North Melbourne': (-37.7992, 144.9439, 4.0)}
ALIAS = {'Footscray': 'Western Bulldogs', 'Kangaroos': 'North Melbourne'}


def games():
    G = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'raw/afl/games_*.json'))):
        for g in json.load(open(f))['games']:
            if g.get('complete') != 100:
                continue
            g['hteam'] = ALIAS.get(g['hteam'], g['hteam']); g['ateam'] = ALIAS.get(g['ateam'], g['ateam'])
            g['winner'] = ALIAS.get(g.get('winner'), g.get('winner'))
            g['when'] = dt.datetime.fromisoformat(g['date'])
            G.append(g)
    return pd.DataFrame(G)


def ladder(G, year, before):
    """home-and-away ladder from completed games of `year` before `before`"""
    g = G[(G.year == year) & (G.is_final == 0) & (G.when < before)]
    pts, pf, pa = {}, {}, {}
    for r in g.itertuples():
        for t, s, o in ((r.hteam, r.hscore, r.ascore), (r.ateam, r.ascore, r.hscore)):
            pts[t] = pts.get(t, 0) + (4 if s > o else 2 if s == o else 0); pf[t] = pf.get(t, 0) + s; pa[t] = pa.get(t, 0) + o
    order = sorted(pts, key=lambda t: (-pts[t], -(pf[t] / max(pa[t], 1))))
    return {t: i + 1 for i, t in enumerate(order)}


def treatments(G, eid, edate):
    when = dt.datetime.combine(edate, dt.time(8, 0))
    y = edate.year
    gf = G[(G.year == y) & (G.is_grand_final == 1) & (G.when < when)]
    gf_final = gf.sort_values('when').tail(1)            # 2010: the replay decides it
    premier = gf_final.winner.iloc[0] if len(gf_final) and gf_final.winner.iloc[0] else None
    loser = None
    if premier:
        r = gf_final.iloc[0]; loser = r.ateam if r.hteam == premier else r.hteam
    in_season = len(G[(G.year == y) & (G.when > when)]) > 0 and len(G[(G.year == y) & (G.when < when)]) > 0
    lad = ladder(G, y, when)
    out = {}
    for club in GROUNDS:
        last = G[((G.hteam == club) | (G.ateam == club)) & (G.when < when) & (G.when >= when - dt.timedelta(days=10))].sort_values('when').tail(1)
        won_last = None
        if in_season and len(last):
            r = last.iloc[0]; won_last = int(r.winner == club); margin = (r.hscore - r.ascore) * (1 if r.hteam == club else -1)
        else:
            margin = None
        out[club] = {'premier': int(premier == club), 'lost_grand_final': int(loser == club), 'in_season': in_season, 'won_last_game': won_last,
                     'last_margin': margin, 'ladder': lad.get(club), 'top_four': int((lad.get(club) or 99) <= 4)}
    return {'premier': premier, 'grand_final_loser': loser, 'in_season': in_season, 'clubs': out}


def area_of(lat, lon):
    best = None
    for club, (la, lo, r) in GROUNDS.items():
        d = math.hypot((lon - lo) * 111.32 * math.cos(math.radians(-37.8)), (lat - la) * 110.57)
        if d <= r and (best is None or d < best[1]):
            best = (club, d)
    return best[0] if best else None


def main():
    import sys
    sys.path.insert(0, ROOT)
    from src.weather_effects import venues, GOV
    import pyfixest as pf
    G = games()
    E = json.load(__import__('gzip').open(os.path.join(ROOT, 'site/data/elections.json.gz'))); E = {r[0]: dt.date.fromisoformat(r[2]) for r in E['rows']}
    T = {e: treatments(G, e, E[e]) for e in GOV}
    V = venues()
    V['area'] = [area_of(a, b) for a, b in zip(V.lat, V.lon)]
    order = {'vic': sorted(e for e in GOV if e.startswith('vic')), 'fed': sorted(e for e in GOV if e.startswith('fed'))}
    prev = {b: a for lv in order.values() for a, b in zip(lv, lv[1:])}
    rows = []
    for e, p in prev.items():
        A = V[V.election_id == p].set_index('venue_id'); B = V[V.election_id == e].set_index('venue_id')
        j = A.index.intersection(B.index)
        gp = GOV[e]; op = 'COAL' if gp == 'ALP' else 'ALP'
        margin = lambda X_: 100 * (X_.loc[j, gp] - X_.loc[j, op]) / X_.loc[j, 'formal']     # government minus opposition, pts
        d = pd.DataFrame({'venue_id': j, 'election_id': e, 'd_gov': (margin(B) - margin(A)).values, 'area': B.loc[j, 'area'].values, 'w': B.loc[j, 'total'].values})
        rows.append(d)
    D = pd.concat(rows)
    D['area'] = D.area.fillna('none')
    for k in ('premier', 'lost_grand_final', 'won_last_game', 'top_four'):
        D[k] = [(T[e]['clubs'][a][k] or 0) if a != 'none' else 0 for e, a in zip(D.election_id, D.area)]
    D['in_season'] = [T[e]['in_season'] for e in D.election_id]
    D['cl'] = D.area + '_' + D.election_id
    res = {'about': __doc__.split('\n\n')[0], 'elections': {e: {k: v for k, v in t.items() if k != 'clubs'} | {'clubs': {c: x for c, x in t['clubs'].items()}} for e, t in T.items()},
           'venue_pairs': int(len(D)), 'area_venues': D[D.area != 'none'].groupby('area').venue_id.nunique().to_dict(), 'effects': {}}
    def fit(formula, d):
        m = pf.feols(formula, data=d, vcov={'CRV1': 'cl'}); t = m.tidy()
        return {x: {'pts': round(float(t.loc[x, 'Estimate']), 2), 'lo': round(float(t.loc[x, '2.5%']), 2), 'hi': round(float(t.loc[x, '97.5%']), 2), 'p': round(float(t.loc[x, 'Pr(>|t|)']), 3)} for x in t.index} | {'n': int(m._N)}
    res['effects']['premiership'] = fit('d_gov ~ premier + lost_grand_final | area + election_id', D)
    res['effects']['top_four'] = fit('d_gov ~ top_four | area + election_id', D)
    Ds = D[D.in_season]
    res['effects']['won_last_game_in_season'] = fit('d_gov ~ won_last_game | area + election_id', Ds[Ds.area != 'none'])
    # Geelong, election by election: its area's government swing against the rest of the state
    gee = []
    for e in sorted(D.election_id.unique()):
        d = D[D.election_id == e]
        a = d[d.area == 'Geelong']; o = d[d.area == 'none']
        if len(a) < 5:
            continue
        t = T[e]['clubs']['Geelong']
        gee.append({'election': e, 'geelong_swing': round(float(np.average(a.d_gov, weights=a.w)), 2), 'rest_swing': round(float(np.average(o.d_gov, weights=o.w)), 2),
                    'difference': round(float(np.average(a.d_gov, weights=a.w) - np.average(o.d_gov, weights=o.w)), 2), 'premier': t['premier'], 'lost_grand_final': t['lost_grand_final'],
                    'ladder': t['ladder'], 'won_last_game': t['won_last_game']})
    res['geelong'] = gee
    g = pd.DataFrame(gee)
    res['geelong_summary'] = {'premiership_years_mean_diff': round(float(g[g.premier == 1].difference.mean()), 2), 'other_years_mean_diff': round(float(g[g.premier == 0].difference.mean()), 2),
                              'other_years_sd': round(float(g[g.premier == 0].difference.std()), 2), 'premiership_elections': g[g.premier == 1].election.tolist()}
    # the in-season win, tested honestly: club-area margin swing against the rest of the state, each area's usual lean
    # removed, wins shuffled across the club-elections
    R = []
    for e in sorted(D[D.in_season].election_id.unique()):
        d = D[D.election_id == e]; rest = np.average(d[d.area == 'none'].d_gov, weights=d[d.area == 'none'].w)
        for c in GROUNDS:
            x = d[d.area == c]; t = T[e]['clubs'][c]
            if len(x) >= 3 and t['won_last_game'] is not None:
                R.append({'club': c, 'dev': float(np.average(x.d_gov, weights=x.w) - rest), 'won': t['won_last_game'], 'margin': t['last_margin']})
    R = pd.DataFrame(R); R['dev2'] = R.dev - R.groupby('club').dev.transform('mean')
    obs = R[R.won == 1].dev2.mean() - R[R.won == 0].dev2.mean(); rng = np.random.default_rng(7); sims = []
    for _ in range(20000):
        w = rng.permutation(R.won.values); sims.append(R.dev2[w == 1].mean() - R.dev2[w == 0].mean())
    res['won_last_game_randomisation'] = {'club_elections': int(len(R)), 'wins': int(R.won.sum()), 'diff_pts': round(float(obs), 2), 'p_permutation': round(float(np.mean(np.abs(sims) >= abs(obs))), 3),
                                          'corr_with_margin': round(float(np.corrcoef(R.margin.astype(float), R.dev2)[0, 1]), 3)}
    print('in-season win, randomisation:', res['won_last_game_randomisation'])
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/afl_effects.json'), 'w'), indent=1, default=str)
    print('venue pairs', res['venue_pairs'], 'area venues', res['area_venues'])
    for e, t in T.items():
        print(f"  {e}: premier {t['premier']}, runner-up {t['grand_final_loser']}, in season {t['in_season']}")
    for k, v in res['effects'].items():
        print(k, {x: y for x, y in v.items()})
    for r in gee:
        print('  Geelong', r)
    print(res['geelong_summary'])


if __name__ == '__main__':
    main()
