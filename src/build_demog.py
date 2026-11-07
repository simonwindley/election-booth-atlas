"""Assemble the site's census files for the 2022 boundaries from the SA1 aggregates (src.load_sa1_census):

site/data/demog_vic_la_2022.json.gz   districts: 2021 indicators (SA1 aggregation), the Parliament of Victoria
                                      cards' own extras and true district medians, change-since-2016 / since-2011
                                      indicators, and a `history` block with the 2016 and 2011 figures per district
site/data/demog_booth_vic2022.json.gz booth catchments keyed by venue id: the same 2021 indicators, change
                                      indicators, and history

Change indicators: for a share, the difference in points (kind 'delta', stored as a fraction); for a median,
count or ratio, the percentage change (kind 'pct'). They use the SA1 series for every year, so a 2021 figure in a
change indicator can differ slightly from the true district median shown as the level.

Usage: python3 -m src.build_demog        (then src.model_issues adds the modelled issue priorities)
"""
import os, json, gzip
from src import load_demographics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Parliament card ids whose figure replaces the SA1 estimate (true district medians; cards' own counts)
MED_FROM_CARDS = {'age_median': 'age_median', 'income_household_median': 'income_and_expense_income', 'mortgage_median_monthly': 'income_and_expense_mortage', 'rent_median': 'income_and_expense_rent'}
CARD_DUP = {'population_total_persons', 'population_male', 'population_female', 'age_median', 'income_and_expense_income', 'income_and_expense_mortage', 'income_and_expense_rent',
            'household_ownership_owned', 'household_ownership_mortgage', 'household_ownership_rented', 'country_of_birth_born_in_australia', 'language_speaks_only_english',
            'health_need_assistance', 'motor_vehicle_ownership_no_motor_vehicles', 'volunteering_for_organisation_or_group', 'dwelling_type_and_household_details_persons_per_bedroom',
            'dwelling_type_and_household_details_people_per_household', 'engaged_in_education_tertiary', 'engaged_in_education_secondary', 'engaged_in_education_primary', 'engaged_in_education_preschool', 'engaged_in_education_other'}
CHANGE_SKIP_GROUPS = {'Model inputs'}
CORE = ['population', 'age_median', 'age_0_17', 'age_65_plus', 'income_household_median', 'income_personal_median', 'rent_median', 'mortgage_median_monthly', 'born_australia', 'born_overseas', 'speaks_english_only',
        'other_language_home', 'religion_no_religion_so_described', 'religion_catholic', 'religion_islam', 'religion_hinduism', 'year12', 'bachelor_or_higher', 'owned_outright', 'owned_mortgage', 'rented', 'social_housing',
        'separate_house', 'flat_apartment', 'unemployment_rate', 'participation_rate', 'occupation_professionals', 'occupation_managers', 'occupation_labourers', 'travel_public_transport', 'travel_car_driver', 'worked_at_home',
        'need_assistance', 'volunteer', 'couple_families_with_children', 'one_parent_families', 'household_size', 'no_motor_vehicle', 'indigenous', 'australian_citizens']


def load(year):
    return json.load(open(os.path.join(ROOT, f'raw/abs/sa1_census_{year}.json')))


def gz_write(path, obj):
    with open(path, 'wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as fh:
        fh.write(json.dumps(obj, separators=(',', ':')).encode())


def change_indicators(ind21, units21, units16, units11, state21, state16, state11):
    """add chg16_/chg11_ indicators to the indicator list and values to every unit (and the state)"""
    new = []
    for x in ind21:
        if x.get('hidden') or x['group'] in CHANGE_SKIP_GROUPS or x['kind'] == 'text':
            continue
        for tag, label, units_then, state_then in (('chg16', 'since 2016', units16, state16), ('chg11', 'since 2011', units11, state11)):
            if state_then.get(x['id']) is None:
                continue
            kind = 'delta' if x['kind'] == 'share' else 'pct'
            nid = f'{tag}_{x["id"]}'
            new.append({'id': nid, 'group': f'Change {label}: {x["group"].lower()}', 'label': x['label'], 'kind': kind, 'base': x['id'], 'since': 2016 if tag == 'chg16' else 2011})
            for uid, rec in units21.items():
                then = units_then.get(uid, {}).get(x['id']); now = rec.get(x['id'])
                if then is None or now is None:
                    continue
                if kind == 'delta':
                    rec[nid] = round(now - then, 5)
                elif then:
                    rec[nid] = round((now - then) / then, 4)
            then, now = state_then.get(x['id']), state21.get(x['id'])
            if then is not None and now is not None:
                state21[nid] = round(now - then, 5) if kind == 'delta' else (round((now - then) / then, 4) if then else None)
    return new


def main():
    c21, c16, c11 = load('2021'), load('2016'), load('2011')
    cards = load_demographics.main(out=os.path.join(ROOT, 'raw/demographics/parliament_cards.json.gz'))
    # ---- districts
    ind = [dict(x) for x in c21['indicators']]
    ids21 = {x['id'] for x in ind}
    districts = {}
    for cid, rec in c21['districts'].items():
        card = cards['districts'].get(cid, {})
        d = {'name': card.get('name') or cid, 'region': card.get('region'), **rec}
        d['population_sa1'] = rec.get('population')
        districts[cid] = d
    state = dict(c21['state'])
    # history from the SA1 series (all three years), before the card medians replace the 2021 levels
    history = {cid: {'2016': {k: v for k, v in c16['districts'].get(cid, {}).items() if not k.startswith('mi_')},
                     '2011': {k: v for k, v in c11['districts'].get(cid, {}).items() if not k.startswith('mi_')},
                     '2021': {k: v for k, v in rec.items() if not k.startswith('mi_')}} for cid, rec in c21['districts'].items()}
    state_history = {'2021': {k: v for k, v in c21['state'].items() if not k.startswith('mi_')}, '2016': {k: v for k, v in c16['state'].items() if not k.startswith('mi_')}, '2011': {k: v for k, v in c11['state'].items() if not k.startswith('mi_')}}
    ind += change_indicators(c21['indicators'], districts, c16['districts'], c11['districts'], state, c16['state'], c11['state'])
    # the cards' true district medians replace the SA1 population-weighted means for the 2021 level
    for mine, theirs in MED_FROM_CARDS.items():
        for cid, d in districts.items():
            v = cards['districts'].get(cid, {}).get(theirs)
            if v is not None:
                d[mine] = v
        if cards['state'].get(theirs) is not None:
            state[mine] = cards['state'][theirs]
    for x in ind:
        if x['id'] in MED_FROM_CARDS:
            x['note'] = 'District figure: the true median from the Parliament of Victoria cards; booth figures are population-weighted means of SA1 medians'
        elif x['kind'] in ('years', 'dollars', 'ratio'):
            x['note'] = 'Population-weighted mean of the SA1 medians, which runs a little above a true median'
    # cards' extras not covered by the ABS set
    extra = [x for x in cards['indicators'] if x['id'] not in CARD_DUP and x['id'] not in ids21 and '_cat_' not in x['id']]
    for x in extra:
        x = dict(x); x['group'] = x['group'] + ' (Parliament of Victoria cards)' if x['kind'] != 'text' else x['group']; ind.append(x)
    exids = {x['id'] for x in extra}
    for cid, d in districts.items():
        src = cards['districts'].get(cid, {})
        d.update({k: v for k, v in src.items() if k in exids or (k.endswith('_share') and k[:-6] in exids)})
    state.update({k: v for k, v in cards['state'].items() if k in exids or (k.endswith('_share') and k[:-6] in exids)})
    # the cards' derived category-share axes (most common religion / birthplace etc.)
    cat = [x for x in cards['indicators'] if '_cat_' in x['id']]
    ind += cat
    catids = {x['id'] for x in cat}
    for cid, d in districts.items():
        d.update({k: v for k, v in cards['districts'].get(cid, {}).items() if k in catids})
    state.update({k: v for k, v in cards['state'].items() if k in catids})
    obj = {'source': 'ABS Census 2021, 2016 and 2011 SA1 DataPacks aggregated onto the 2022 Victorian districts by the share of each SA1 inside each district; plus the Parliament of Victoria Library electorate data cards (true district medians and their own extras)',
           'merged': True, 'sa1': True, 'census': 2021, 'boundaries': 'vic_la_2022', 'indicators': ind, 'state': state, 'districts': districts,
           'history': history, 'state_history': state_history,
           'note': 'State medians are population-weighted averages of the district medians, not the true state median. The 2021 Census was taken on 10 August 2021, during Melbourne\'s lockdown, so travel-to-work and worked-at-home figures describe that week, not normal commuting. Change indicators compare the same SA1-based series across censuses; nominal dollars are not adjusted for inflation.'}
    out = os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')
    gz_write(out, obj)
    print(f'districts: {len(districts)} districts, {len(ind)} indicators ({len(extra)} from the cards, {sum(1 for x in ind if x["id"].startswith("chg"))} change) -> {out}')
    # ---- booths (by venue)
    bind = [dict(x) for x in c21['indicators']]
    booths = {vid: dict(rec) for vid, rec in c21['booths'].items()}
    bstate = dict(c21['state'])
    bhist = {vid: {'2016': {k: v for k, v in c16['booths'].get(vid, {}).items() if not k.startswith('mi_') and k != 'booth_id'},
                   '2011': {k: v for k, v in c11['booths'].get(vid, {}).items() if not k.startswith('mi_') and k != 'booth_id'}} for vid in booths}
    bind += change_indicators(c21['indicators'], booths, c16['booths'], c11['booths'], bstate, c16['state'], c11['state'])
    for x in bind:
        if x['kind'] in ('years', 'dollars', 'ratio'):
            x['note'] = 'Population-weighted mean of the SA1 medians, which runs a little above a true median'
    # columnar storage keeps the booth file small: one shared id list, one value array per venue (null = no figure)
    bcols = [x['id'] for x in bind if not x.get('hidden')]
    hcols = [c for c in CORE if any(c in y for h in bhist.values() for y in h.values())]   # booth history: the headline indicators only, to keep the file small
    r4 = lambda v: (round(v, 4) if isinstance(v, float) else v)
    bvals = {vid: {'booth_id': rec['booth_id'], 'v': [r4(rec.get(c)) for c in bcols], 'h': {y: [r4(h.get(c)) for c in hcols] for y, h in bhist[vid].items()}} for vid, rec in booths.items()}
    bobj = {'source': 'ABS Census 2021, 2016 and 2011 SA1 DataPacks aggregated onto the 2022 election-day booth catchments (the area nearest each booth within its district) by the share of each SA1 inside each catchment',
            'census': 2021, 'boundaries': 'vic_la_2022', 'keyed_by': 'venue_id', 'indicators': [x for x in bind if not x.get('hidden')], 'cols': bcols, 'hcols': hcols, 'state': bstate, 'state_history': state_history, 'booths': bvals,
            'note': 'A catchment is who lives nearest the booth, not who votes there: early, postal and absent votes are not tied to a booth. Small catchments carry small-area census noise.'}
    bout = os.path.join(ROOT, 'site/data/demog_booth_vic2022.json.gz')
    gz_write(bout, bobj)
    print(f'booths: {len(booths)} venues, {len(bcols)} indicators -> {bout} ({os.path.getsize(bout) // 1000} kB)')
    plain = os.path.join(ROOT, 'site/data_plain')
    if os.path.isdir(plain):
        json.dump(obj, open(os.path.join(plain, 'demog_vic_la_2022.json'), 'w'), separators=(',', ':'))
        json.dump(bobj, open(os.path.join(plain, 'demog_booth_vic2022.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
