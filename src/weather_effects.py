"""Election-day weather and the vote (the weather question in analysis/questions.json).

Weather: SILO daily station data (tools/fetch_silo.py -> src.weather_reduce -> data/weather/*.csv). Each polling place
gets the nearest station with an observed rain reading that day (within 25 km), and that station's maximum
temperature (SILO's interpolated surface where the station keeps no thermometer). Voting-hours rain is the reading
of the morning after the election (rainfall is reported for the 24 hours to 9 am).

Outcomes, at each election-day polling place (venue) of every Victorian state (2002-2022) and federal (2004-2025)
general election:
  * votes cast there that day (log), against the same venue at other elections of the same level
  * the informal rate
  * first preferences: Labor, Coalition, Greens, others; and the sitting government's share
The design: venue fixed effects (each place against itself) and district x election fixed effects, so the weather
effect comes from booths in the same district at the same election that got different weather. (With election
effects only, regional swings masquerade as weather: hot booths look like +16 pts to the government because they
were Mallee booths in 2006 and 2014.) Standard errors are clustered by election x region (weather is shared by
neighbouring booths, so the real sample is rainy regions, not booths).

Also: the statewide picture (the wettest and hottest election days), and district-level shares of votes cast on the
day against early and postal votes.

Usage: python3 -m src.weather_effects  -> data/analysis/weather_effects.json
"""
import os, json, gzip, math
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV = {'vic2002': 'ALP', 'vic2006': 'ALP', 'vic2010': 'ALP', 'vic2014': 'COAL', 'vic2018': 'ALP', 'vic2022': 'ALP',
       'fed2004': 'COAL', 'fed2007': 'COAL', 'fed2010': 'ALP', 'fed2013': 'ALP', 'fed2016': 'COAL', 'fed2019': 'COAL', 'fed2022': 'COAL', 'fed2025': 'ALP'}


def rd(name):
    d = json.load(gzip.open(os.path.join(ROOT, f'site/data/{name}.json.gz')))
    return pd.DataFrame(d['rows'], columns=d['cols'])


def g5(p):
    return 'COAL' if p in ('LIB', 'NAT') else p if p in ('ALP', 'GRN', 'ONP') else 'OTH'


def weather():
    S = pd.read_csv(os.path.join(ROOT, 'data/weather/stations.csv'), dtype={'station': str})
    W = pd.read_csv(os.path.join(ROOT, 'data/weather/station_elections.csv'), dtype={'station': str})
    W = W.merge(S[['station', 'lat', 'lon', 'name']], on='station')
    return W


def venues():
    B = rd('booths'); F = rd('fp'); K = rd('candidates')
    B = B[B.election_id.isin(GOV) & B.booth_type.eq('ordinary') & B.venue_id.notna() & B.lat.notna()]
    F = F.merge(B[['election_id', 'booth_id', 'venue_id', 'contest_id']], on=['election_id', 'booth_id'])
    F = F.merge(K[['election_id', 'candidate_id', 'party']], on=['election_id', 'candidate_id'], how='left')
    F['g'] = np.where(F.candidate_id == 'INFORMAL', 'INF', F.party.map(g5).fillna('OTH'))
    V = F.pivot_table(index=['election_id', 'venue_id'], columns='g', values='votes', aggfunc='sum', fill_value=0).reset_index()
    for g in ('ALP', 'COAL', 'GRN', 'ONP', 'OTH', 'INF'):
        if g not in V:
            V[g] = 0
    V['formal'] = V[['ALP', 'COAL', 'GRN', 'ONP', 'OTH']].sum(axis=1); V['total'] = V.formal + V.INF
    V = V[V.total >= 100].copy()
    for g in ('ALP', 'COAL', 'GRN', 'OTH'):
        V[g + '_sh'] = 100 * V[g] / V.formal
    V['informal'] = 100 * V.INF / V.total
    V['gov_sh'] = [100 * getattr(r, GOV[r.election_id]) / r.formal for r in V.itertuples()]
    V['gov_opp'] = [100 * (getattr(r, GOV[r.election_id]) - getattr(r, 'COAL' if GOV[r.election_id] == 'ALP' else 'ALP')) / r.formal for r in V.itertuples()]   # government minus opposition, pts
    V['lab_coal'] = 100 * (V.ALP - V.COAL) / V.formal
    V['log_votes'] = np.log(V.total)
    loc = B.groupby(['election_id', 'venue_id']).agg(lat=('lat', 'mean'), lon=('lon', 'mean'), contest_id=('contest_id', 'first')).reset_index()
    return V.merge(loc, on=['election_id', 'venue_id'])


def assign(V, W):
    out = []
    for e, g in V.groupby('election_id'):
        w = W[(W.election_id == e)].copy()
        wo = w[w.rain_vote_src.isin([0, 15]) & w.rain_vote.notna()]
        lat0 = math.radians(-37.5)
        def nearest(ws, la, lo):
            dx = (ws.lon.values - lo) * 111.32 * math.cos(lat0); dy = (ws.lat.values - la) * 110.57
            d = np.hypot(dx, dy); i = int(np.argmin(d)); return ws.iloc[i], float(d[i])
        rows = []
        for r in g.itertuples():
            s, dist = nearest(wo, r.lat, r.lon)
            rows.append({'station': s.station, 'dist_km': dist, 'rain': s.rain_vote, 'rain_normal': s.rain_vote_normal, 'wet_share': s.rain_vote_wet_share,
                         'tmax': s.tmax, 'tmax_normal': s.tmax_normal, 'rain_30d': s.rain_30d, 'rain_30d_normal': s.rain_30d_normal, 'tmax_30d': s.tmax_30d, 'tmax_30d_normal': s.tmax_30d_normal})
        out.append(pd.concat([g.reset_index(drop=True), pd.DataFrame(rows)], axis=1))
    D = pd.concat(out)
    D = D[D.dist_km <= 25].copy()
    D['wet'] = (D.rain >= 1).astype(int)            # a wet voting day: 1 mm or more
    D['heavy'] = (D.rain >= 10).astype(int)         # 10 mm or more
    D['rain_mm'] = D.rain.clip(upper=40)
    D['hot'] = (D.tmax >= 30).astype(int)
    D['tmax_anom'] = D.tmax - D.tmax_normal
    D['level'] = D.election_id.str[:3]
    # region for clustering: 0.5-degree grid cell
    D['cell'] = D.election_id + '_' + (D.lat * 2).round().astype(str) + '_' + (D.lon * 2).round().astype(str)
    return D


def fe(d, y, xs, fes='venue_id + election_id'):
    import pyfixest as pf
    m = pf.feols(f"{y} ~ {' + '.join(xs)} | {fes}", data=d, vcov={'CRV1': 'cell'})
    t = m.tidy()
    return {x: ({'est': round(float(t.loc[x, 'Estimate']), 3), 'lo': round(float(t.loc[x, '2.5%']), 3), 'hi': round(float(t.loc[x, '97.5%']), 3), 'p': round(float(t.loc[x, 'Pr(>|t|)']), 3)} if x in t.index else None) for x in xs} | {'n': int(m._N)}


def statewide(D):
    """each election: share of booths (vote-weighted) that were wet, heavy, hot; mean rain and tmax"""
    out = []
    for e, g in D.groupby('election_id'):
        w = g.total
        out.append({'election': e, 'wet_share': round(float(np.average(g.wet, weights=w)), 3), 'heavy_share': round(float(np.average(g.heavy, weights=w)), 3),
                    'rain_mm': round(float(np.average(g.rain, weights=w)), 1), 'tmax': round(float(np.average(g.tmax, weights=w)), 1),
                    'tmax_anom': round(float(np.average(g.tmax_anom, weights=w)), 1), 'hot_share': round(float(np.average(g.hot, weights=w)), 3),
                    'rain_30d_ratio': round(float(np.average(g.rain_30d / g.rain_30d_normal.replace(0, np.nan), weights=w)), 2) if g.rain_30d_normal.notna().any() else None,
                    'tmax_30d_anom': round(float(np.average(g.tmax_30d - g.tmax_30d_normal, weights=w)), 1)})
    return out


def main():
    W = weather(); V = venues(); D = assign(V, W)
    D = D[D.groupby('venue_id').venue_id.transform('size') >= 2]
    res = {'about': __doc__.split('\n\n')[0], 'venue_elections': int(len(D)), 'venues': int(D.venue_id.nunique()),
           'median_station_km': round(float(D.dist_km.median()), 1), 'statewide': statewide(D)}
    # the main design: venue effects + district x election effects, so the comparison is booths in the same district at
    # the same election that got different weather (statewide and regional moods drop out)
    D['de'] = D.election_id + '_' + D.contest_id
    res['within_district_sd'] = {'rain_mm': round(float(D.groupby('de').rain_mm.std().mean()), 2), 'tmax': round(float(D.groupby('de').tmax.std().mean()), 2)}
    res['effects'] = {y: fe(D, y, ['rain_mm', 'tmax'], 'venue_id + de') for y in ('log_votes', 'informal', 'gov_opp', 'lab_coal', 'gov_sh', 'ALP_sh', 'COAL_sh', 'GRN_sh', 'OTH_sh')}
    # the naive design (election effects only) for the record: it mistakes regional swings for weather
    res['naive_election_fe_only'] = {y: fe(D, y, ['rain_mm', 'tmax_anom']) for y in ('log_votes', 'informal', 'gov_sh')}
    res['naive_hot_day'] = {'election_fe_only': fe(D, 'gov_opp', ['hot']), 'within_district': fe(D, 'gov_opp', ['hot'], 'venue_id + de'),
                            'hot_booths': int(D.hot.sum()), 'hot_elections': sorted(D[D.hot == 1].election_id.unique().tolist())}
    # 2010: the one statewide deluge, against the elections either side
    C = rd('contests'); B = rd('booths'); F = rd('fp')
    st = ['vic2002', 'vic2006', 'vic2010', 'vic2014', 'vic2018', 'vic2022']
    c = C[C.election_id.isin(st)].groupby('election_id')[['enrolment', 'total_votes', 'informal']].sum()
    B = B[B.election_id.isin(st)]; F = F.merge(B[['election_id', 'booth_id', 'booth_type']], on=['election_id', 'booth_id'])
    T = F.groupby(['election_id', 'booth_type']).votes.sum().unstack(fill_value=0)
    res['vic2010_deluge'] = {e: {'turnout': round(100 * c.loc[e, 'total_votes'] / c.loc[e, 'enrolment'], 2), 'informal': round(100 * c.loc[e, 'informal'] / c.loc[e, 'total_votes'], 2),
                                 'on_the_day': round(100 * T.loc[e, 'ordinary'] / T.loc[e].sum(), 1), 'early': round(100 * T.loc[e, 'early'] / T.loc[e].sum(), 1),
                                 'rain_mm': next(s['rain_mm'] for s in res['statewide'] if s['election'] == e)} for e in st}
    os.makedirs(os.path.join(ROOT, 'data/analysis'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/weather_effects.json'), 'w'), indent=1)
    print(res['venue_elections'], 'venue-elections,', res['venues'], 'venues, median station', res['median_station_km'], 'km')
    for s in res['statewide']:
        print('  ', s)
    f = lambda e: f"{e['est']:+.3f} [{e['lo']:+.3f},{e['hi']:+.3f}]" if e else '-'
    for y, r in res['effects'].items():
        print(f"   {y:9s} per mm rain {f(r['rain_mm'])}   per degree {f(r['tmax'])}")
    print('   2010:', res['vic2010_deluge'])


if __name__ == '__main__':
    main()
