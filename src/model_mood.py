"""Modelled "democratic mood" for each Victorian district and booth catchment: how an area would be expected to
answer the McKinnon Index 2026 questions (trust in state politicians, satisfaction with democracy, "Australia is
more divided", "violence is sometimes justified", local safety...), given who lives there.

Data: the McKinnon Index 2026 dashboard (mckinnon.co/index/dashboard) serves its unit records: 4,273 respondents
nationally, with survey weights and the respondent's age band, education, household income band, birthplace
(Australia / elsewhere), language at home, remoteness and gender. It has no state, no electorate and no voting
question, so this is NOT a Victorian measurement and NOT a vote model: it is the national relationship between
demographics and attitudes, applied to each area's 2021 Census mix.

Method: for each outcome (a yes/no reading of a question, e.g. trust 6-10 on the 0-10 scale), a weighted
linear-probability regression on main effects of age band, education, household income band, born overseas,
other language at home and remoteness. Because the model is additive, an area's estimate needs only its census
margins: estimate = intercept + sum over dimensions of (area's share in each group x that group's coefficient).
Household income bands are the survey's 2026 dollars, deflated to 2021 by wage growth for the census cut-offs.
Remoteness is assigned per district (metropolitan regions = major city; regional seats under 6,000 km2 = inner
regional; the large rural seats = outer regional/remote). The national level is kept as the intercept: no
Victorian anchor is available from this source.

Adds indicators `mood_<id>` (shares, flagged modelled) to site/data/demog_vic_la_2022.json.gz and
site/data/demog_booth_vic2022.json.gz. Usage: python3 -m src.model_mood
"""
import os, json, gzip
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAGE_2021_TO_2026 = 1.18
WAGE_TO_2021 = {2025: 1.135, 2026: 1.18}   # Wage Price Index growth from September 2021 to each survey year (approx.)
VIC_CODE = 1   # McKinnon 2025 'state' filter: codes follow the ABS state order (0 NSW, 1 Vic, 2 Qld, 3 SA, 4 WA, 5 Tas, 6 NT, 7 ACT); sample sizes match that order
AGE = ['18_24', '25_34', '35_49', '50_64', '65_plus']            # survey codes 0..4
EDU = ['secondary', 'vocational', 'bachelor', 'postgrad']         # survey codes 0..3 (weighted shares and the trust gradient identify this order)
INC = [(0, 50000), (50000, 80000), (80000, 120000), (120000, 200000), (200000, None)]   # survey codes 0..4, annual household income, 2026 dollars
REM = ['major_city', 'inner_regional', 'outer_regional']          # survey codes 0..2
OUTER_SEATS_KM2 = 6000

# outcome id, label, question code, reading
OUTCOMES = [
    ('trust_state_politicians', 'Trusts state politicians (6–10 of 10)', 'epl1_2', lambda v: v <= 10 and v >= 6),
    ('trust_state_government', 'Trusts the state government (6–10 of 10)', 'epl6_2', lambda v: v <= 10 and v >= 6),
    ('trust_federal_politicians', 'Trusts federal politicians (6–10 of 10)', 'epl1_1', lambda v: v <= 10 and v >= 6),
    ('state_politicians_represent_me', 'Agrees the state’s politicians understand and represent people like me', 'epl2_4', lambda v: v in (1, 2)),
    ('government_does_right_thing', 'Agrees people in government can usually be trusted to do the right thing', 'epl2_5', lambda v: v in (1, 2)),
    ('state_government_effective', 'Rates the state government effective', 'epl5', lambda v: v in (1, 2)),
    ('direction_satisfied', 'Satisfied with the way Australia is heading', 'epl7', lambda v: v in (1, 2)),
    ('corruption_state_politics', 'Agrees corruption is a problem in state politics', 'eps2_2', lambda v: v in (1, 2)),
    ('trust_news_media', 'Trusts the news media (6–10 of 10)', 'epl1_6', lambda v: v <= 10 and v >= 6),
    ('elections_free_fair', 'Agrees our elections are free and fair', 'sdi3_2', lambda v: v in (1, 2)),
    ('have_a_say', 'Agrees the political system lets people like me have a say', 'sdi3_4', lambda v: v in (1, 2)),
    ('violence_justified', 'Agrees extreme measures such as violence are sometimes justified for a cause', 'sdi4_3', lambda v: v in (1, 2)),
    ('democracy_preferable', 'Agrees democracy is preferable to any other kind of government', 'sdi4_5', lambda v: v in (1, 2)),
    ('more_divided', 'Agrees Australia is more divided than 12 months ago', 'sdi4_6', lambda v: v in (1, 2)),
    ('hard_work_pays', 'Agrees anyone can get wealthier if they work hard', 'sdi4_7', lambda v: v in (1, 2)),
    ('local_safety_satisfied', 'Satisfied with safety in the local neighbourhood (6–10 of 10)', 'eps4_5', lambda v: v <= 10 and v >= 6),
    ('local_infrastructure_satisfied', 'Satisfied with local public infrastructure (6–10 of 10)', 'eps4_3', lambda v: v <= 10 and v >= 6),
    ('health_system_satisfied', 'Satisfied with the health system (6–10 of 10)', 'eps4_2', lambda v: v <= 10 and v >= 6),
    ('life_satisfaction_high', 'High life satisfaction (7–10 of 10)', 'sdlsat', lambda v: v <= 10 and v >= 7),
]
GROUP = 'Democratic mood (modelled from the McKinnon Index 2026)'


def design(age, edu, inc, born, lang, rem):
    """one-hot main effects with the first category of each dimension as the base"""
    cols = [np.ones(len(age))]
    for arr, k in ((age, 5), (edu, 4), (inc, 5), (rem, 3)):
        for c in range(1, k):
            cols.append((arr == c).astype(float))
    cols.append(born.astype(float)); cols.append(lang.astype(float))
    return np.column_stack(cols)


def fit(mck, year=2026):
    f = mck['filters']
    n = mck['n']
    W = np.array(mck['weight'], dtype=float)
    def arr(k):
        return np.array([-1 if v is None else v for v in f[k]], dtype=int)
    age, edu, inc, born, lang, rem = arr('age'), arr('education'), arr('household_income'), arr('born_australia'), arr('language'), arr('remoteness')
    ok = (age >= 0) & (edu >= 0) & (inc >= 0) & (born >= 0) & (lang >= 0) & (rem >= 0)
    X = design(age, edu, inc, born, lang, rem)
    models = {}
    reg = {r['codes'].get('2026'): r['codes'] for r in (mck.get('registry') or {}).get('questions', [])}
    vic = np.array([v == VIC_CODE for v in f['state']]) if 'state' in f else None
    for oid, label, q, reading in OUTCOMES:
        code = reg.get(q, {}).get(str(year), q) if reg else q
        a = mck['answers'].get(code) if code else None
        if a is None:
            continue
        labs = mck['labels'].get(code, {})
        dk = {int(k) for k, t in labs.items() if 'know' in str(t).lower() or 'refused' in str(t).lower()}
        y = np.array([1.0 if (v is not None and reading(v)) else 0.0 for v in a])
        valid = ok & np.array([v is not None and v <= 10 and v not in dk for v in a])   # drop don't-know / not stated
        sw = np.sqrt(W[valid])
        beta, *_ = np.linalg.lstsq(X[valid] * sw[:, None], y[valid] * sw, rcond=None)
        level = float(np.average(y[valid], weights=W[valid]))
        mod = {'label': label, 'q': code, 'beta': beta.tolist(), 'level': level, 'national': level, 'n': int(valid.sum())}
        if vic is not None and (valid & vic).sum() > 300:
            mod['level'] = float(np.average(y[valid & vic], weights=W[valid & vic])); mod['n_vic'] = int((valid & vic).sum())   # anchor on Victoria
        models[oid] = mod
    return models


def margins(rec, remoteness, wage=WAGE_2021_TO_2026):
    """an area's shares in each survey group, in the design's column order (excluding the intercept)"""
    adults = sum(rec.get('mi_age_' + a, 0) for a in AGE)
    p15 = rec.get('mi_persons_15_plus', 0)
    hh = {k[7:]: v for k, v in rec.items() if k.startswith('mi_hhi_')}
    if not adults or not p15 or not hh:
        return None
    cols = []
    cols += [rec.get('mi_age_' + a, 0) / adults for a in AGE[1:]]
    post, bach, voc = rec.get('mi_edu_postgrad', 0) / p15, rec.get('mi_edu_bachelor', 0) / p15, rec.get('mi_edu_vocational', 0) / p15
    cols += [voc, bach, post]                                                  # EDU[1:] = vocational, bachelor, postgrad
    # household income: census weekly bands (2021 dollars) against the survey's annual cut-offs deflated to 2021
    bands = [('negative_nil_income', 0, 0), ('hi_1_149', 1, 150), ('hi_150_299', 150, 300), ('hi_300_399', 300, 400), ('hi_400_499', 400, 500), ('hi_500_649', 500, 650), ('hi_650_799', 650, 800),
             ('hi_800_999', 800, 1000), ('hi_1000_1249', 1000, 1250), ('hi_1250_1499', 1250, 1500), ('hi_1500_1749', 1500, 1750), ('hi_1750_1999', 1750, 2000), ('hi_2000_2499', 2000, 2500),
             ('hi_2500_2999', 2500, 3000), ('hi_3000_3499', 3000, 3500), ('hi_3500_3999', 3500, 4000), ('hi_4000_more', 4000, 6000)]
    cuts = [c / 52 / wage for _, c in INC[:-1]]
    tot = sum(hh.get(b, 0) for b, _, _ in bands)
    def frac_below(lo, hi, cut):
        if hi <= cut: return 1.0
        if lo >= cut: return 0.0
        return (cut - lo) / (hi - lo)
    cum = []
    for cut in cuts:
        cum.append(sum(hh.get(b, 0) * frac_below(lo, hi, cut) for b, lo, hi in bands) / tot)
    shares = [cum[0], cum[1] - cum[0], cum[2] - cum[1], cum[3] - cum[2], 1 - cum[3]]
    cols += shares[1:]
    cols += [1.0 if remoteness == 'inner_regional' else 0.0, 1.0 if remoteness == 'outer_regional' else 0.0]
    cols += [rec.get('born_overseas', 0), rec.get('other_language_home', 0)]
    return np.array(cols)


def predict(models, m, m_state):
    """the national level, shifted by how the area's mix differs from Victoria's: the survey's own composition (an online
    panel, heavier on graduates than the population) then cancels out of the level"""
    return {oid: float(np.clip(mod['level'] + np.dot(np.array(mod['beta'][1:]), m - m_state), 0, 1)) for oid, mod in models.items()}


def remoteness_of(d):
    region = d.get('region') or ''
    if 'Metropolitan' in region:
        return 'major_city'
    return 'outer_regional' if (d.get('electorate_size_kilometres_squared') or 0) >= OUTER_SEATS_KM2 else 'inner_regional'


def gz_write(path, obj):
    with open(path, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as fh:
        fh.write(json.dumps(obj, separators=(',', ':')).encode())


def main():
    mck = json.load(open(os.path.join(ROOT, 'raw/mood/mckinnon_2026.json')))
    models = fit(mck, 2026)
    c21 = json.load(open(os.path.join(ROOT, 'raw/abs/sa1_census_2021.json')))
    note = ('Modelled from the McKinnon Index 2026 (national survey, n≈4,300): the relationship between attitudes and age, education, household income, birthplace, language and remoteness, '
            'applied to the area’s 2021 Census mix. The level is the national figure; it is not a Victorian poll and not a measure of how anyone votes.')
    inds = [{'id': 'mood_' + oid, 'group': GROUP, 'label': mod['label'], 'kind': 'share', 'modelled': True, 'from': '2026-01-01', 'note': note} for oid, mod in models.items()]
    # districts
    path = os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz'); D = json.load(gzip.open(path))
    D['indicators'] = [x for x in D['indicators'] if not x['id'].startswith('mood_')] + inds
    for rec in list(D['districts'].values()) + [D['state']]:
        for k in [k for k in rec if k.startswith('mood_')]:
            del rec[k]
    rem_of = {cid: remoteness_of(d) for cid, d in D['districts'].items()}
    # Victoria's own margins (remoteness: the population-weighted mix of the seat classes)
    pop = {cid: c21['districts'][cid].get('population', 0) for cid in D['districts'] if cid in c21['districts']}
    m_state = margins(c21['state'], 'major_city')
    for i, cls in ((-4, 'inner_regional'), (-3, 'outer_regional')):
        m_state[i] = sum(p for cid, p in pop.items() if rem_of[cid] == cls) / sum(pop.values())
    for cid, d in D['districts'].items():
        m = margins(c21['districts'].get(cid, {}), rem_of[cid])
        if m is None:
            continue
        for oid, v in predict(models, m, m_state).items():
            d['mood_' + oid] = round(v, 4)
    for oid, mod in models.items():
        D['state']['mood_' + oid] = round(mod['level'], 4)
    D['mood_model'] = {'source': mck['source'], 'retrieved': mck['retrieved'], 'n': mck['n'], 'wage_deflator': WAGE_2021_TO_2026, 'outcomes': {oid: {'q': mod['q'], 'n': mod['n'], 'national': round(mod['level'], 4)} for oid, mod in models.items()}}
    gz_write(path, D)
    # booths
    bpath = os.path.join(ROOT, 'site/data/demog_booth_vic2022.json.gz'); B = json.load(gzip.open(bpath))
    keep = [i for i, c in enumerate(B['cols']) if not c.startswith('mood_')]
    B['cols'] = [B['cols'][i] for i in keep]; B['indicators'] = [x for x in B['indicators'] if not x['id'].startswith('mood_')] + inds
    for rec in B['booths'].values():
        rec['v'] = [rec['v'][i] for i in keep]
    B['cols'] += [x['id'] for x in inds]
    for vid, rec in B['booths'].items():
        src = c21['booths'].get(vid, {})
        # the catchment's district: the booth id starts with the contest id
        cid = next((c for c in D['districts'] if rec['booth_id'].startswith(c + '-')), None)
        m = margins(src, rem_of.get(cid, 'major_city')) if src else None
        p = predict(models, m, m_state) if m is not None else {}
        rec['v'] += [round(p[oid], 4) if oid in p else None for oid in models]
    for oid, mod in models.items():
        B['state']['mood_' + oid] = round(mod['level'], 4)
    B['mood_model'] = D['mood_model']
    gz_write(bpath, B)
    plain = os.path.join(ROOT, 'site/data_plain')
    if os.path.isdir(plain):
        json.dump(D, open(os.path.join(plain, 'demog_vic_la_2022.json'), 'w'), separators=(',', ':'))
        json.dump(B, open(os.path.join(plain, 'demog_booth_vic2022.json'), 'w'), separators=(',', ':'))
    for oid, mod in models.items():
        vals = [d['mood_' + oid] for d in D['districts'].values() if 'mood_' + oid in d]
        print(f'{oid:34s} national {100 * mod["level"]:5.1f}%  seats {100 * min(vals):5.1f}..{100 * max(vals):5.1f}  n={mod["n"]}')
    print(len(models), 'mood indicators ->', path, 'and', bpath)


    main_2025(c21)


def main_2025(c21):
    """the McKinnon Index 2025 (first wave, n=4,416, with the respondent's state): the same model, levelled on its ~1,000
    Victorian respondents, for the 2025 contests only: the federal election (2024 divisions) and the 2025 by-elections
    (2022 districts). Indicator ids mood25_*, valid for elections held in 2025."""
    path25 = os.path.join(ROOT, 'raw/mood/mckinnon_2025.json')
    if not os.path.exists(path25):
        return
    mck = json.load(open(path25))
    models = fit(mck, 2025)
    wage = WAGE_TO_2021[2025]
    note = ('Modelled from the McKinnon Index 2025 (national survey, n≈4,400, about 1,000 of them Victorian): the relationship between attitudes and age, education, household income, '
            'birthplace, language and remoteness, applied to the area’s 2021 Census mix and levelled on the Victorian respondents. Shown for 2025 contests only; not a measure of how anyone votes.')
    inds = [{'id': 'mood25_' + oid, 'group': 'Democratic mood (modelled from the McKinnon Index 2025)', 'label': mod['label'], 'kind': 'share', 'modelled': True,
             'from': '2025-01-01', 'to': '2025-12-31', 'note': note} for oid, mod in models.items()]
    D = json.load(gzip.open(os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')))
    rem_of = {cid: remoteness_of(d) for cid, d in D['districts'].items()}
    pop = {cid: c21['districts'][cid].get('population', 0) for cid in D['districts'] if cid in c21['districts']}
    m_state = margins(c21['state'], 'major_city', wage)
    for i, cls in ((-4, 'inner_regional'), (-3, 'outer_regional')):
        m_state[i] = sum(p for cid, p in pop.items() if rem_of[cid] == cls) / sum(pop.values())
    def apply(fname, units, rem):
        path = os.path.join(ROOT, 'site/data', fname); X = json.load(gzip.open(path))
        X['indicators'] = [x for x in X['indicators'] if not x['id'].startswith('mood25_')] + inds
        for rec in list(X['districts'].values()) + [X['state']]:
            for k in [k for k in rec if k.startswith('mood25_')]:
                del rec[k]
        for cid, d in X['districts'].items():
            m = margins(units.get(cid, {}), rem(cid, d), wage)
            if m is None:
                continue
            for oid, v in predict(models, m, m_state).items():
                d['mood25_' + oid] = round(v, 4)
        for oid, mod in models.items():
            X['state']['mood25_' + oid] = round(mod['level'], 4)
        X['mood25_model'] = {'source': mck['source'], 'retrieved': mck['retrieved'], 'n': mck['n'], 'wage_deflator': wage, 'victoria_code': VIC_CODE,
                             'outcomes': {oid: {'q': mod['q'], 'n': mod['n'], 'n_vic': mod.get('n_vic'), 'victoria': round(mod['level'], 4), 'national': round(mod['national'], 4)} for oid, mod in models.items()}}
        gz_write(path, X)
        plain = os.path.join(ROOT, 'site/data_plain')
        if os.path.isdir(plain):
            json.dump(X, open(os.path.join(plain, fname.replace('.gz', '')), 'w'), separators=(',', ':'))
        return X
    apply('demog_vic_la_2022.json.gz', c21['districts'], lambda cid, d: rem_of[cid])
    # federal divisions: metropolitan if most of the division's people live in metropolitan districts, outer regional if very large
    F = None
    if os.path.exists(os.path.join(ROOT, 'site/data/demog_fed_2024.json.gz')):
        F = apply('demog_fed_2024.json.gz', c21.get('fed_2024', {}), lambda cid, d: FED_REMOTENESS.get(d['name'].title().replace('Mce', 'McE'), 'major_city'))
    for oid, mod in models.items():
        vals = [d['mood25_' + oid] for d in (F or D)['districts'].values() if 'mood25_' + oid in d]
        print(f'2025 {oid:34s} Victoria {100 * mod["level"]:5.1f}% (national {100 * mod["national"]:5.1f}%, n_vic={mod.get("n_vic")})  divisions {100 * min(vals):5.1f}..{100 * max(vals):5.1f}')


# Victorian federal divisions (2024 boundaries) outside Greater Melbourne: inner regional, or outer regional for the big rural ones
FED_REMOTENESS = {'Ballarat': 'inner_regional', 'Bendigo': 'inner_regional', 'Corangamite': 'inner_regional', 'Corio': 'inner_regional', 'Flinders': 'inner_regional',
                  'McEwen': 'inner_regional', 'Monash': 'inner_regional', 'Indi': 'outer_regional', 'Mallee': 'outer_regional', 'Nicholls': 'outer_regional',
                  'Wannon': 'outer_regional', 'Gippsland': 'outer_regional'}


if __name__ == '__main__':
    main()
