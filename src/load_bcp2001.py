"""2001 Census indicators for the Victorian state electoral districts in force at the 1999 election, from the ABS 2001
Basic Community Profiles (BCP) by State Electoral Division (SED).

The 2001 Census was coded to the districts drawn in 1991 (used at the 1992 and 1996 elections and at the 1999 election),
so each SED profile is exactly one 1999 district: no apportioning is needed. The profiles are the ABS's own
spreadsheets (cat. 2001.0, place of enumeration), downloaded by tools/fetch_bcp2001.py into raw/abs/bcp2001/
(BCP_SED<code>.xlsx per district, BCP_2.xlsx for Victoria).

Indicators keep the ids of the 2006-2021 series where the definition matches. Differences worth knowing:
  - place of enumeration (where people were on census night), not usual residence as in 2006-2021
  - medians (age, weekly personal and household income, in 2001 dollars) are interpolated from the profile's bands
  - occupation is coded to ASCO (2nd edition), not ANZSCO: managers, professionals, trades, labourers and
    production/transport workers are close equivalents, the clerical/sales/service groups are not carried
  - 'english_not_well' counts overseas-born people only (the BCP tabulates proficiency for them alone), over everyone
  - internet is personal use in the week before the census (no household connection question until 2006)

Input  raw/abs/bcp2001/BCP_*.xlsx, site/data/boundary_vic_la_1991.geojson.gz
Output site/data/demog_vic_la_1991.json.gz (and site/data_plain/demog_vic_la_1991.json when that folder exists)
Usage  python3 -m src.load_bcp2001
"""
import os, re, json, gzip, glob, warnings
import openpyxl
from .load_cd_census import median

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings('ignore', module='openpyxl')


class Sheet:
    """one BCP table: rows of (label, [values by column])"""
    def __init__(self, ws):
        self.rows = []
        for r in ws.iter_rows(values_only=True):
            self.rows.append([None if v is None or (isinstance(v, str) and v.strip() in ('', '|')) else (v.strip() if isinstance(v, str) else v) for v in r])

    def find(self, label, after=None, start=0, labcol=0):
        i0 = start
        if after:
            i0 = next(i for i, r in enumerate(self.rows) if i >= start and len(r) > labcol and isinstance(r[labcol], str) and r[labcol].startswith(after)) + 1
        for i in range(i0, len(self.rows)):
            r = self.rows[i]
            if len(r) > labcol and isinstance(r[labcol], str) and r[labcol].startswith(label):
                return i
        raise KeyError(f'{label!r} after {after!r}')

    def val(self, label, col, after=None, start=0, labcol=0):
        r = self.rows[self.find(label, after, start, labcol)]
        v = r[col] if col < len(r) else None
        return float(v) if isinstance(v, (int, float)) else 0.0


def ages(S):
    """single years 0-79 and bands 80-84 ... 100+ from B03 (persons columns 3, 8, 13)"""
    single, bands = {}, {}
    for r in S.rows:
        for lc, pc in ((0, 3), (5, 8), (10, 13)):
            if len(r) <= pc or r[lc] is None or not isinstance(r[pc], (int, float)):
                continue
            lab = str(r[lc]).replace(' years', '').strip()
            if re.fullmatch(r'\d+', lab):
                single[int(lab)] = float(r[pc])
            elif (m := re.fullmatch(r'(8\d|9\d)-(\d+)', lab)):
                bands[int(m.group(1))] = float(r[pc])
            elif lab.startswith('100'):
                bands[100] = float(r[pc])
    cnt = [single.get(a, 0.0) for a in range(80)] + [bands.get(a, 0.0) for a in (80, 85, 90, 95, 100)]
    edges = [(a, a + 1) for a in range(80)] + [(80, 85), (85, 90), (90, 95), (95, 100), (100, 110)]
    return cnt, edges


PERS_INC = [(None, 0), (1, 39), (40, 79), (80, 119), (120, 159), (160, 199), (200, 299), (300, 399), (400, 499), (500, 599), (600, 699), (700, 799), (800, 999), (1000, 1499), (1500, 2500)]
PERS_LAB = ['Negative/Nil', '$1-$39', '$40-$79', '$80-$119', '$120-$159', '$160-$199', '$200-$299', '$300-$399', '$400-$499', '$500-$599', '$600-$699', '$700-$799', '$800-$999', '$1,000-$1,499', '$1,500 or more']
HH_INC = [(None, 0), (1, 199), (200, 299), (300, 399), (400, 499), (500, 599), (600, 699), (700, 799), (800, 999), (1000, 1199), (1200, 1499), (1500, 1999), (2000, 3000)]
HH_LAB = ['Negative/Nil', '$1-$199', '$200-$299', '$300-$399', '$400-$499', '$500-$599', '$600-$699', '$700-$799', '$800-$999', '$1,000-$1,199', '$1,200-$1,499', '$1,500-$1,999', '$2,000 or more']


def profile(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    T = {n.replace(' ', ''): Sheet(wb[n]) for n in wb.sheetnames if n.startswith('B ')}
    title = str(T['B01'].rows[1][0]).split(',')[0].strip()   # 'Caulfield (Monash) (SED 22115) ,  16.7 sq. Kms'
    out = {}
    def share(id_, num, den):
        if den > 0:
            out[id_] = round(num / den, 5)
    b1 = T['B01']
    tot = b1.val('Total persons', 3); ov = b1.val('Overseas visitors', 3)
    pop = tot - ov
    out['population'] = int(round(tot))
    # age
    cnt, edges = ages(T['B03'])
    m = median(cnt, edges)
    if m is not None: out['age_median'] = round(m, 1)
    n = sum(cnt)
    yrs = lambda a, b: sum(cnt[a:b])
    share('age_0_17', yrs(0, 18), n); share('age_15_24', yrs(15, 25), n); share('age_25_34', yrs(25, 35), n); share('age_35_49', yrs(35, 50), n)
    share('age_50_64', yrs(50, 65), n); share('age_65_plus', yrs(65, 85), n)
    adults = yrs(18, 85)
    share('adults_18_34', yrs(18, 35), adults); share('adults_35_54', yrs(35, 55), adults); share('adults_55_plus', yrs(55, 85), adults)
    # income (2001 dollars)
    s13 = T['B13B']; st = s13.find('PERSONS', labcol=5)
    inc = [s13.val(l, 9, start=st) for l in PERS_LAB]
    if sum(inc) > 0: out['income_personal_median'] = round(median(inc, PERS_INC), 0)
    s31 = T['B31']
    hh = [s31.val(l, 3) for l in HH_LAB]
    if sum(hh) > 0: out['income_household_median'] = round(median(hh, HH_INC), 0)
    # birthplace
    b7a, b7b = T['B07A'], T['B07B']
    b_tot = b7b.val('Total', 3, after='Overseas visitors') - b7b.val('Overseas visitors', 3)
    b_aus = b7a.val('Australia', 3); b_ns = b7b.val('Not stated', 3)
    share('born_australia', b_aus, b_tot); share('born_overseas', b_tot - b_aus - b_ns, b_tot)
    share('born_uk_ireland', b7a.val('United Kingdom', 3) + b7a.val('Ireland', 3), b_tot)
    share('born_new_zealand', T['B06'].val('New Zealand', 3), b_tot)
    for lab, hdr, sh in (('born_southern_eastern_europe', 'Southern and Eastern Europe:', b7a), ('born_north_africa_middle_east', 'North Africa and the Middle East:', b7a),
                         ('born_south_east_asia', 'South-East Asia:', b7a), ('born_north_east_asia', 'North-East Asia:', b7b),
                         ('born_southern_central_asia', 'Southern and Central Asia:', b7b), ('born_sub_saharan_africa', 'Sub-Saharan Africa:', b7b)):
        share(lab, sh.val('Total', 3, after=hdr), b_tot)
    # language
    b8 = T['B08']
    lan_tot = b8.val('Total', 3, after='Overseas visitors') - b8.val('Overseas visitors', 3)
    share('speaks_english_only', b8.val('Speaks English only', 3), lan_tot)
    share('other_language_home', b8.val('Total', 3, after='Other(a)'), lan_tot)
    share('language_greek', b8.val('Greek', 3), lan_tot); share('language_italian', b8.val('Italian', 3), lan_tot)
    share('language_chinese_all', b8.val('Total', 3, after='Chinese languages:'), lan_tot)
    share('language_middle_eastern_semitic', b8.val('Arabic', 3), lan_tot)
    share('language_mon_khmer', b8.val('Vietnamese', 3) + b8.val('Khmer', 3), lan_tot)
    share('english_not_well', T['B09'].val('Not well or Not at all', 11), pop)
    # religion
    b10 = T['B10']
    rel_tot = b10.val('Total', 3, after='Overseas visitors') - b10.val('Overseas visitors', 3)
    share('religion_buddhism', b10.val('Buddhism', 3), rel_tot)
    share('religion_christianity_total', b10.val('Total', 3, after='Christianity:'), rel_tot)
    share('religion_catholic', b10.val('Catholic', 3), rel_tot); share('religion_anglican', b10.val('Anglican', 3), rel_tot)
    share('religion_hinduism', b10.val('Hinduism', 3), rel_tot); share('religion_islam', b10.val('Islam', 3), rel_tot); share('religion_judaism', b10.val('Judaism', 3), rel_tot)
    share('religion_other_religions_total', b10.val('Total', 3, after='Other Religions:'), rel_tot)
    share('religion_no_religion_so_described', b10.val('No religion', 3), rel_tot)
    # education
    b12 = T['B12']
    share('year12', b12.val('Year 12', 3), b12.val('Total', 3) - b12.val('Not stated', 3))
    b23 = T['B23']; p15 = b23.val('Total', 3)
    share('bachelor_or_higher', b23.val('Postgraduate', 3) + b23.val('Graduate Diploma', 3) + b23.val('Bachelor', 3), p15)
    share('postgraduate', b23.val('Postgraduate', 3), p15); share('diploma', b23.val('Advanced Diploma', 3), p15); share('certificate', b23.val('Certificate', 3), p15)
    # tenure (B19 total row: fully owned, being purchased, rent/buy, SHA, other rented, rented ns, rented total, other, not stated, total)
    b19 = T['B19']; r = b19.rows[b19.find('Total')]
    v = [float(x) if isinstance(x, (int, float)) else 0.0 for x in r[1:11]]
    t_tot = v[9] - v[8]
    share('owned_outright', v[0], t_tot); share('owned_mortgage', v[1] + v[2], t_tot); share('rented', v[6], t_tot); share('social_housing', v[3], t_tot)
    # dwelling structure (occupied private dwellings)
    b18 = T['B18']
    s_tot = b18.val('Total', 1, after='Unoccupied') - b18.val('Unoccupied', 1) - b18.val('Not stated', 1)
    share('separate_house', b18.val('Separate house', 1), s_tot)
    share('townhouse', b18.val('Total', 1, after='Semi-detached'), s_tot)
    share('flat_apartment', b18.val('Total', 1, after='Flat, unit'), s_tot)
    # internet use, cars
    b16 = T['B16']
    share('internet_not_used', b16.val('Did not use', 3), b16.val('Total', 3, after='Overseas visitors') - b16.val('Not stated', 3) - b16.val('Overseas visitors', 3))
    # labour force (persons 15+)
    b25 = T['B25']; st = b25.find('PERSONS', labcol=7); r = b25.rows[b25.find('Total', start=st)]
    f = [float(x) if isinstance(x, (int, float)) else 0.0 for x in r[:13]]
    share('unemployment_rate', f[8], f[9]); share('participation_rate', f[9], f[12] - f[11]); share('part_time_share', f[2], f[1] + f[2])
    # occupation (ASCO 2nd edition; persons, total column 8)
    b27 = T['B27B']
    occ_tot = b27.val('Total', 8) - b27.val('Not stated', 8)
    for lab, row in (('occupation_managers', 'Managers and Administrators'), ('occupation_professionals', 'Professionals'), ('occupation_associate_professionals', 'Associate Professionals'),
                     ('occupation_technicians_and_trades_workers', 'Tradespersons'), ('occupation_machinery_operators_and_drivers', 'Intermediate Production'), ('occupation_labourers', 'Labourers')):
        share(lab, b27.val(row, 8), occ_tot)
    share('indigenous', b1.val('Total Indigenous', 3), tot)
    return title, out


def no_car(path):
    """households with no motor vehicle, of households that stated the number (B29)"""
    wb = openpyxl.load_workbook(path, read_only=True); S = Sheet(wb['B 29'])
    none = S.val('Total', 2, after='No motor vehicles')
    ns = S.val('Total', 2, after='Number of motor vehicles not stated')
    tot = next(float(r[2]) for r in reversed(S.rows) if len(r) > 2 and r[0] == 'Total' and isinstance(r[2], (int, float)))
    return round(none / (tot - ns), 5) if tot - ns > 0 else None


IND_META = [
    ('population', 'Population', 'Population (census night)', 'count'), ('age_median', 'Age', 'Median age', 'years'), ('age_0_17', 'Age', 'Under 18', 'share'), ('age_15_24', 'Age', '15 to 24', 'share'),
    ('age_25_34', 'Age', '25 to 34', 'share'), ('age_35_49', 'Age', '35 to 49', 'share'), ('age_50_64', 'Age', '50 to 64', 'share'), ('age_65_plus', 'Age', '65 and over', 'share'),
    ('adults_18_34', 'Age', 'Adults aged 18 to 34 (of adults)', 'share'), ('adults_35_54', 'Age', 'Adults aged 35 to 54 (of adults)', 'share'), ('adults_55_plus', 'Age', 'Adults aged 55 and over (of adults)', 'share'),
    ('income_personal_median', 'Income', 'Median weekly personal income (2001 dollars)', 'dollars'), ('income_household_median', 'Income', 'Median weekly household income (2001 dollars)', 'dollars'),
    ('born_australia', 'Birthplace', 'Born in Australia', 'share'), ('born_overseas', 'Birthplace', 'Born overseas', 'share'), ('born_uk_ireland', 'Birthplace', 'Born in the UK or Ireland', 'share'),
    ('born_new_zealand', 'Birthplace', 'Born in New Zealand', 'share'), ('born_southern_eastern_europe', 'Birthplace', 'Born in southern or eastern Europe', 'share'),
    ('born_north_africa_middle_east', 'Birthplace', 'Born in North Africa or the Middle East', 'share'), ('born_south_east_asia', 'Birthplace', 'Born in South-East Asia', 'share'),
    ('born_north_east_asia', 'Birthplace', 'Born in North-East Asia', 'share'), ('born_southern_central_asia', 'Birthplace', 'Born in southern or central Asia', 'share'), ('born_sub_saharan_africa', 'Birthplace', 'Born in sub-Saharan Africa', 'share'),
    ('speaks_english_only', 'Language', 'Speaks only English at home', 'share'), ('other_language_home', 'Language', 'Speaks a language other than English at home', 'share'),
    ('english_not_well', 'Language', 'Born overseas, speaks English not well or not at all', 'share'), ('language_greek', 'Language', 'Greek', 'share'), ('language_italian', 'Language', 'Italian', 'share'),
    ('language_chinese_all', 'Language', 'Chinese languages', 'share'), ('language_middle_eastern_semitic', 'Language', 'Arabic', 'share'), ('language_mon_khmer', 'Language', 'Vietnamese and Khmer', 'share'),
    ('religion_buddhism', 'Religion', 'Buddhism', 'share'), ('religion_christianity_total', 'Religion', 'Christianity Total', 'share'), ('religion_catholic', 'Religion', 'Catholic', 'share'),
    ('religion_anglican', 'Religion', 'Anglican', 'share'), ('religion_hinduism', 'Religion', 'Hinduism', 'share'), ('religion_islam', 'Religion', 'Islam', 'share'), ('religion_judaism', 'Religion', 'Judaism', 'share'),
    ('religion_other_religions_total', 'Religion', 'Other Religions Total', 'share'), ('religion_no_religion_so_described', 'Religion', 'No Religion, so described', 'share'),
    ('year12', 'Education', 'Completed Year 12 (of persons 15+ who stated)', 'share'), ('bachelor_or_higher', 'Education', 'Bachelor degree or higher (of persons 15+)', 'share'),
    ('postgraduate', 'Education', 'Postgraduate degree (of persons 15+)', 'share'), ('diploma', 'Education', 'Advanced diploma or diploma (of persons 15+)', 'share'), ('certificate', 'Education', 'Certificate level (of persons 15+)', 'share'),
    ('owned_outright', 'Tenure', 'Owned outright', 'share'), ('owned_mortgage', 'Tenure', 'Being purchased', 'share'), ('rented', 'Tenure', 'Rented', 'share'), ('social_housing', 'Tenure', 'Rented from the state housing authority', 'share'),
    ('separate_house', 'Dwellings', 'Separate houses', 'share'), ('townhouse', 'Dwellings', 'Townhouses and terraces', 'share'), ('flat_apartment', 'Dwellings', 'Flats and apartments', 'share'),
    ('no_motor_vehicle', 'Dwellings', 'Households with no car', 'share'), ('internet_not_used', 'Dwellings', 'Did not use the internet in the week before the census', 'share'),
    ('unemployment_rate', 'Work', 'Unemployment rate (of the labour force)', 'share'), ('participation_rate', 'Work', 'Labour force participation', 'share'), ('part_time_share', 'Work', 'Part-time (of the employed)', 'share'),
    ('occupation_managers', 'Occupation', 'Managers and administrators', 'share'), ('occupation_professionals', 'Occupation', 'Professionals', 'share'), ('occupation_associate_professionals', 'Occupation', 'Associate professionals', 'share'),
    ('occupation_technicians_and_trades_workers', 'Occupation', 'Tradespersons', 'share'), ('occupation_machinery_operators_and_drivers', 'Occupation', 'Production and transport workers', 'share'), ('occupation_labourers', 'Occupation', 'Labourers', 'share'),
    ('indigenous', 'Population', 'Aboriginal and/or Torres Strait Islander', 'share')]


def norm(s):
    return re.sub(r'[^a-z]', '', s.lower())


def main():
    fc = json.load(gzip.open(os.path.join(ROOT, 'site/data/boundary_vic_la_1991.geojson.gz')))
    by_name = {norm(f['properties']['name']): f['properties']['contest_id'] for f in fc['features'] if f['properties'].get('contest_id')}
    names = {f['properties']['contest_id']: f['properties']['name'] for f in fc['features'] if f['properties'].get('contest_id')}
    districts, state = {}, None
    for path in sorted(glob.glob(os.path.join(ROOT, 'raw/abs/bcp2001/BCP_*.xlsx'))):
        title, ind = profile(path)
        nc = no_car(path)
        if nc is not None: ind['no_motor_vehicle'] = nc
        else: ind.pop('no_motor_vehicle', None)
        if os.path.basename(path) == 'BCP_2.xlsx':
            state = ind; continue
        nm = re.sub(r'\s*\(SED.*', '', title).strip()          # 'Caulfield (Monash) (SED 22115)' -> 'Caulfield (Monash)'
        nm = re.sub(r'\s*\([^)]*\)\s*$', '', nm).strip() if norm(nm) not in by_name else nm   # drop the region tag
        cid = by_name.get(norm(nm))
        if not cid:
            print('  no district for', title, path); continue
        districts[cid] = {'name': names[cid], 'sed': re.search(r'SED\s*(\d+)', title).group(1) if 'SED' in title else None, **ind}
    missing = sorted(set(names) - set(districts))
    print(f'{len(districts)} districts from the 2001 profiles; missing: {missing}')
    ind = [{'id': i, 'group': g, 'label': l, 'kind': k} for i, g, l, k in IND_META]
    o = {'source': 'ABS Census 2001, Basic Community Profiles by State Electoral Division (cat. 2001.0, place of enumeration); the 2001 SEDs are the districts used at the 1999 election',
         'census': 2001, 'boundaries': 'vic_la_1991', 'indicators': ind, 'state': state, 'districts': districts,
         'note': 'Medians (age, weekly personal and household income in 2001 dollars) are interpolated from the profile bands. Occupations use the 2001 ASCO classification, close to but not the same as the ANZSCO groups used from 2006.'}
    out = os.path.join(ROOT, 'site/data/demog_vic_la_1991.json.gz')
    with gzip.open(out, 'wt') as f:
        json.dump(o, f, separators=(',', ':'))
    plain = os.path.join(ROOT, 'site/data_plain')
    if os.path.isdir(plain):
        json.dump(o, open(os.path.join(plain, 'demog_vic_la_1991.json'), 'w'), separators=(',', ':'))
    s = state
    print(f'-> {out}; Victoria: population {s["population"]:,}, median age {s.get("age_median")}, personal income ${s.get("income_personal_median")}, household ${s.get("income_household_median")}, '
          f'born overseas {s.get("born_overseas")}, degree {s.get("bachelor_or_higher")}, unemployment {s.get("unemployment_rate")}, no car {s.get("no_motor_vehicle")}')


if __name__ == '__main__':
    main()
