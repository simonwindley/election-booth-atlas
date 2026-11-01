"""2021 Census indicators for the 88 Victorian districts on the 2022 boundaries, from the Parliament of Victoria
Library's "Electorate data cards" workbook (raw/demographics/abs-electorate-data-2021v2.xlsx; ABS Census 2021
collated to 2022 electorates). Two sheets, each with a two-row header (group / indicator) and one row per district,
plus "Victoria - Total" and "No usual address".

Writes site/data/demog_vic2022.json:
  {source, indicators: [{id, group, label, kind}], state: {id: value}, districts: {contest_id: {name, region, id: value}}}
Shares are stored as fractions (0-1); medians as dollars / years; areas in km2. Text "most common" columns are kept
as paired text/share indicators (e.g. religion_1 = 'Catholic', religion_1_share = 0.21).

Usage: python3 -m src.load_demographics [xlsx] [out]
"""
import sys, re, json, os
import openpyxl

SLUG = lambda s: 'vic-' + re.sub(r'[^a-z]+', '-', s.lower()).strip('-')
KIND_HINT = {'Total persons': 'count', 'Kilometres squared': 'area', 'Income': 'dollars', 'Mortage': 'dollars', 'Mortgage': 'dollars', 'Rent': 'dollars',
             'Median (in years)': 'years', 'Persons per bedroom (average)': 'ratio', 'People per household (average)': 'ratio'}


def ident(group, label):
    s = re.sub(r'\(.*?\)', '', f'{group} {label}').lower()
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return s[:60]


def read_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    groups, cur = [], None
    for a in rows[0]:
        if a is not None:
            cur = re.sub(r'\s+', ' ', str(a)).strip()
        groups.append(cur)
    labels = [re.sub(r'\s+', ' ', str(b)).strip() if b is not None else None for b in rows[1]]
    cols = []   # (index, group, label, kind, id)
    i = 2
    ncol = len(rows[1])
    pending_text = None
    while i < ncol:
        g, l = groups[i], labels[i]
        sample = next((r[i] for r in rows[2:] if r[0] is not None and r[i] is not None), None)
        if sample is None:
            i += 1; continue
        if isinstance(sample, str) and not re.fullmatch(r'[\d.,%$ ]+', sample):
            # a "most common" text column: the next column holds its share; up to three pairs follow
            base = ident(g, l or 'most common') if l else pending_text
            pending_text = base
            n = 1
            while i < ncol and isinstance(next((r[i] for r in rows[2:] if r[0] is not None and r[i] is not None), None), str):
                cols.append((i, g, f'{l or g}: #{n}', 'text', f'{base}_{n}'))
                if i + 1 < ncol:
                    cols.append((i + 1, g, f'{l or g}: #{n} share', 'share', f'{base}_{n}_share'))
                i += 2; n += 1
                l = None
            continue
        kind = KIND_HINT.get(l, 'share') if (g or '').startswith(('Income', 'Electorate size', 'Population', 'Age', 'Dwelling')) else 'share'
        if kind == 'share' and isinstance(sample, (int, float)) and sample > 1.5:
            kind = 'number'
        cols.append((i, g, l, kind, ident(g, l)))
        i += 1
    recs = {}
    for r in rows[2:]:
        if r[0] is None:
            continue
        name = str(r[0]).strip()
        rec = {'region': str(r[1]).strip() if r[1] is not None and str(r[1]).strip() != 'NA' else None}
        for (ci, g, l, kind, cid) in cols:
            v = r[ci]
            if v is None or (isinstance(v, str) and v.strip() in ('NA', '')):
                continue
            if kind == 'text':
                rec[cid] = str(v).strip()
            else:
                try:
                    rec[cid] = float(str(v).replace('$', '').replace(',', '').replace('%', ''))
                except ValueError:
                    continue
        recs[name] = rec
    return [{'id': cid, 'group': g, 'label': l, 'kind': kind} for (ci, g, l, kind, cid) in cols], recs


def main(xlsx='raw/demographics/abs-electorate-data-2021v2.xlsx', out='site/data/demog_vic_la_2022.json.gz'):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    indicators, recs = [], {}
    seen = set()
    for ws in wb.worksheets:
        ind, rr = read_sheet(ws)
        for x in ind:
            if x['id'] not in seen:
                seen.add(x['id']); indicators.append(x)
        for name, rec in rr.items():
            recs.setdefault(name, {}).update(rec)
    state = recs.pop('Victoria - Total', {}); recs.pop('No usual address', None)
    # tidy labels
    NICE = {'religion': 'religion', 'country_of_birth': 'birthplace other than Australia', 'dwelling_type': 'dwelling type', 'motor_vehicle': 'number of motor vehicles'}
    for x in indicators:
        x['label'] = x['label'].replace('Mortage', 'Mortgage').replace('Australian Citizens', 'Australian citizens')
        m = re.match(r'^(.*?)_(\d)(_share)?$', x['id'])
        if x['kind'] in ('text',) or (m and x['id'].endswith('_share') and '_most_common_' in x['id'] or (m and 'country_of_birth_country' in x['id'])):
            base = next((v for k, v in NICE.items() if x['id'].startswith(k)), x['group'].lower())
            n = m.group(2); x['label'] = f'{"Most common " if n == "1" else ("2nd " if n == "2" else "3rd ")}{base}' + (' (share)' if x['id'].endswith('_share') else '')
        x['group'] = re.sub(r'\s*\(.*?\)\s*$', '', x['group'])
    NICE_LABEL = {'population_total_persons': 'Population', 'electorate_size_kilometres_squared': 'Area (km²)', 'income_and_expense_income': 'Median weekly household income',
                  'income_and_expense_mortage': 'Median weekly mortgage repayment', 'income_and_expense_rent': 'Median weekly rent', 'household_ownership_owned': 'Home owned outright',
                  'household_ownership_mortgage': 'Home owned with a mortgage', 'household_ownership_rented': 'Renting', 'country_of_birth_born_in_australia': 'Born in Australia',
                  'language_speaks_only_english': 'Speaks only English at home', 'health_no_longer_term_health_concerns': 'No long-term health condition', 'health_need_assistance': 'Needs assistance with core activities',
                  'age_median': 'Median age', 'engaged_in_education_tertiary': 'Students at university or TAFE (share of all students)', 'engaged_in_education_secondary': 'Students at secondary school (share of all students)', 'engaged_in_education_primary': 'Students at primary school (share of all students)',
                  'engaged_in_education_preschool': 'Students at preschool (share of all students)', 'engaged_in_education_other': 'Students at other institutions (share of all students)', 'population_australian_citizens': 'Australian citizens', 'population_first_nations': 'First Nations (share of citizens)',
                  'armed_forces_service': 'Armed forces service (current or past)', 'volunteering_for_organisation_or_group': 'Volunteers for an organisation or group', 'motor_vehicle_ownership_no_motor_vehicles': 'Households with no motor vehicle',
                  'dwelling_type_and_household_details_persons_per_bedroom': 'Persons per bedroom', 'dwelling_type_and_household_details_people_per_household': 'People per household'}
    for x in indicators:
        if x['id'] in NICE_LABEL:
            x['label'] = NICE_LABEL[x['id']]
        if x['id'].startswith('engaged_in_education'):
            x['group'] = 'Students, by type of institution'   # ABS G15: people currently attending, not attainment
    districts = {}
    for name, rec in recs.items():
        cid = SLUG(name)
        districts[cid] = {'name': name, **rec}
    # derived axes from the "most common" lists: the share of each named category, for the seats where it is in the top three
    bases = {}
    for x in indicators:
        m = re.match(r'^(.*)_(\d)$', x['id'])
        if x['kind'] == 'text' and m:
            bases.setdefault(m.group(1), []).append(x)
    GROUP = {'religion_most_common': 'Religion', 'country_of_birth_country_of_birth_other_than_australia': 'Birthplace other than Australia',
             'dwelling_type_and_household_details_most_common_dwelling': 'Dwelling type', 'motor_vehicle_ownership_most_common_number_of_motor_vehicles': 'Motor vehicles per household'}
    for base, cols in bases.items():
        counts = {}
        for d in list(districts.values()) + [state]:
            for x in cols:
                v = d.get(x['id'])
                if v and d.get(x['id'] + '_share') is not None:
                    counts[v] = counts.get(v, 0) + 1
        for v, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            if n < 3 or v == 'Elsewhere':
                continue
            nid = f"{base}_cat_{re.sub(r'[^a-z0-9]+', '_', v.lower()).strip('_')}"
            indicators.append({'id': nid, 'group': GROUP.get(base, base) + ' (share; seats where it is in the top three)', 'label': v, 'kind': 'share', 'partial': True})
            for d in list(districts.values()) + [state]:
                for x in cols:
                    if d.get(x['id']) == v and d.get(x['id'] + '_share') is not None:
                        d[nid] = d[x['id'] + '_share']
    obj = {'source': "Parliament of Victoria Library, Electorate data cards (April 2026): ABS Census 2021 collated to the 2022 Victorian electorates",
           'census': 2021, 'boundaries': 'vic_la_2022', 'indicators': indicators, 'state': state, 'districts': districts}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    import gzip
    with gzip.open(out, 'wt') as fh:
        json.dump(obj, fh, separators=(',', ':'))
    print(f'{len(districts)} districts, {len(indicators)} indicators ->', out)
    return obj


if __name__ == '__main__':
    main(*sys.argv[1:3])
