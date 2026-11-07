"""2021 Census indicators by electorate from the ABS Data API capture (raw/abs/c21_<geo>_vic.json, made in the browser:
for each GCP table the Victorian regions' cells, with persons totals for sex and age), into the same shape as
site/data/demog_vic2022.json so the site can treat every boundary set alike:

  {source, census, boundaries, indicators: [{id, group, label, kind}], state: {...}, districts: {contest_id: {name, ...}}}

Geographies: SED (ABS "SED 2021" = the Victorian districts as drawn in 2013, used at the 2014 and 2018 elections) ->
boundaries vic_la_2013, matched by name to the vic2018 contests; CED (federal divisions as at 2021, used in 2022) ->
boundaries fed_2021, matched by name to the fed2022 contests.

SA2: the same tables at SA2 level, apportioned in the browser onto the 2022 districts with raw/abs/sa2_to_vic_la_2022.json
(src/sa2_weights.py) -> raw/abs/c21_sa2_vic.json whose regions are already contest ids; merged with the Parliament
workbook file so the 2022/2026 seats keep the workbook's own figures for anything the ABS tables do not cover.

Usage: python3 -m src.load_abs_census SED site/data/demog_vic_la_2013.json.gz
       python3 -m src.load_abs_census CED site/data/demog_fed_2021.json.gz
       python3 -m src.load_abs_census SA2 site/data/demog_vic_la_2022.json.gz   (after src.load_demographics)
"""
import sys, re, json, gzip, os

SLUG = lambda s: re.sub(r'[^a-z]+', '-', s.lower()).strip('-')


def contests_for(boundaries):
    j = json.load(gzip.open('site/data/contests.json.gz'))
    rows = [dict(zip(j['cols'], r)) for r in j['rows']] if 'cols' in j else j
    eid = {'vic_la_2013': 'vic2018', 'fed_2021': 'fed2022'}[boundaries]
    return {r['contest_name'].lower(): r['contest_id'] for r in rows if r['election_id'] == eid and r['house'] != 'LC'}


def main(geo, out):
    cap = json.load(open(f'raw/abs/c21_{geo.lower()}_vic.json'))
    T = cap['tables']
    boundaries = {'SED': 'vic_la_2013', 'CED': 'fed_2021', 'SA2': 'vic_la_2022'}[geo]
    cmap = contests_for(boundaries) if geo != 'SA2' else None
    regions = {}
    for t in T.values():
        regions.update(t['regions'])
    # region code -> contest id (skip the non-geographic codes)
    rid = {}
    if geo == 'SA2':
        wb = json.load(gzip.open('site/data/demog_vic_la_2022.json.gz'))
        for cid in regions:
            d = wb['districts'].get(cid)
            if d:
                rid[cid] = (cid, d['name'], (d.get('region') or '').replace(' Metropolitan', ' Metropolitan') or None)
    for code, name in (regions.items() if geo != 'SA2' else []):
        base = re.sub(r'\s*\(.*\)$', '', name).strip()
        if re.search(r'no usual address|migratory|offshore', name, re.I):
            continue
        cid = cmap.get(base.lower())
        if not cid:
            print('unmatched region', code, name); continue
        rid[code] = (cid, base, (re.search(r'\((.*)\)$', name) or [None, None])[1])
    # cell lookup: table -> {region: {(dimcodes...): value}}
    cells = {}
    for g, t in T.items():
        m = {}
        for r in t['rows']:
            m.setdefault(r[0], {})[tuple(r[1:-1])] = r[-1]
        cells[g] = m
    ind = []          # indicator definitions
    vals = {}         # cid -> {id: value}
    state_num = {}    # id -> (numerator sum, denominator sum) for shares; medians handled separately

    def add(id_, group, label, kind):
        if not any(x['id'] == id_ for x in ind):
            ind.append({'id': id_, 'group': group, 'label': label, 'kind': kind})

    def share(id_, group, label, g, num_keys, den_key):
        add(id_, group, label, 'share')
        for code, (cid, name, region) in rid.items():
            m = cells[g].get(code, {})
            n = sum(m.get(k, 0) for k in num_keys); d = m.get(den_key)
            if d:
                vals.setdefault(cid, {})[id_] = n / d
                a, b = state_num.get(id_, (0, 0)); state_num[id_] = (a + n, b + d)

    def lab(g, dim, code):
        return T[g]['labels'][dim].get(code, code)

    # G02 medians
    MED = {'1': ('age_median', 'Age', 'Median age', 'years'), '2': ('income_personal_median', 'Income', 'Median weekly personal income', 'dollars'),
           '3': ('income_family_median', 'Income', 'Median weekly family income', 'dollars'), '4': ('income_household_median', 'Income', 'Median weekly household income', 'dollars'),
           '5': ('mortgage_median_monthly', 'Housing costs', 'Median monthly mortgage repayment', 'dollars'), '6': ('rent_median', 'Housing costs', 'Median weekly rent', 'dollars'),
           '7': ('persons_per_bedroom', 'Dwellings', 'Persons per bedroom', 'ratio'), '8': ('household_size', 'Dwellings', 'Average household size', 'ratio')}
    pop = {}
    for code, (cid, name, region) in rid.items():
        pop[cid] = cells['G04'].get(code, {}).get(('_T',), 0)
    for k, (id_, group, label, kind) in MED.items():
        add(id_, group, label, kind)
        for code, (cid, name, region) in rid.items():
            v = cells['G02'].get(code, {}).get((k,))
            if v is not None:
                vals.setdefault(cid, {})[id_] = v
    # G04 age bands (five-year codes)
    bands = {'age_0_17': (['0_4', '5_9', '10_14'], 'Under 15'), 'age_15_24': (['15_19', '20_24'], '15 to 24'), 'age_25_34': (['25_29', '30_34'], '25 to 34'), 'age_35_49': (['35_39', '40_44', '45_49'], '35 to 49'),
             'age_50_64': (['50_54', '55_59', '60_64'], '50 to 64'), 'age_65_plus': (['65_69', '70_74', '75_79', '80_84', '85_89', '90_94', '95_99', 'GE100'], '65 and over')}
    for id_, (codes, label) in bands.items():
        share(id_, 'Age', label, 'G04', [(c,) for c in codes], ('_T',))
    # G09 birthplace
    share('born_australia', 'Birthplace', 'Born in Australia', 'G09', [('11',)], ('_T',))
    share('born_overseas', 'Birthplace', 'Born overseas', 'G09', [(c,) for c in T['G09']['labels']['BPLP'] if c not in ('11', '_T', '_N')], ('_T',))
    for c, name in T['G09']['labels']['BPLP'].items():
        if c in ('11', '_T', '_N', '_O'):
            continue
        share('born_' + SLUG(name).replace('-', '_'), 'Birthplace: country', name, 'G09', [(c,)], ('_T',))
    # G08 ancestry (share of persons, total responses can exceed persons; use G04 total as the base)
    for c, name in T['G08']['labels']['ANCP'].items():
        if c.startswith('_'):
            continue
        id_ = 'ancestry_' + SLUG(name).replace('-', '_'); add(id_, 'Ancestry', name, 'share')
        for code, (cid, nm, region) in rid.items():
            n = cells['G08'].get(code, {}).get((c, '_T')); d = pop.get(cid)
            if n is not None and d:
                vals.setdefault(cid, {})[id_] = n / d; a, b = state_num.get(id_, (0, 0)); state_num[id_] = (a + n, b + d)
    share('parents_both_overseas', 'Ancestry', 'Both parents born overseas', 'G08', [(c, '1') for c in T['G08']['labels']['ANCP'] if c == '_T'] or [], ('_T', '_T'))
    # G13 language
    lanT = ('_T', '_T') if ('_T', '_T') in next(iter(cells['G13'].values()), {}) else None
    den13 = [k for k in next(iter(cells['G13'].values()), {}) if k[1] == '_T' and k[0] in ('_T',)]
    share('speaks_english_only', 'Language', 'Speaks only English at home', 'G13', [('1', '_T')], ('_T', '_T'))
    share('english_not_well', 'Language', 'Other language, speaks English not well or not at all', 'G13', [('_T', '3')], ('_T', '_T'))
    for c, name in T['G13']['labels']['LANP'].items():
        if c in ('1', '_T', '_N') or 'Total' in name:
            continue
        share('language_' + SLUG(name).replace('-', '_'), 'Language: spoken at home', name, 'G13', [(c, '_T')], ('_T', '_T'))
    # G14 religion
    for c, name in T['G14']['labels']['RELP'].items():
        if c in ('_T', '_N'):
            continue
        share('religion_' + SLUG(name).replace('-', '_'), 'Religion', name, 'G14', [(c,)], ('_T',))
    # G16 school
    share('year12', 'Education', 'Completed Year 12', 'G16', [('1',)], ('_T',))
    # G49 qualification
    # G49 lists only people who hold a qualification, so use persons aged 15+ (from G04) as the base, as the ABS does for attainment
    bands15 = ['15_19', '20_24', '25_29', '30_34', '35_39', '40_44', '45_49', '50_54', '55_59', '60_64', '65_69', '70_74', '75_79', '80_84', '85_89', '90_94', '95_99', 'GE100']
    for id_, label, keys in [('bachelor_or_higher', 'Bachelor degree or higher (of persons 15+)', [('1',), ('2',), ('3',)]), ('postgraduate', 'Postgraduate degree (of persons 15+)', [('1',)]), ('certificate', 'Certificate level (of persons 15+)', [('5',)]), ('diploma', 'Advanced diploma or diploma (of persons 15+)', [('4',)])]:
        add(id_, 'Education', label, 'share')
        for code, (cid, name, region) in rid.items():
            n = sum(cells['G49'].get(code, {}).get(k, 0) for k in keys); d = sum(cells['G04'].get(code, {}).get((b,), 0) for b in bands15)
            if d:
                vals.setdefault(cid, {})[id_] = n / d; a_, b_ = state_num.get(id_, (0, 0)); state_num[id_] = (a_ + n, b_ + d)
    # G17 personal income bands
    inc = T['G17']['labels']['INCP']
    hi = [(c,) for c, n in inc.items() if re.match(r'\$(2|3),', n) or 'or more' in n]
    lo = [(c,) for c, n in inc.items() if c in ('1', '2', '3', '4', '5')]
    share('income_personal_2000_plus', 'Income', 'Personal income $2,000+ a week', 'G17', hi, ('_T',))
    share('income_personal_under_500', 'Income', 'Personal income under $500 a week', 'G17', lo, ('_T',))
    # G33 household income
    hind = T['G33']['labels']['HIND']
    share('income_household_3000_plus', 'Income', 'Household income $3,000+ a week', 'G33', [(c, '_T') for c, n in hind.items() if re.match(r'\$(3|4|5),', n) or 'or more' in n], ('_T', '_T'))
    share('income_household_under_1000', 'Income', 'Household income under $1,000 a week', 'G33', [(c, '_T') for c in ('1', '2', '3', '4', '5', '6', '7', '8')], ('_T', '_T'))
    # G34 vehicles, G36 dwellings, G37 tenure
    share('no_motor_vehicle', 'Dwellings', 'Households with no motor vehicle', 'G34', [('0', 'D')], ('_T', 'D'))
    share('two_plus_vehicles', 'Dwellings', 'Households with two or more vehicles', 'G34', [('2', 'D'), ('3', 'D'), ('4', 'D')], ('_T', 'D'))
    share('separate_house', 'Dwellings', 'Separate houses', 'G36', [('11', 'D')], ('_T', 'D'))
    share('flat_apartment', 'Dwellings', 'Flats and apartments', 'G36', [('3', 'D')], ('_T', 'D'))
    share('townhouse', 'Dwellings', 'Townhouses and terraces', 'G36', [('2', 'D')], ('_T', 'D'))
    share('owned_outright', 'Tenure', 'Owned outright', 'G37', [('1', '_T')], ('_T', '_T'))
    share('owned_mortgage', 'Tenure', 'Owned with a mortgage', 'G37', [('2', '_T')], ('_T', '_T'))
    share('rented', 'Tenure', 'Rented', 'G37', [('R_T', '_T')], ('_T', '_T'))
    share('social_housing', 'Tenure', 'Social housing (public or community)', 'G37', [('4', '_T'), ('5', '_T')], ('_T', '_T'))
    # G46 labour force
    share('unemployment_rate', 'Work', 'Unemployment rate (of the labour force)', 'G46', [('8',)], ('9',))
    share('participation_rate', 'Work', 'Labour force participation', 'G46', [('9',)], ('_T',))
    share('part_time_share', 'Work', 'Part-time (of the employed)', 'G46', [('2',)], ('5',))
    # G60 occupation, G54 industry (of employed)
    for c, name in T['G60']['labels']['OCCP'].items():
        if c in ('_T', '_N'):
            continue
        share('occupation_' + SLUG(name).replace('-', '_'), 'Occupation', name, 'G60', [(c,)], ('_T',))
    for c, name in T['G54']['labels']['INDP'].items():
        if c in ('_T', '_N') or c.startswith('_'):
            continue
        share('industry_' + SLUG(name).replace('-', '_'), 'Industry', name, 'G54', [(c,)], ('_T',))
    # G62 travel to work
    mt = T['G62']['labels']['MTWP']
    pt = [(c,) for c, n in mt.items() if re.search(r'train|bus|tram|ferry', n, re.I) and not re.search(r'did not|worked at home', n, re.I)]
    share('travel_public_transport', 'Travel to work', 'Public transport (any)', 'G62', pt, ('_T',))
    share('travel_car_driver', 'Travel to work', 'Car, as driver', 'G62', [('6',)], ('_T',))
    wfh = [(c,) for c, n in mt.items() if re.search(r'worked at home', n, re.I)]
    share('worked_at_home', 'Travel to work', 'Worked at home', 'G62', wfh, ('_T',))
    share('travel_bicycle', 'Travel to work', 'Bicycle', 'G62', [('10',)], ('_T',))
    # G18, G23
    share('need_assistance', 'Health and community', 'Needs assistance with core activities', 'G18', [('1',)], ('_T',))
    share('volunteer', 'Health and community', 'Volunteers', 'G23', [('2',)], ('_T',))
    # population
    add('population', 'Population', 'Population', 'count')
    for cid, p in pop.items():
        vals.setdefault(cid, {})['population'] = p
    # state figures: shares from pooled numerators; medians as population-weighted means (approximate)
    state = {}
    for id_, (a, b) in state_num.items():
        if b:
            state[id_] = a / b
    tot = sum(pop.values()); state['population'] = tot
    for k, (id_, group, label, kind) in MED.items():
        s = sum(vals[c].get(id_, 0) * pop[c] for c in vals if id_ in vals[c]); w = sum(pop[c] for c in vals if id_ in vals[c])
        if w:
            state[id_] = round(s / w)
    # drop indicators that are tiny everywhere (keeps the axis list useful)
    keep = []
    for x in ind:
        mx = max((v.get(x['id'], 0) for v in vals.values()), default=0)
        if x['kind'] != 'share' or mx >= 0.01:
            keep.append(x)
    keepids = {x['id'] for x in keep}
    districts = {}
    for code, (cid, name, region) in rid.items():
        d = {k: v for k, v in vals.get(cid, {}).items() if k in keepids}
        districts[cid] = {'name': name, 'region': region, **d}
    if geo == 'SA2':
        # merge: ABS indicators first, then the workbook's own where the ABS set has no equivalent
        wb = json.load(gzip.open('site/data/demog_vic_la_2022.json.gz'))
        if wb.get('merged'):
            raise SystemExit('demog_vic_la_2022 is already merged: rerun src.load_demographics first')
        DUP = {'population_total_persons', 'population_male', 'population_female', 'age_median', 'income_and_expense_income', 'income_and_expense_mortage', 'income_and_expense_rent',
               'household_ownership_owned', 'household_ownership_mortgage', 'household_ownership_rented', 'country_of_birth_born_in_australia', 'language_speaks_only_english',
               'health_need_assistance', 'motor_vehicle_ownership_no_motor_vehicles', 'volunteering_for_organisation_or_group', 'dwelling_type_and_household_details_persons_per_bedroom',
               'dwelling_type_and_household_details_people_per_household'}
        extra = [x for x in wb['indicators'] if x['id'] not in DUP and x['id'] not in keepids and '_cat_' not in x['id']]
        for x in extra:
            x = dict(x); x['group'] = x['group'] + ' (Parliament of Victoria cards)' if x['kind'] != 'text' else x['group']; keep.append(x)
        exids = {x['id'] for x in extra}
        keepids |= exids | {i + '_share' for i in exids}
        for cid, d in districts.items():
            src = wb['districts'].get(cid, {})
            d.update({k: v for k, v in src.items() if k in exids or k.endswith('_share') and k[:-6] in exids})
            d['region'] = src.get('region') or d.get('region')
        state.update({k: v for k, v in wb['state'].items() if k in exids or k.endswith('_share') and k[:-6] in exids})
        # check the apportionment: ABS persons aggregated from SA2s against the workbook's district populations
        diffs = sorted(((abs(districts[c]['population'] - wb['districts'][c]['population_total_persons']) / wb['districts'][c]['population_total_persons'], c) for c in districts if c in wb['districts'] and districts[c].get('population')), reverse=True)
        print('population check vs Parliament cards: median abs diff %.1f%%, worst %s' % (100 * diffs[len(diffs) // 2][0], ', '.join(f'{c} {100 * d:.1f}%' for d, c in diffs[:5])))
    obj = {'source': ("ABS Census 2021 (General Community Profile tables via the ABS Data API) at SA2 level, apportioned onto the 2022 districts by election-day votes within each SA2; plus the Parliament of Victoria Library electorate data cards" if geo == 'SA2' else f"ABS Census 2021 (General Community Profile tables via the ABS Data API), {'State Electoral Divisions as at 2021, i.e. the Victorian districts drawn in 2013' if geo == 'SED' else 'Commonwealth Electoral Divisions as at 2021'}"),
           'merged': geo == 'SA2',
           'census': 2021, 'boundaries': boundaries, 'indicators': keep, 'state': {k: v for k, v in state.items() if k in keepids}, 'districts': districts,
           'note': 'State medians are population-weighted averages of the district medians, not the true state median. The 2021 Census was taken on 10 August 2021, during Melbourne\'s lockdown, so travel-to-work and worked-at-home figures describe that week, not normal commuting.'}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with gzip.open(out, 'wt') as fh:
        json.dump(obj, fh, separators=(',', ':'))
    print(f'{geo}: {len(districts)} districts, {len(keep)} indicators ->', out)


if __name__ == '__main__':
    if sys.argv[1] == 'SA2':
        raise SystemExit('the 2022-boundary file is now built from the SA1 DataPacks: python3 -m src.load_sa1_census && python3 -m src.build_demog && python3 -m src.model_issues')
    main(sys.argv[1], sys.argv[2])
