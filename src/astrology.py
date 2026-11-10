"""Things that don't matter (we checked): the sky, and other irrelevant events, against the vote.
(the astrology question in analysis/questions.json; the footy and the weather sit beside it)

The sky on every Victorian state and federal general election day since 1999, at noon in Melbourne (PyEphem):
moon phase, how big the moon looks (its distance; a 'supermoon' within three days), moon sign, sun sign, Mercury / Venus / Mars retrograde, signs of Mars, Jupiter and Saturn, an eclipse
within a fortnight; and some earthly irrelevancies: a full moon within three days, a Friday the 13th in the campaign,
daylight saving, days since the Melbourne Cup.

Outcome: the sitting government's first-preference vote in Victoria, change from the previous election of the same
level (points), and whether it held office. Every test compares elections with and without the feature (difference
in means, exact permutation p-value). The point is the count: with twenty-odd tests on fifteen elections, chance
alone hands over a "significant" result or two; after a correction for the number of tests (Holm), nothing survives.

Second part, the moon by party: the sign the moon was in at noon (local time) on election day against each party's
first-preference change (Labor, Coalition, Greens, One Nation), across 20 elections: Victorian state elections
(2002-2022), federal elections counted in Victoria (2007-2025), and the general elections of the other states we hold
with a previous election to compare (Queensland 2017, 2020, 2024; NSW 2023; WA 2021, 2025; SA 2026). Each sign that
fell on at least two election days, and each element, is compared with the rest for every party (permutation p),
then corrected for the number of tests (Holm, and the false discovery rate).

Third part, the moon's phase and size by party, on the same 20 elections: waxing, more than half full, full or new
within three days, looking bigger than average, a supermoon within three days; and how big it looked as a dial.

Usage: python3 -m src.astrology  -> data/analysis/astrology.json
"""
import os, json, gzip, math, itertools, datetime as dt
import numpy as np
import pandas as pd
import ephem

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNS = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']
ELEMENT = {s: e for s, e in zip(SIGNS, ['fire', 'earth', 'air', 'water'] * 3)}
GOV = {'vic1999': ('COAL', False), 'vic2002': ('ALP', True), 'vic2006': ('ALP', True), 'vic2010': ('ALP', False), 'vic2014': ('COAL', False), 'vic2018': ('ALP', True), 'vic2022': ('ALP', True),
       'fed2004': ('COAL', True), 'fed2007': ('COAL', False), 'fed2010': ('ALP', True), 'fed2013': ('ALP', False), 'fed2016': ('COAL', True), 'fed2019': ('COAL', True), 'fed2022': ('COAL', False), 'fed2025': ('ALP', True)}
PREV = {'vic1999': None, 'vic2002': 'vic1999', 'vic2006': 'vic2002', 'vic2010': 'vic2006', 'vic2014': 'vic2010', 'vic2018': 'vic2014', 'vic2022': 'vic2018',
        'fed2004': None, 'fed2007': 'fed2004', 'fed2010': 'fed2007', 'fed2013': 'fed2010', 'fed2016': 'fed2013', 'fed2019': 'fed2016', 'fed2022': 'fed2019', 'fed2025': 'fed2022'}
PREV_SHARE = {'vic1999': None, 'fed2004': None}


def ecl_lon(body, when):
    body.compute(when)
    return math.degrees(float(ephem.Ecliptic(body).lon)) % 360


def sign(lon):
    return SIGNS[int(lon // 30)]


def retro(cls, when):
    a = ecl_lon(cls(), ephem.Date(when - 1)); b = ecl_lon(cls(), ephem.Date(when + 1))
    return ((b - a + 540) % 360 - 180) < 0


def eclipse_near(when, days=14):
    """a new or full moon within `days` with the moon near a node (ecliptic latitude small)"""
    out = []
    for f, kind, lim in ((ephem.previous_new_moon, 'solar', 1.5), (ephem.next_new_moon, 'solar', 1.5), (ephem.previous_full_moon, 'lunar', 1.0), (ephem.next_full_moon, 'lunar', 1.0)):
        t = f(when)
        m = ephem.Moon(); m.compute(t)
        lat = abs(math.degrees(float(ephem.Ecliptic(m).lat)))
        if abs(t - when) <= days and lat <= lim:
            out.append(kind)
    return out


MEAN_KM = 384400


def moon_extra(when):
    """how big the moon looks (distance), and whether a full moon near perigee (a 'supermoon') is within three days"""
    m = ephem.Moon(); m.compute(when); km = m.earth_distance * ephem.meters_per_au / 1000
    sup = False
    for f in (ephem.previous_full_moon, ephem.next_full_moon):
        t = f(when)
        if abs(t - when) <= 3:
            mm = ephem.Moon(); mm.compute(t); sup = sup or mm.earth_distance * ephem.meters_per_au / 1000 < 360000
    new3 = min(when - ephem.previous_new_moon(when), ephem.next_new_moon(when) - when) <= 3
    return {'moon_km': round(km), 'moon_size_vs_mean': round(MEAN_KM / km - 1, 3), 'supermoon_within_3_days': sup, 'new_moon_within_3_days': new3}


def sky(date):
    noon = ephem.Date(dt.datetime(date.year, date.month, date.day, 1, 0, 0))   # noon in Melbourne (AEDT, UTC+11) ~ 01:00 UTC; AEST elections differ by an hour, irrelevant here
    m = ephem.Moon(); m.compute(noon)
    full_prev, full_next = ephem.previous_full_moon(noon), ephem.next_full_moon(noon)
    new_prev = ephem.previous_new_moon(noon)
    cup = dt.date(date.year, 11, 1); cup += dt.timedelta(days=(1 - cup.weekday()) % 7)   # first Tuesday of November
    campaign = [date - dt.timedelta(days=i) for i in range(0, 33)]
    dst = (date.month >= 10 or date.month <= 3) or (date.month == 4 and date.day <= 7)
    return {**moon_extra(noon), 'moon_illumination': round(m.phase / 100, 3), 'moon_waxing': (noon - new_prev) < 14.77, 'moon_sign': sign(ecl_lon(ephem.Moon(), noon)),
            'sun_sign': sign(ecl_lon(ephem.Sun(), noon)), 'days_from_full_moon': round(min(noon - full_prev, full_next - noon), 1),
            'mercury_retrograde': retro(ephem.Mercury, noon), 'venus_retrograde': retro(ephem.Venus, noon), 'mars_retrograde': retro(ephem.Mars, noon),
            'mars_sign': sign(ecl_lon(ephem.Mars(), noon)), 'jupiter_sign': sign(ecl_lon(ephem.Jupiter(), noon)), 'saturn_sign': sign(ecl_lon(ephem.Saturn(), noon)),
            'eclipse_within_14_days': eclipse_near(noon), 'friday_13th_in_campaign': any(d.day == 13 and d.weekday() == 4 for d in campaign),
            'daylight_saving': dst, 'days_since_melbourne_cup': (date - cup).days if date >= cup else None}


def outcomes():
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/elections.json.gz'))); E = pd.DataFrame(d['rows'], columns=d['cols'])
    k = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz'))); K = pd.DataFrame(k['rows'], columns=k['cols'])
    v = json.load(gzip.open(os.path.join(ROOT, 'site/data/contest_cand.json.gz'))); V = pd.DataFrame(v['rows'], columns=v['cols'])
    X = K.merge(V, on=['election_id', 'contest_id', 'candidate_id'])
    X['g'] = X.party.map(lambda p: 'COAL' if p in ('LIB', 'NAT') else p)
    share = X.groupby(['election_id', 'g']).votes.sum() / X.groupby('election_id').votes.sum()
    out = {}
    for e, (gp, held) in GOV.items():
        s = float(share.get((e, gp), np.nan)) * 100
        p = PREV[e]
        out[e] = {'date': E.set_index('election_id').date[e], 'government': gp, 'held_office': held, 'gov_primary': round(s, 2),
                  'gov_primary_change': round(s - float(share.get((p, gp), np.nan)) * 100, 2) if p else None}
    return out


def perm_test(y, x, n_exact=200000):
    """difference in means of y between x True and False; exact permutation p when feasible"""
    y = np.asarray(y, float); x = np.asarray(x, bool)
    k = int(x.sum()); n = len(y)
    if k == 0 or k == n:
        return None
    obs = y[x].mean() - y[~x].mean()
    combos = math.comb(n, k)
    rng = np.random.default_rng(13)
    if combos <= n_exact:
        diffs = [y[list(c)].mean() - np.delete(y, list(c)).mean() for c in itertools.combinations(range(n), k)]
    else:
        diffs = []
        for _ in range(n_exact // 4):
            idx = rng.choice(n, k, replace=False); diffs.append(y[idx].mean() - np.delete(y, idx).mean())
    diffs = np.array(diffs)
    return {'diff': round(float(obs), 2), 'p': round(float(np.mean(np.abs(diffs) >= abs(obs) - 1e-9)), 3), 'n_with': k, 'n': n}


OTHER_STATES = {'qld2015': ('2015-01-31', 'QLD', None), 'qld2017': ('2017-11-25', 'QLD', 'qld2015'), 'qld2020': ('2020-10-31', 'QLD', 'qld2017'), 'qld2024': ('2024-10-26', 'QLD', 'qld2020'),
                'nsw2019': ('2019-03-23', 'NSW', None), 'nsw2023': ('2023-03-25', 'NSW', 'nsw2019'), 'wa2017': ('2017-03-11', 'WA', None), 'wa2021': ('2021-03-13', 'WA', 'wa2017'),
                'wa2025': ('2025-03-08', 'WA', 'wa2021'), 'sa2022': ('2022-03-19', 'SA', None), 'sa2026': ('2026-03-21', 'SA', 'sa2022')}
PARTIES = ('ALP', 'COAL', 'GRN', 'ONP')


def utc_offset(state, date):
    dst = (date.month >= 10 or date.month <= 3) or (date.month == 4 and date.day <= 6)
    return {'QLD': 10, 'WA': 8, 'SA': 10.5 if dst else 9.5}.get(state, 11 if dst else 10)


def moon_sign_local_noon(date, state):
    t = dt.datetime(date.year, date.month, date.day, 12) - dt.timedelta(hours=utc_offset(state, date))
    return sign(ecl_lon(ephem.Moon(), ephem.Date(t)))


def party_changes():
    """one row per election: date, place, moon sign at local noon, each party's statewide first-preference change (pts)"""
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/elections.json.gz'))); E = pd.DataFrame(d['rows'], columns=d['cols']).set_index('election_id')
    k = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz'))); K = pd.DataFrame(k['rows'], columns=k['cols'])
    v = json.load(gzip.open(os.path.join(ROOT, 'site/data/contest_cand.json.gz'))); V = pd.DataFrame(v['rows'], columns=v['cols'])
    X = K.merge(V, on=['election_id', 'contest_id', 'candidate_id'])
    X['g'] = X.party.map(lambda p: 'COAL' if p in ('LIB', 'NAT') else p)
    share = (100 * X.groupby(['election_id', 'g']).votes.sum() / X.groupby('election_id').votes.sum()).to_dict()
    rows = []
    for e, p in PREV.items():
        if p:
            date = dt.date.fromisoformat(E.date[e])
            rows.append({'election': e, 'place': 'Victoria' if e.startswith('vic') else 'Federal (Victoria)', 'date': str(date), 'moon_sign': moon_sign_local_noon(date, 'VIC'),
                         **{g: round(share.get((e, g), 0) - share.get((p, g), 0), 2) for g in PARTIES}})
    S = json.load(open(os.path.join(ROOT, 'data/national/state_results.json')))['seats']
    tot = {}
    for r in S:
        if r['election_id'] in OTHER_STATES:
            t = tot.setdefault(r['election_id'], {})
            for c in r['candidates']:
                g = 'COAL' if c['party'] in ('LIB', 'NAT', 'LNP', 'CLP') else c['party']
                t[g] = t.get(g, 0) + (c['fp'] or 0)
    sh = {e: {g: 100 * x / sum(t.values()) for g, x in t.items()} for e, t in tot.items()}
    for e, (ds, st, p) in OTHER_STATES.items():
        if p and e in sh and p in sh:
            date = dt.date.fromisoformat(ds)
            rows.append({'election': e, 'place': {'QLD': 'Queensland', 'NSW': 'New South Wales', 'WA': 'Western Australia', 'SA': 'South Australia'}[st], 'date': ds,
                         'moon_sign': moon_sign_local_noon(date, st), **{g: round(sh[e].get(g, 0) - sh[p].get(g, 0), 2) for g in PARTIES}})
    return pd.DataFrame(rows)


def adjust(tests):
    """Holm and Benjamini-Hochberg across a family of tests (in place)"""
    m = len(tests); order = sorted(range(m), key=lambda i: tests[i]['p']); running = 0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * tests[i]['p'])); tests[i]['p_holm'] = round(running, 3)
    q = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]; q = min(q, tests[i]['p'] * m / (rank + 1)); tests[i]['q_fdr'] = round(q, 3)


def moon_by_party():
    P = party_changes()
    tests = []
    feats = {f'Moon in {s}': P.moon_sign == s for s in SIGNS if 2 <= (P.moon_sign == s).sum() <= len(P) - 2}
    feats.update({f'Moon in a {el} sign': P.moon_sign.map(ELEMENT) == el for el in ('fire', 'earth', 'air', 'water')})
    for name, x in feats.items():
        for g in PARTIES:
            r = perm_test(P[g].values, x.values, n_exact=20000)
            if r:
                tests.append({'feature': name, 'party': g, **r})
    adjust(tests)
    grid = {s: {'n': int((P.moon_sign == s).sum()), **{g: round(float(P[P.moon_sign == s][g].mean()), 2) for g in PARTIES}} for s in SIGNS if (P.moon_sign == s).any()}
    return {'elections': P.to_dict('records'), 'grid': grid, 'tests': tests, 'n_tests': len(tests), 'nominal_hits': [t for t in tests if t['p'] < 0.05],
            'expected_by_chance': round(0.05 * len(tests), 1), 'surviving_holm': [t for t in tests if t['p_holm'] < 0.05], 'surviving_fdr': [t for t in tests if t['q_fdr'] < 0.05],
            'best': sorted(tests, key=lambda t: t['p'])[:5], 'signs_untested': [s for s in SIGNS if (P.moon_sign == s).sum() < 2]}


def moon_phase_by_party():
    """the moon's phase and size at local noon on election day against each party's first-preference change, 20 elections"""
    P = party_changes()
    off = {'Victoria': 'VIC', 'Federal (Victoria)': 'VIC', 'Queensland': 'QLD', 'New South Wales': 'NSW', 'Western Australia': 'WA', 'South Australia': 'SA'}
    ex = []
    for r in P.itertuples():
        d = dt.date.fromisoformat(r.date); st = off[r.place]
        t = ephem.Date(dt.datetime(d.year, d.month, d.day, 12) - dt.timedelta(hours=utc_offset(st, d)))
        m = ephem.Moon(); m.compute(t)
        ex.append({'moon_illumination': round(m.phase / 100, 3), 'moon_waxing': (t - ephem.previous_new_moon(t)) < 14.77,
                   'full_moon_within_3_days': min(t - ephem.previous_full_moon(t), ephem.next_full_moon(t) - t) <= 3, **moon_extra(t)})
    P = pd.concat([P, pd.DataFrame(ex)], axis=1)
    feats = {'Waxing moon': P.moon_waxing, 'Moon more than half full': P.moon_illumination > 0.5, 'Full moon within 3 days': P.full_moon_within_3_days,
             'New moon within 3 days': P.new_moon_within_3_days, 'Moon looking bigger than average (closer)': P.moon_size_vs_mean > 0, 'Supermoon within 3 days': P.supermoon_within_3_days}
    tests = []
    for name, x in feats.items():
        for g in PARTIES:
            r = perm_test(P[g].values, x.values.astype(bool), n_exact=20000)
            if r:
                tests.append({'feature': name, 'party': g, **r})
    adjust(tests)
    # size as a dial, not a switch: correlation of how big the moon looked with each party's change, permutation p
    rng = np.random.default_rng(29); dial = {}
    for g in PARTIES:
        y = P[g].values; x = P.moon_size_vs_mean.values; r0 = np.corrcoef(x, y)[0, 1]
        rs = np.array([np.corrcoef(rng.permutation(x), y)[0, 1] for _ in range(20000)]); dial[g] = {'r': round(float(r0), 3), 'p': round(float((np.abs(rs) >= abs(r0)).mean()), 3)}
    return {'elections': P.to_dict('records'), 'counts': {k: int(v.sum()) for k, v in feats.items()}, 'tests': tests, 'n_tests': len(tests),
            'nominal_hits': [t for t in tests if t['p'] < 0.05], 'expected_by_chance': round(0.05 * len(tests), 1),
            'surviving_holm': [t for t in tests if t['p_holm'] < 0.05], 'surviving_fdr': [t for t in tests if t['q_fdr'] < 0.05],
            'best': sorted(tests, key=lambda t: t['p'])[:5], 'size_dial': dial,
            'size_range_pct': [round(100 * float(P.moon_size_vs_mean.min()), 1), round(100 * float(P.moon_size_vs_mean.max()), 1)]}


def main():
    O = outcomes()
    rows = []
    for e, o in O.items():
        sk = sky(dt.date.fromisoformat(o['date']))
        rows.append({'election': e, **o, **sk})
    D = pd.DataFrame(rows)
    T = D[D.gov_primary_change.notna()].copy()
    feats = {
        'Full moon within 3 days': T.days_from_full_moon <= 3,
        'Moon more than half full': T.moon_illumination > 0.5,
        'Waxing moon': T.moon_waxing,
        'Moon looking bigger than average (closer)': T.moon_size_vs_mean > 0,
        'Supermoon within 3 days': T.supermoon_within_3_days,
        'Mercury retrograde': T.mercury_retrograde,
        'Venus retrograde': T.venus_retrograde,
        'Mars retrograde': T.mars_retrograde,
        'Eclipse within a fortnight': T.eclipse_within_14_days.map(bool),
        'Moon in a fire sign': T.moon_sign.map(ELEMENT) == 'fire',
        'Moon in an earth sign': T.moon_sign.map(ELEMENT) == 'earth',
        'Moon in an air sign': T.moon_sign.map(ELEMENT) == 'air',
        'Moon in a water sign': T.moon_sign.map(ELEMENT) == 'water',
        'Sun in Sagittarius': T.sun_sign == 'Sagittarius',
        'Mars in a fire sign': T.mars_sign.map(ELEMENT) == 'fire',
        'Jupiter in a fire or air sign': T.jupiter_sign.map(ELEMENT).isin(['fire', 'air']),
        'Saturn in a water sign': T.saturn_sign.map(ELEMENT) == 'water',
        'Friday the 13th in the campaign': T.friday_13th_in_campaign,
        'Daylight saving': T.daylight_saving,
        'Within 4 weeks of the Melbourne Cup': T.days_since_melbourne_cup.fillna(999) <= 28,
    }
    tests = []
    for name, x in feats.items():
        for yname, y in (('gov_primary_change', T.gov_primary_change), ('held_office', T.held_office.astype(float))):
            r = perm_test(y.values, x.values)
            if r:
                tests.append({'feature': name, 'outcome': yname, **r})
    # Holm correction across every test run
    ps = sorted(range(len(tests)), key=lambda i: tests[i]['p']); m = len(tests); running = 0
    for rank, i in enumerate(ps):
        adj = min(1.0, (m - rank) * tests[i]['p']); running = max(running, adj); tests[i]['p_holm'] = round(running, 3)
    res = {'about': __doc__.split('\n\n')[0], 'elections': D.to_dict('records'), 'tests': tests, 'n_tests': m,
           'nominal_hits': [t for t in tests if t['p'] < 0.05], 'expected_by_chance': round(0.05 * m, 1), 'surviving_correction': [t for t in tests if t['p_holm'] < 0.05]}
    res['moon_by_party'] = mb = moon_by_party()
    res['moon_phase_by_party'] = mp = moon_phase_by_party()
    old = os.path.join(ROOT, 'data/analysis/astrology.json')
    if os.path.exists(old):   # keep pieces added by other passes (the seat-level pseudo-replication demo)
        for k, v in json.load(open(old)).items():
            res.setdefault(k, v)
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/astrology.json'), 'w'), indent=1, default=str)
    print(pd.DataFrame(mb['elections']).to_string())
    print(f"moon by party: {mb['n_tests']} tests; nominal {len(mb['nominal_hits'])} (chance {mb['expected_by_chance']}); Holm {len(mb['surviving_holm'])}; FDR {len(mb['surviving_fdr'])}")
    for t in mb['best']:
        print('  ', t)
    print(f"moon phase and size by party: {mp['n_tests']} tests; counts {mp['counts']}; nominal {len(mp['nominal_hits'])} (chance {mp['expected_by_chance']}); Holm {len(mp['surviving_holm'])}; FDR {len(mp['surviving_fdr'])}; size dial {mp['size_dial']}; size range {mp['size_range_pct']}")
    for t in mp['best']:
        print('  ', t)
    print(D[['election', 'gov_primary_change', 'held_office', 'moon_sign', 'moon_illumination', 'mercury_retrograde', 'eclipse_within_14_days', 'friday_13th_in_campaign']].to_string())
    print(f'{m} tests; nominal p<0.05: {len(res["nominal_hits"])} (chance alone expects {res["expected_by_chance"]}); after Holm: {len(res["surviving_correction"])}')
    for t in sorted(tests, key=lambda t: t['p'])[:6]:
        print('  ', t)


if __name__ == '__main__':
    main()
