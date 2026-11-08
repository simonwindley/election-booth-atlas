"""2006 Census indicators from the TableBuilder Collection District (CD) tables, aggregated onto electoral areas with
the CD weights from src.cd_weights.

The ABS no longer distributes 2006 small-area DataPacks; the tables come from TableBuilder (Victoria, all 9,311 CDs in
the rows, one variable in the columns, place of usual residence for persons and of enumeration for dwellings), saved
in raw/abs/tablebuilder/2006/ and flattened into cd2006_tables.json on the Mac. Every indicator is built from counts
summed over the weighted CDs and divided afterwards; the medians (age, weekly personal income) are interpolated from
the aggregated bands, so unlike the SA1 series they are true medians of the area. TableBuilder randomly adjusts small
cells, which washes out at district level but leaves a little noise in small booth catchments.

Indicators keep the ids of the 2011-2021 SA1 series (src.load_sa1_census) where the definition matches, so the
history blocks and change indicators line up; a few are new (birthplace regions, internet at home).

Inputs  raw/abs/tablebuilder/2006/cd2006_tables.json, raw/abs/cd_weights_2006.json, site/data/booths.json.gz
Outputs raw/abs/sa1_census_2006.json       2022 districts + booth venues, in the shape of the SA1 series (for history)
        raw/abs/cd_census_2006.json        the same plus the 2001 districts (d01) and the 2003-2010 federal divisions (f03)
Usage   python3 -m src.load_cd_census
"""
import os, json, gzip
from collections import defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AGE_EDGES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 110]
INC_EDGES = [(None, 0), (0, 0), (1, 149), (150, 249), (250, 399), (400, 599), (600, 799), (800, 999), (1000, 1299), (1300, 1599), (1600, 1999), (2000, 3000)]


def atoms_for(T, cd):
    """the counts every indicator is built from, for one CD"""
    g = lambda k: T[k].get(cd)
    a = {}
    age = g('age')
    if age is None:
        return None
    for i in range(21):
        a[f'age{i}'] = age[i]
    a['pop'] = age[21]
    a['p15plus'] = sum(age[3:21])
    a['p20plus'] = sum(age[4:21])
    if (h := g('hscp')): a['y12'] = h[0]; a['hs_tot'] = h[8] - h[7]
    if (q := g('qallp')): a['q_pg'], a['q_gd'], a['q_bach'], a['q_adv'], a['q_cert'] = q[2], q[3], q[4], q[5], q[6]
    if (o := g('occ')):
        for i, k in enumerate(['managers', 'professionals', 'technicians_and_trades_workers', 'community_and_personal_service_workers', 'clerical_and_administrative_workers', 'sales_workers', 'machinery_operators_and_drivers', 'labourers']):
            a['occ_' + k] = o[2 + i]
        a['occ_tot'] = o[11] - o[10]
    if (x := g('indig')): a['indig'] = x[1] + x[2] + x[3]; a['indig_tot'] = x[5]
    if (b := g('bplp')):
        C = {c: i for i, c in enumerate(META['bplp']['categories'])}
        s = lambda *names: sum(b[C[n]] for n in names)
        a['b_aus'] = s('Australia (includes External Territories)'); a['b_tot'] = b[C['Total']]
        a['b_overseas'] = a['b_tot'] - a['b_aus'] - s('Not stated', 'Supplementary codes')
        a['b_nz'] = s('New Zealand'); a['b_uk'] = s('United Kingdom', 'Ireland')
        a['b_seur'] = s('Southern and Eastern Europe, nfd', 'Southern Europe', 'South Eastern Europe', 'Eastern Europe')
        a['b_nafme'] = s('North Africa and the Middle East, nfd', 'North Africa', 'Middle East')
        a['b_sea'] = s('South-East Asia, nfd', 'Mainland South-East Asia', 'Maritime South-East Asia')
        a['b_nea'] = s('North-East Asia, nfd', 'Chinese Asia (includes Mongolia)', 'Japan and the Koreas')
        a['b_sasia'] = s('Southern and Central Asia, nfd', 'Southern Asia', 'Central Asia')
        a['b_africa'] = s('Sub-Saharan Africa, nfd', 'Central and West Africa', 'Southern and East Africa')
    if (e := g('engp')): a['eng_nw'] = e[2] + e[3]; a['eng_tot'] = e[7]
    if (r := g('relp')):
        for i, k in enumerate(['buddhism', 'christianity_total', 'hinduism', 'islam', 'judaism', 'other_religions_total', 'no_religion_so_described']):
            a['rel_' + k] = r[2 + i]
        a['rel_tot'] = r[9]
    if (l := g('lanp')):
        C = {c: i for i, c in enumerate(META['lanp']['categories'])}
        s = lambda *names: sum(l[C[n]] for n in names)
        a['lan_eng'] = s('English'); a['lan_tot'] = l[C['Total']]
        a['lan_other'] = a['lan_tot'] - a['lan_eng'] - s('Not stated', 'Supplementary codes')
        a['lan_greek'] = s('Greek'); a['lan_italian'] = s('Italian'); a['lan_chinese'] = s('Chinese')
        a['lan_semitic'] = s('Middle Eastern Semitic Languages'); a['lan_indoaryan'] = s('Indo-Aryan'); a['lan_monkhmer'] = s('Mon-Khmer')
    if (t := g('tend')):
        a['t_own'] = t[0]; a['t_mort'] = t[1] + t[2]; a['t_rent'] = t[3]; a['t_tot'] = t[9] - t[8]
    if (l := g('lldd')): a['social'] = l[1] + l[7]
    if (s_ := g('strd')):
        a['s_house'] = s_[0]; a['s_semi'] = s_[1] + s_[2]; a['s_flat'] = s_[3] + s_[4] + s_[5] + s_[6]; a['s_tot'] = s_[12] - s_[11]
    if (n := g('nedd')): a['net_none'] = n[0]; a['net_bb'] = n[1]; a['net_tot'] = n[6] - n[5]
    if (f := g('lfsp')):
        a['emp_ft'], a['emp_pt'], a['emp_away'] = f[0], f[1], f[2]; a['unemp'] = f[3] + f[4]; a['lf_base'] = f[8] - f[7]
    if (i := g('incp')):
        for j in range(12):
            a[f'inc{j}'] = i[j]
    return a


def median(counts, edges):
    tot = sum(counts)
    if tot <= 0:
        return None
    half, run = tot / 2, 0.0
    for c, (lo, hi) in zip(counts, edges):
        if run + c >= half:
            if lo is None:
                return float(hi)
            frac = (half - run) / c if c else 0
            return lo + frac * (hi - lo)
        run += c
    return float(edges[-1][1])


def indicators(A):
    """indicator values for one aggregated unit (A = summed atoms)"""
    g = lambda k: A.get(k, 0.0)
    out = {}
    def share(id_, num, den):
        if den > 0:
            out[id_] = round(num / den, 5)
    pop = g('pop')
    out['population'] = int(round(pop))
    age = [g(f'age{i}') for i in range(21)]
    m = median(age, list(zip(AGE_EDGES[:-1], AGE_EDGES[1:])))
    if m is not None: out['age_median'] = round(m, 1)
    share('age_0_17', sum(age[0:3]) + 0.6 * age[3], pop)
    share('age_15_24', age[3] + age[4], pop)
    share('age_25_34', age[5] + age[6], pop)
    share('age_35_49', age[7] + age[8] + age[9], pop)
    share('age_50_64', age[10] + age[11] + age[12], pop)
    share('age_65_plus', sum(age[13:21]), pop)
    adults = 0.4 * age[3] + sum(age[4:21])
    share('adults_18_34', 0.4 * age[3] + age[4] + age[5] + age[6], adults)
    share('adults_35_54', age[7] + age[8] + age[9] + age[10], adults)
    share('adults_55_plus', sum(age[11:21]), adults)
    inc = [g(f'inc{j}') for j in range(12)]
    m = median(inc, INC_EDGES)
    if m is not None and sum(inc) > 0: out['income_personal_median'] = round(m, 0)
    share('born_australia', g('b_aus'), g('b_tot'))
    share('born_overseas', g('b_overseas'), g('b_tot'))
    for k, lab in (('b_uk', 'born_uk_ireland'), ('b_nz', 'born_new_zealand'), ('b_seur', 'born_southern_eastern_europe'), ('b_nafme', 'born_north_africa_middle_east'),
                   ('b_sea', 'born_south_east_asia'), ('b_nea', 'born_north_east_asia'), ('b_sasia', 'born_southern_central_asia'), ('b_africa', 'born_sub_saharan_africa')):
        share(lab, g(k), g('b_tot'))
    share('speaks_english_only', g('lan_eng'), g('lan_tot'))
    share('other_language_home', g('lan_other'), g('lan_tot'))
    share('english_not_well', g('eng_nw'), g('eng_tot'))
    for k, lab in (('lan_greek', 'language_greek'), ('lan_italian', 'language_italian'), ('lan_chinese', 'language_chinese_all'), ('lan_semitic', 'language_middle_eastern_semitic'),
                   ('lan_indoaryan', 'language_indo_aryan'), ('lan_monkhmer', 'language_mon_khmer')):
        share(lab, g(k), g('lan_tot'))
    for k in ['buddhism', 'christianity_total', 'hinduism', 'islam', 'judaism', 'other_religions_total', 'no_religion_so_described']:
        share('religion_' + k, g('rel_' + k), g('rel_tot'))
    share('year12', g('y12'), g('hs_tot'))
    share('bachelor_or_higher', g('q_pg') + g('q_gd') + g('q_bach'), g('p15plus'))
    share('postgraduate', g('q_pg'), g('p15plus'))
    share('diploma', g('q_adv'), g('p15plus'))
    share('certificate', g('q_cert'), g('p15plus'))
    share('owned_outright', g('t_own'), g('t_tot'))
    share('owned_mortgage', g('t_mort'), g('t_tot'))
    share('rented', g('t_rent'), g('t_tot'))
    share('social_housing', g('social'), g('t_tot'))
    share('separate_house', g('s_house'), g('s_tot'))
    share('townhouse', g('s_semi'), g('s_tot'))
    share('flat_apartment', g('s_flat'), g('s_tot'))
    share('internet_none', g('net_none'), g('net_tot'))
    share('internet_broadband', g('net_bb'), g('net_tot'))
    lf = g('emp_ft') + g('emp_pt') + g('emp_away') + g('unemp')
    share('unemployment_rate', g('unemp'), lf)
    share('participation_rate', lf, g('lf_base'))
    share('part_time_share', g('emp_pt'), g('emp_ft') + g('emp_pt'))
    for k in ['managers', 'professionals', 'technicians_and_trades_workers', 'community_and_personal_service_workers', 'clerical_and_administrative_workers', 'sales_workers', 'machinery_operators_and_drivers', 'labourers']:
        share('occupation_' + k, g('occ_' + k), g('occ_tot'))
    share('indigenous', g('indig'), g('indig_tot'))
    return out


IND_META = [
    ('population', 'Population', 'Population', 'count'), ('age_median', 'Age', 'Median age', 'years'), ('age_0_17', 'Age', 'Under 18', 'share'), ('age_15_24', 'Age', '15 to 24', 'share'),
    ('age_25_34', 'Age', '25 to 34', 'share'), ('age_35_49', 'Age', '35 to 49', 'share'), ('age_50_64', 'Age', '50 to 64', 'share'), ('age_65_plus', 'Age', '65 and over', 'share'),
    ('adults_18_34', 'Age', 'Adults aged 18 to 34 (of adults)', 'share'), ('adults_35_54', 'Age', 'Adults aged 35 to 54 (of adults)', 'share'), ('adults_55_plus', 'Age', 'Adults aged 55 and over (of adults)', 'share'),
    ('income_personal_median', 'Income', 'Median weekly personal income (2006 dollars)', 'dollars'),
    ('born_australia', 'Birthplace', 'Born in Australia', 'share'), ('born_overseas', 'Birthplace', 'Born overseas', 'share'), ('born_uk_ireland', 'Birthplace', 'Born in the UK or Ireland', 'share'),
    ('born_new_zealand', 'Birthplace', 'Born in New Zealand', 'share'), ('born_southern_eastern_europe', 'Birthplace', 'Born in southern or eastern Europe', 'share'),
    ('born_north_africa_middle_east', 'Birthplace', 'Born in North Africa or the Middle East', 'share'), ('born_south_east_asia', 'Birthplace', 'Born in South-East Asia', 'share'),
    ('born_north_east_asia', 'Birthplace', 'Born in North-East Asia', 'share'), ('born_southern_central_asia', 'Birthplace', 'Born in southern or central Asia', 'share'), ('born_sub_saharan_africa', 'Birthplace', 'Born in sub-Saharan Africa', 'share'),
    ('speaks_english_only', 'Language', 'Speaks only English at home', 'share'), ('other_language_home', 'Language', 'Speaks a language other than English at home', 'share'),
    ('english_not_well', 'Language', 'Other language, speaks English not well or not at all', 'share'), ('language_greek', 'Language', 'Greek', 'share'), ('language_italian', 'Language', 'Italian', 'share'),
    ('language_chinese_all', 'Language', 'Chinese languages', 'share'), ('language_middle_eastern_semitic', 'Language', 'Arabic and other Middle Eastern Semitic languages', 'share'),
    ('language_indo_aryan', 'Language', 'Indo-Aryan languages (Hindi, Punjabi, Urdu and others)', 'share'), ('language_mon_khmer', 'Language', 'Vietnamese and Khmer (Mon-Khmer)', 'share'),
    ('religion_buddhism', 'Religion', 'Buddhism', 'share'), ('religion_christianity_total', 'Religion', 'Christianity Total', 'share'), ('religion_hinduism', 'Religion', 'Hinduism', 'share'),
    ('religion_islam', 'Religion', 'Islam', 'share'), ('religion_judaism', 'Religion', 'Judaism', 'share'), ('religion_other_religions_total', 'Religion', 'Other Religions Total', 'share'),
    ('religion_no_religion_so_described', 'Religion', 'No Religion, so described', 'share'),
    ('year12', 'Education', 'Completed Year 12 (of persons 15+)', 'share'), ('bachelor_or_higher', 'Education', 'Bachelor degree or higher (of persons 15+)', 'share'),
    ('postgraduate', 'Education', 'Postgraduate degree (of persons 15+)', 'share'), ('diploma', 'Education', 'Advanced diploma or diploma (of persons 15+)', 'share'), ('certificate', 'Education', 'Certificate level (of persons 15+)', 'share'),
    ('owned_outright', 'Tenure', 'Owned outright', 'share'), ('owned_mortgage', 'Tenure', 'Owned with a mortgage', 'share'), ('rented', 'Tenure', 'Rented', 'share'), ('social_housing', 'Tenure', 'Social housing (public or community)', 'share'),
    ('separate_house', 'Dwellings', 'Separate houses', 'share'), ('townhouse', 'Dwellings', 'Townhouses and terraces', 'share'), ('flat_apartment', 'Dwellings', 'Flats and apartments', 'share'),
    ('internet_none', 'Dwellings', 'No internet connection at home', 'share'), ('internet_broadband', 'Dwellings', 'Broadband internet at home', 'share'),
    ('unemployment_rate', 'Work', 'Unemployment rate (of the labour force)', 'share'), ('participation_rate', 'Work', 'Labour force participation', 'share'), ('part_time_share', 'Work', 'Part-time (of the employed)', 'share'),
    ('occupation_managers', 'Occupation', 'Managers', 'share'), ('occupation_professionals', 'Occupation', 'Professionals', 'share'), ('occupation_technicians_and_trades_workers', 'Occupation', 'Technicians and Trades Workers', 'share'),
    ('occupation_community_and_personal_service_workers', 'Occupation', 'Community and Personal Service Workers', 'share'), ('occupation_clerical_and_administrative_workers', 'Occupation', 'Clerical and Administrative Workers', 'share'),
    ('occupation_sales_workers', 'Occupation', 'Sales Workers', 'share'), ('occupation_machinery_operators_and_drivers', 'Occupation', 'Machinery Operators and Drivers', 'share'), ('occupation_labourers', 'Occupation', 'Labourers', 'share'),
    ('indigenous', 'Population', 'Aboriginal and/or Torres Strait Islander', 'share')]

META = {}


def main():
    global META
    src = json.load(open(os.path.join(ROOT, 'raw/abs/tablebuilder/2006/cd2006_tables.json')))
    META, T = src['meta'], src['tables']
    W = json.load(open(os.path.join(ROOT, 'raw/abs/cd_weights_2006.json')))['cd']
    atoms = {cd: a for cd in T['age'] if (a := atoms_for(T, cd))}
    keys = sorted({k for a in atoms.values() for k in a})
    print(f'{len(atoms)} CDs with tables, {len(keys)} atoms, {sum(1 for cd in atoms if cd in W)} with weights')
    state = indicators({k: sum(a.get(k, 0) for a in atoms.values()) for k in keys})
    units = {}
    for tgt in ('d22', 'b22', 'd01', 'f03'):
        acc = defaultdict(lambda: defaultdict(float))
        for cd, a in atoms.items():
            for tid, w in W.get(cd, {}).get(tgt, {}).items():
                u = acc[tid]
                for k, v in a.items():
                    u[k] += w * v
        units[tgt] = {tid: indicators(A) for tid, A in acc.items()}
        print(f'  {tgt}: {len(units[tgt])} units')
    booths = json.load(gzip.open(os.path.join(ROOT, 'site/data/booths.json.gz')))
    venue_of = {r[2]: r[5] for r in booths['rows'] if r[0] in ('vic2022', 'vic2023n')}
    by_venue = {venue_of[b]: {'booth_id': b, **rec} for b, rec in units['b22'].items() if venue_of.get(b)}
    ind = [{'id': i, 'group': g, 'label': l, 'kind': k} for i, g, l, k in IND_META]
    source = 'ABS Census 2006 (TableBuilder, Victorian Collection Districts by place of usual residence; dwellings by place of enumeration), aggregated by the share of each CD inside each area'
    base = {'census': 2006, 'source': source, 'indicators': ind, 'state': state}
    json.dump({**base, 'boundaries': 'vic_la_2022', 'districts': units['d22'], 'booths': by_venue}, open(os.path.join(ROOT, 'raw/abs/sa1_census_2006.json'), 'w'), separators=(',', ':'))
    json.dump({**base, 'units': {'vic_la_2022': units['d22'], 'vic_la_2001': units['d01'], 'fed_2003': units['f03']}, 'booths': by_venue}, open(os.path.join(ROOT, 'raw/abs/cd_census_2006.json'), 'w'), separators=(',', ':'))
    print(f'state: population {state["population"]:,}, median age {state.get("age_median")}, born overseas {state.get("born_overseas")}, no religion {state.get("religion_no_religion_so_described")}, '
          f'degree {state.get("bachelor_or_higher")}, unemployment {state.get("unemployment_rate")}, median personal income ${state.get("income_personal_median")}')


if __name__ == '__main__':
    main()
