"""Weather and mood: does the weather on election day (or through the campaign) change WHO votes for whom?
(the weather question in analysis/questions.json, second pass)

Idea: a wet, cold or unusually hot day sours the mood, and a soured voter turns to the Coalition (or to Labor), or
punishes the government, or punishes the local member, some groups more than others (older voters, renters, trades,
graduates, migrants, the religious...). Three contrasts, each a margin so third parties do not blur it:
  Labor v Coalition          change in Labor's share minus the Coalition's
  government v opposition    change in the governing party's share minus the main opposition's
  sitting member's party     change in the share of the party that held the booth's seat going in (Labor, Coalition
                             or Greens seats; independents' seats are left out)

Unit: each election-day polling place, the change since the previous election of that level (state 2006-2022, federal
2007-2025), in points of first preferences. Model, pooled over elections:
    change = district x election effects            (the statewide and local swing: regional mood drops out)
           + group share x election                 (each group's own statewide swing that election)
           + W + sum over groups of  d_g x (W x group share)
W is the weather at the booth (standardised); d_g is the extra swing of a booth with one standard step more of group g
when the weather is one standard step worse. Groups: the census of the booth area (src.demog_change), standardised.

Inference by placebo: the same model is fitted 40 more times with the weather of other Saturdays 2 to 21 weeks either
side of each election (src.weather_placebo). Those days keep the regional patterns of weather but cannot have moved
the vote, so their spread is what chance and regional coincidence produce. A real effect should sit outside it; the
joint test compares the largest group effect on election day with the largest on each placebo day.

Weather measures: voting-hours rain (mm, log); maximum temperature against the normal for the date (cold or hot);
departure from comfortable (|tmax - 22|); campaign rain (30 days, as a share of normal) and campaign temperature.

Usage: python3 -m src.weather_mood  -> data/analysis/weather_mood.json
"""
import os, json, math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV = {'vic2006': 'ALP', 'vic2010': 'ALP', 'vic2014': 'COAL', 'vic2018': 'ALP', 'vic2022': 'ALP',
       'fed2007': 'COAL', 'fed2010': 'ALP', 'fed2013': 'ALP', 'fed2016': 'COAL', 'fed2019': 'COAL', 'fed2022': 'COAL', 'fed2025': 'ALP'}
PAIRS = [('vic2002', 'vic2006'), ('vic2006', 'vic2010'), ('vic2010', 'vic2014'), ('vic2014', 'vic2018'), ('vic2018', 'vic2022'),
         ('fed2004', 'fed2007'), ('fed2007', 'fed2010'), ('fed2010', 'fed2013'), ('fed2013', 'fed2016'), ('fed2016', 'fed2019'), ('fed2019', 'fed2022'), ('fed2022', 'fed2025')]
WVARS = {'rain': 'Rain while voting (log mm)', 'tmax_anom': 'Warmer than normal (deg)', 'discomfort': 'Distance from 22 deg',
         'rain_30d_ratio': 'Wet campaign (30-day rain vs normal)', 'tmax_30d_anom': 'Warm campaign (30-day temp vs normal)'}


def panel():
    import sys
    sys.path.insert(0, ROOT)
    from src.demog_change import venue_shares, census_at, X, XL
    from src.weather_effects import rd
    D = census_at(venue_shares())
    B = rd('booths'); B = B[B.booth_type.eq('ordinary') & B.venue_id.notna() & B.lat.notna()]
    loc = B.groupby('venue_id').agg(lat=('lat', 'mean'), lon=('lon', 'mean'))
    K = rd('candidates')
    K = K[K.elected == 1]
    held = {(e, c): ('COAL' if p in ('LIB', 'NAT') else p if p in ('ALP', 'GRN') else 'OTH') for e, c, p in zip(K.election_id, K.contest_id, K.party)}
    rows = []
    for a, b in PAIRS:
        A = D[D.election_id == a].set_index('venue_id'); Bb = D[D.election_id == b].set_index('venue_id')
        j = A.index.intersection(Bb.index)
        d = pd.DataFrame({'venue_id': j, 'election_id': b, 'contest_id': Bb.loc[j, 'contest_id'].values, 'w': Bb.loc[j, 'tot'].values})
        for p in ('ALP', 'COAL', 'GRN', 'ONP', 'OTH'):
            d['d_' + p] = Bb.loc[j, p].values - A.loc[j, p].values
        d['d_OTH'] = d.d_OTH + d.d_ONP
        gp = GOV[b]; op = 'COAL' if gp == 'ALP' else 'ALP'
        d['d_lab_coal'] = d.d_ALP - d.d_COAL                       # Labor v Coalition (positive: towards Labor)
        d['d_gov_opp'] = d['d_' + gp] - d['d_' + op]               # government v opposition (positive: towards the government)
        inc = [held.get((a, c)) for c in A.loc[j, 'contest_id'].values]   # the party holding the booth's seat going in
        d['inc'] = inc
        d['d_inc'] = [d.loc[i, 'd_' + p] if p in ('ALP', 'COAL', 'GRN') else np.nan for i, p in zip(d.index, inc)]   # sitting member's party
        for k in X:
            d[k] = Bb.loc[j, k].values
        rows.append(d)
    P = pd.concat(rows).dropna(subset=X)
    P = P.join(loc, on='venue_id').dropna(subset=['lat'])
    for k in X:                                   # standardise each group within election
        P[k] = P.groupby('election_id')[k].transform(lambda s: (s - s.mean()) / s.std())
    P['de'] = P.election_id + '_' + P.contest_id
    return P.reset_index(drop=True), X, XL


def weather_for(P, W):
    """nearest station with observed voting-hours rain (25 km) for rain; nearest station for the rest; per election x k"""
    S = pd.read_csv(os.path.join(ROOT, 'data/weather/stations.csv'), dtype={'station': str}).set_index('station')
    W = W.join(S[['lat', 'lon']], on='station')
    out = {}
    lat0 = math.cos(math.radians(-37.5))
    for (e, k), g in W.groupby(['election_id', 'k']):
        v = P[P.election_id == e]
        if not len(v):
            continue
        gx = g.lon.values * 111.32 * lat0; gy = g.lat.values * 110.57
        vx = v.lon.values[:, None] * 111.32 * lat0; vy = v.lat.values[:, None] * 110.57
        dist = np.hypot(vx - gx[None, :], vy - gy[None, :])
        obs = g.rain_obs.values == 1
        dr = np.where(obs[None, :], dist, np.inf); ir = dr.argmin(1); okr = dr[np.arange(len(v)), ir] <= 25
        it = dist.argmin(1)
        res = pd.DataFrame({'idx': v.index, 'rain': np.where(okr, g.rain_vote.values[ir], np.nan), 'tmax': g.tmax.values[it], 'tmax_anom': g.tmax_anom.values[it],
                            'rain_30d_ratio': g.rain_30d_ratio.values[it], 'tmax_30d_anom': g.tmax_30d_anom.values[it]})
        out[(e, k)] = res
    return out


def main():
    import pyfixest as pf
    P, X, XL = panel()
    W = pd.read_csv(os.path.join(ROOT, 'data/weather/placebo_days.csv.gz'), dtype={'station': str})
    W['rain_30d_ratio'] = pd.to_numeric(W.rain_30d_ratio, errors='coerce'); W['tmax_30d_anom'] = pd.to_numeric(W.tmax_30d_anom, errors='coerce')
    Wk = weather_for(P, W)
    ks = sorted({k for (_, k) in Wk})
    # group x election controls (each group's statewide swing that election), built once
    E = sorted(P.election_id.unique())
    ctrl = []
    for k_ in X:
        for e in E[1:]:
            c = f'{k_}__{e}'; P[c] = P[k_] * (P.election_id == e); ctrl.append(c)
    res = {'about': __doc__.split('\n\n')[0], 'venue_pairs': int(len(P)), 'groups': [XL[k] for k in X], 'placebo_days': len(ks) - 1, 'results': {}}
    for wv, wlab in WVARS.items():
        for y in ('d_lab_coal', 'd_gov_opp', 'd_inc'):
            est = {}
            for k in ks:
                d = P.copy()
                wk = pd.concat([Wk[(e, k)] for e in E if (e, k) in Wk]).set_index('idx')
                if wv == 'rain':
                    d['W'] = np.log1p(wk.rain.reindex(d.index))
                elif wv == 'discomfort':
                    d['W'] = (wk.tmax.reindex(d.index) - 22).abs()
                else:
                    d['W'] = wk[wv].reindex(d.index)
                d = d.dropna(subset=['W', y])
                if d.W.std() == 0 or len(d) < 1000:
                    continue
                d['W'] = (d.W - d.W.mean()) / d.W.std()
                for k_ in X:
                    d['Wx_' + k_] = d.W * d[k_]
                fml = f"{y} ~ W + {' + '.join('Wx_' + k_ for k_ in X)} + {' + '.join(X)} + {' + '.join(ctrl)} | de"
                m = pf.feols(fml, data=d, vcov={'CRV1': 'de'})
                t = m.tidy()
                est[k] = {k_: (float(t.loc['Wx_' + k_, 'Estimate']), float(t.loc['Wx_' + k_, 't value'])) for k_ in X} | {'_W': (float(t.loc['W', 'Estimate']), float(t.loc['W', 't value'])), '_n': int(m._N)}
            real = est.get(0)
            if not real:
                continue
            plac = [est[k] for k in ks if k != 0 and k in est]
            r = {'n': real['_n'], 'placebo_days': len(plac), 'groups': {}}
            for k_ in X:
                b, tv = real[k_]
                pb = np.array([p[k_][0] for p in plac])
                r['groups'][XL[k_]] = {'pts': round(b, 3), 't': round(tv, 2), 'placebo_sd': round(float(pb.std()), 3),
                                       'placebo_p': round(float(np.mean(np.abs(pb) >= abs(b))), 3)}
            mx = max(abs(real[k_][1]) for k_ in X); pmx = np.array([max(abs(p[k_][1]) for k_ in X) for p in plac])
            r['joint'] = {'max_abs_t': round(mx, 2), 'placebo_max_abs_t_median': round(float(np.median(pmx)), 2), 'placebo_p': round(float(np.mean(pmx >= mx)), 3)}
            pw = np.array([p['_W'][0] for p in plac])
            r['overall'] = {'pts': round(real['_W'][0], 3), 'placebo_p': round(float(np.mean(np.abs(pw) >= abs(real['_W'][0]))), 3)}
            res['results'][f'{wv}|{y}'] = r
            best = max(r['groups'].items(), key=lambda kv: abs(kv[1]['t']))
            print(f"{wlab:42s} {y:7s} joint: max|t| {r['joint']['max_abs_t']} vs placebo median {r['joint']['placebo_max_abs_t_median']}, p {r['joint']['placebo_p']}; strongest {best[0]} {best[1]['pts']:+.3f} (t {best[1]['t']}, placebo p {best[1]['placebo_p']})", flush=True)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/weather_mood.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
