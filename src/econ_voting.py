"""Does the local economy move the vote? Booth-level swings against local economic change, Victoria.

Unit: a polling-place venue (the same premises at consecutive elections of the same level), with its
SA2 (2021 ASGS) from its coordinates. Outcome: the change in the governing party's first-preference share
at the venue, minus the same change across the other venues of its electorate (so the statewide swing,
the candidates and the sitting member are all taken out, and only local variation within an electorate is left).

Local measures (each as its change over the term, the last 12 months and the last 6 months):
  unemployment rate (DEWR SALM, smoothed, SA2, quarterly 2010-), rents (DFFH moving annual median, all
  properties, suburb groups matched to SA2 names, 2000-), level crossings removed within 1.5 km (state only),
  and where the ABS regional series reach (terms ending 2022 on): median employee income, median house
  price, population, dwelling approvals per head.

Reliability: discover on 2014/2018 state and 2016/2019 federal, confirm on 2022 state, 2022 and 2025 federal;
placebos run through the identical regression: (a) each measure taken from the wrong term (the venue's
previous term), (b) random walks with each SA2's own quarterly volatility (200 draws). Standard errors
clustered by electorate. Effects are points of first preference per one standard deviation of the measure.

Usage: python3 -m src.econ_voting [db] [out_json]
"""
import sys, os, re, json, glob, math, sqlite3, warnings
import numpy as np, pandas as pd
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
warnings.filterwarnings('ignore')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'raw', 'econ')
GOV = {'vic2014': ('vic2010', ['LIB', 'NAT']), 'vic2018': ('vic2014', ['ALP']), 'vic2022': ('vic2018', ['ALP']),
       'fed2016': ('fed2013', ['LIB', 'NAT', 'LNP']), 'fed2019': ('fed2016', ['LIB', 'NAT', 'LNP']), 'fed2022': ('fed2019', ['LIB', 'NAT', 'LNP']), 'fed2025': ('fed2022', ['ALP'])}
DISCOVER = ['vic2014', 'vic2018', 'fed2016', 'fed2019']
CONFIRM = ['vic2022', 'fed2022', 'fed2025']


def venue_panel(con):
    v = pd.read_sql("SELECT venue_id, lat, lon, election_id, date, contest_id, booth_id, party, votes FROM venue_party_share WHERE booth_type = 'ordinary'", con)
    tot = v.groupby(['venue_id', 'election_id']).votes.transform('sum')
    v['share'] = v.votes / tot
    rows = []
    for eid, (prev, gov) in GOV.items():
        a = v[v.election_id == eid]; b = v[v.election_id == prev]
        ga = a[a.party.isin(gov)].groupby('venue_id').share.sum(); gb = b[b.party.isin(gov)].groupby('venue_id').share.sum()
        meta = a.groupby('venue_id').agg(lat=('lat', 'first'), lon=('lon', 'first'), contest_id=('contest_id', 'first'), date=('date', 'first'), votes=('votes', 'sum'))
        both = meta.index.intersection(gb.index)
        d = meta.loc[both].copy(); d['gov_now'] = ga.reindex(both).fillna(0); d['gov_prev'] = gb.reindex(both).fillna(0)
        d['swing'] = 100 * (d.gov_now - d.gov_prev); d['election_id'] = eid; d['prev'] = prev
        d['prev_date'] = b.date.iloc[0]
        rows.append(d.reset_index())
    p = pd.concat(rows, ignore_index=True)
    p = p[p.votes >= 200]
    # within-electorate deviation: the venue's swing minus the vote-weighted swing of the electorate's other venues
    def dev(g):
        w = g.votes; tot = (g.swing * w).sum(); wt = w.sum()
        return g.swing - (tot - g.swing * w) / (wt - w).replace(0, np.nan)
    p['dev'] = p.groupby(['election_id', 'contest_id'], group_keys=False).apply(dev)
    return p.dropna(subset=['dev'])


def add_sa2(p):
    g = json.load(open(os.path.join(ROOT, 'raw', 'boundaries', 'abs', 'sa2_2021_vic.geojson')))
    feats = [f for f in g['features'] if f.get('geometry')]
    polys = [shape(f['geometry']) for f in feats]; codes = [f['properties']['sa2_code_2021'] for f in feats]; names = [f['properties']['sa2_name_2021'] for f in feats]
    tree = STRtree(polys); out_c, out_n = [], []
    for lat, lon in zip(p.lat, p.lon):
        pt = Point(lon, lat); hit = None
        for i in tree.query(pt):
            if polys[i].contains(pt): hit = i; break
        out_c.append(codes[hit] if hit is not None else None); out_n.append(names[hit] if hit is not None else None)
    p['sa2'] = out_c; p['sa2_name'] = out_n
    return p.dropna(subset=['sa2'])


def salm():
    f = glob.glob(os.path.join(RAW, 'salm', '*SA2*.xlsx'))[0]
    df = pd.read_excel(f, 'Smoothed SA2 unemployment rate', header=3)
    df = df.rename(columns={df.columns[0]: 'name', df.columns[1]: 'sa2'}).dropna(subset=['sa2'])
    df['sa2'] = df.sa2.astype(str).str.replace(r'\.0$', '', regex=True)
    cols = [c for c in df.columns if isinstance(c, (pd.Timestamp,)) or re.match(r'\d{4}-\d{2}', str(c))]
    s = df.set_index('sa2')[cols].apply(pd.to_numeric, errors='coerce')
    s.columns = pd.to_datetime([str(c)[:10] for c in cols])
    return s   # rows SA2, columns quarter (first day of the quarter's last month)


def rents():
    f = glob.glob(os.path.join(RAW, 'rents', 'Moving annual*.xlsx'))[0]
    df = pd.read_excel(f, 'All properties', header=None)
    q = df.iloc[1, 2:].ffill().tolist(); kind = df.iloc[2, 2:].tolist()
    cols = [(i + 2, pd.to_datetime(str(qq), format='%b %Y')) for i, (qq, k) in enumerate(zip(q, kind)) if str(k).startswith('Median')]
    out = {}
    for _, r in df.iloc[3:].iterrows():
        name = str(r[1]).strip()
        if not name or name == 'nan' or name.lower().startswith('group total'):
            continue
        ser = pd.Series({d: pd.to_numeric(r[i], errors='coerce') for i, d in cols})
        out[name] = ser
    return pd.DataFrame(out).T   # rows suburb group, columns quarter-end dates


def rent_group_of(sa2_name, groups):
    toks = [t.strip().lower() for t in re.split(r' - |\(|\)', sa2_name) if t.strip()]
    for g in groups:
        parts = [x.strip().lower() for x in re.split(r'-', g)]
        if any(t in parts or t == g.lower() for t in toks):
            return g
    return None


def lxr_sites():
    txt = open(os.path.join(RAW, 'lxrp', 'level_crossing_removal_project.wikitext')).read()
    coords = json.load(open(os.path.join(RAW, 'lxrp', 'station_coordinates.json')))
    out = []
    for blk in txt.split('\n|-'):
        st = re.search(r'\[\[([^\]|]*railway station[^\]|]*)', blk); dt = re.search(r'Date table sorting\|(\d{4})\|(\d{1,2})', blk)
        if st and dt and st.group(1) in coords:
            lat, lon = coords[st.group(1)]; out.append((lat, lon, pd.Timestamp(int(dt.group(1)), int(dt.group(2)), 1)))
    return out


def km(lat1, lon1, lat2, lon2):
    p = math.pi / 180; a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def at(series_row, when):
    """the latest value in a dated series at or before a date"""
    s = series_row.dropna(); s = s[s.index <= when]
    return s.iloc[-1] if len(s) else np.nan


def measures(p, S, R, L):
    groups = list(R.index); rg = {n: rent_group_of(n, groups) for n in p.sa2_name.unique()}
    out = []
    for r in p.itertuples():
        e, pe = pd.Timestamp(r.date), pd.Timestamp(r.prev_date)
        row = {}
        for win, start in [('term', pe), ('12m', e - pd.DateOffset(months=12)), ('6m', e - pd.DateOffset(months=6))]:
            if r.sa2 in S.index:
                u = S.loc[r.sa2]; row[f'unemp_{win}'] = at(u, e) - at(u, start)
            g = rg.get(r.sa2_name)
            if g is not None:
                x = R.loc[g]; a, b = at(x, e), at(x, start)
                row[f'rent_{win}'] = 100 * math.log(a / b) if a and b and a > 0 and b > 0 else np.nan
        if r.election_id.startswith('vic'):
            row['lxr_term'] = sum(1 for la, lo, d in L if pe < d <= e and km(r.lat, r.lon, la, lo) <= 1.5)
        out.append(row)
    return pd.concat([p.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def cluster_ols(y, x, cl):
    """slope of y on x (both demeaned), with standard errors clustered by cl"""
    m = np.isfinite(y) & np.isfinite(x); y, x, cl = y[m], x[m], cl[m]
    if len(y) < 40 or np.nanstd(x) == 0:
        return None
    x = (x - x.mean()) / x.std(); y = y - y.mean()
    b = (x @ y) / (x @ x); u = y - b * x
    meat = sum((x[cl == c] @ u[cl == c]) ** 2 for c in np.unique(cl))
    se = math.sqrt(meat) / (x @ x)
    return {'b': round(float(b), 3), 'se': round(float(se), 3), 't': round(float(b / se), 2) if se else None, 'n': int(len(y))}


def fit(d, col):
    out = {}
    for name, ids in [('discover', DISCOVER), ('confirm', CONFIRM), ('all', DISCOVER + CONFIRM)]:
        s = d[d.election_id.isin(ids)]
        out[name] = cluster_ols(s.dev.values, s[col].values.astype(float), (s.election_id + '|' + s.contest_id).values)
    return out


def main(db=os.path.join(ROOT, 'data', 'elections.sqlite'), out=os.path.join(ROOT, 'data', 'analysis', 'econ_effects.json')):
    con = sqlite3.connect(db)
    p = add_sa2(venue_panel(con)); S = salm(); R = rents(); L = lxr_sites()
    d = measures(p, S, R, L)
    cols = [c for c in d.columns if re.match(r'(unemp|rent|lxr)_', c)]
    res = {c: fit(d, c) for c in cols}
    # between electorates: each electorate's swing (its venues, vote-weighted) against the statewide swing, and its average local change
    def wavg(g, c):
        m = g[c].notna(); return np.average(g.loc[m, c], weights=g.loc[m, 'votes']) if m.any() else np.nan
    seat = d.groupby(['election_id', 'contest_id']).apply(lambda g: pd.Series({'swing': wavg(g, 'swing'), 'votes': g.votes.sum(), **{c: wavg(g, c) for c in cols}})).reset_index()
    seat['dev'] = seat.swing - seat.groupby('election_id').swing.transform('mean')
    seat['_cl'] = seat.election_id + '|' + seat.contest_id
    def fit_seat(c):
        out = {}
        for name, ids in [('discover', DISCOVER), ('confirm', CONFIRM), ('all', DISCOVER + CONFIRM)]:
            s_ = seat[seat.election_id.isin(ids)]
            out[name] = cluster_ols(s_.dev.values, s_[c].values.astype(float), s_._cl.values) if len(s_) >= 50 else None
        return out
    res_seat = {c: fit_seat(c) for c in cols}
    # placebo (a): the same measure from the venue's previous term, against this term's swing
    prevterm = {}
    for c in cols:
        k = d[['venue_id', 'election_id', c]].copy(); nxt = {v: k2 for k2, (v, _) in GOV.items()}
        k['election_id'] = k.election_id.map(nxt); k = k.dropna(subset=['election_id']).rename(columns={c: c + '_prev'})
        dd = d.merge(k, on=['venue_id', 'election_id'], how='inner')
        prevterm[c] = fit(dd, c + '_prev')['all'] if len(dd) else None
    # placebo (b): random walks with each SA2's own volatility, summarised as the spread of t-statistics chance gives
    rng = np.random.default_rng(2026); tstats = []
    vol = S.diff(axis=1).std(axis=1)
    for _ in range(200):
        draw = d.sa2.map(lambda s: rng.normal(0, vol.get(s, np.nan)) if s in vol.index else np.nan).values * np.sqrt(np.maximum(1, (pd.to_datetime(d.date) - pd.to_datetime(d.prev_date)).dt.days.values / 91))
        r = cluster_ols(d.dev.values, draw, (d.election_id + '|' + d.contest_id).values)
        if r: tstats.append(abs(r['t']))
    tstats = np.array(tstats)
    summary = {'venues': int(d.venue_id.nunique()), 'observations': int(len(d)), 'by_election': d.groupby('election_id').size().to_dict(),
               'matched': {c: int(d[c].notna().sum()) for c in cols},
               'placebo_random_walk': {'draws': int(len(tstats)), 'share_abs_t_over_2': round(float((tstats > 2).mean()), 3), 'p95_abs_t': round(float(np.quantile(tstats, 0.95)), 2)},
               'design': {'discover': DISCOVER, 'confirm': CONFIRM, 'outcome': 'governing party first-preference change at the venue minus its electorate (points)', 'scale': 'per one standard deviation of the measure, within the sample'}}
    out_d = {'summary': summary, 'effects': res, 'effects_between_electorates': res_seat, 'electorates': int(len(seat)), 'placebo_previous_term': prevterm,
             'sd': {c: round(float(d[c].std()), 3) for c in cols}, 'mean': {c: round(float(d[c].mean()), 3) for c in cols}}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out_d = json.loads(json.dumps(out_d).replace('NaN', 'null'))   # browsers can't parse NaN
    json.dump(out_d, open(out, 'w'), indent=1)
    print(json.dumps(summary, indent=1))
    for c in cols:
        r = res[c]; f = lambda z: f"{z['b']:+.2f} (t {z['t']:+.1f}, n {z['n']})" if z else '–'
        print(f'{c:12s} discover {f(r["discover"]):28s} confirm {f(r["confirm"]):28s} all {f(r["all"]):28s} prev-term placebo {f(prevterm[c]) if prevterm[c] else "–"}')
        r = res_seat[c]; print(f'{"  seats":12s} discover {f(r["discover"]):28s} confirm {f(r["confirm"]):28s} all {f(r["all"]):28s}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
