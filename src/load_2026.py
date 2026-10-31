"""Build the 2026 pre-election register: contests, declared candidates, retiring members, withdrawals.

Source: the Wikipedia page "Candidates of the 2026 Victorian state election", captured through the
browser into raw/vec/2026/wikipedia_candidates_raw.json. Everything here is *declared* (pre-nomination)
and carries its source; the VEC nominations list (closes 9 Nov 2026) replaces it when published.

Usage: python3 -m src.load_2026 <raw_json> <out_dir> <retrieved_date>
"""
import sys, os, re, json
import pandas as pd
from .load_vec import slug

EID = 'vic2026'
LABEL_PARTY = {  # Wikipedia column / suffix label -> canonical code
    'labor': 'ALP', 'liberal': 'LIB', 'national': 'NAT', 'coalition': 'COAL', 'greens': 'GRN', 'one nation': 'ONP',
    'socialists': 'VSP', 'legalise cannabis': 'LCP', 'dlp': 'DLP', 'libertarian': 'LDP', 'sff': 'SFF', 'freedom': 'FRP',
    'ajp': 'AJP', 'family first': 'FFP', 'sustainable': 'SAP', 'new democrats': 'NDP', 'emi-reform': 'OTH', 'emi - reform': 'OTH',
    'citizens party': 'CYA', 'democrats': 'OTH', 'socialist alliance': 'OTH', 'west party': 'OTH', 'independent': 'IND',
}
SUFFIX_PARTY = {'l': 'LIB', 'lib': 'LIB', 'n': 'NAT', 'nat': 'NAT', 'ind': 'IND', 'ajp': 'AJP', 'ff': 'FFP', 'lbt': 'LDP', 'ldp': 'LDP',
                'sa': 'SAP', 'sap': 'SAP', 'on': 'ONP', 'onp': 'ONP', 'lc': 'LCP', 'lcp': 'LCP', 'dlp': 'DLP', 'sff': 'SFF', 'frp': 'FRP',
                'fp': 'FRP', 'vs': 'VSP', 'grn': 'GRN', 'alp': 'ALP', 'nd': 'NDP', 'cya': 'CYA', 'fus': 'FUS', 'hap': 'HAP', 'acp': 'CYA', 'cp': 'CYA', 'dem': 'OTH'}
PARTY_LABEL = {'ALP': 'Labor', 'LIB': 'Liberal', 'NAT': 'National', 'GRN': 'Greens', 'ONP': 'One Nation', 'VSP': 'Victorian Socialists',
               'LCP': 'Legalise Cannabis', 'DLP': 'DLP', 'LDP': 'Libertarian', 'SFF': 'Shooters, Fishers & Farmers', 'FRP': 'Freedom Party',
               'AJP': 'Animal Justice', 'FFP': 'Family First', 'SAP': 'Sustainable Australia', 'NDP': 'New Democrats', 'CYA': 'Citizens Party', 'IND': 'Independent', 'OTH': 'Other'}


PARTY_URL = {  # each party's own candidate listing (checked October 2026; the VEC's nominations list supersedes these from 9 Nov)
    'ALP': 'https://www.viclabor.com.au/candidates/', 'LIB': 'https://vic.liberal.org.au/candidates', 'NAT': 'https://vic.nationals.org.au/our-team/',
    'COAL': 'https://vic.liberal.org.au/candidates', 'GRN': 'https://greens.org.au/vic/candidates', 'ONP': 'https://www.onenation.org.au/candidates',
    'VSP': 'https://www.victoriansocialists.org.au/candidates', 'LCP': 'https://legalisecannabis.org.au/', 'AJP': 'https://animaljusticeparty.org/',
    'FFP': 'https://www.familyfirstparty.org.au/', 'LDP': 'https://www.libertarians.org.au/', 'SFF': 'https://www.shootersfishersandfarmers.org.au/',
    'DLP': 'https://dlp.org.au/', 'SAP': 'https://www.sustainableaustralia.org.au/', 'CYA': 'https://citizensparty.org.au/',
}


def split_names(cell):
    return [x.strip() for x in cell.split('|') if x.strip()]


def name_party(text, default):
    m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', text)
    if m:
        suffix = m.group(2).strip().lower()
        return m.group(1).strip(), SUFFIX_PARTY.get(suffix, default if default != 'COAL' else 'OTH'), m.group(2).strip()
    return text.strip(), default, ''


def main(raw_path, out, retrieved):
    d = json.load(open(raw_path))
    cands, contests, notes = [], [], []
    # ---- Legislative Assembly
    hdr = [c['text'] for c in d['assembly'][0]]
    col_party = {i: LABEL_PARTY.get(h.replace(' candidate', '').replace(' candidates', '').strip().lower()) for i, h in enumerate(hdr)}
    for row in d['assembly'][1:]:
        cells = [c['text'] for c in row]
        if len(cells) < 3 or not cells[0]:
            continue
        name, held = cells[0], cells[1]
        cid = f'vic-{slug(name)}'
        contests.append({'election_id': EID, 'contest_id': cid, 'contest_name': name, 'house': 'LA', 'held_by': held})
        for i, cell in enumerate(cells[2:], start=2):
            for who in split_names(cell):
                base = col_party.get(i)
                nm, party, suffix = name_party(who, base or 'OTH')
                if base == 'COAL' and not suffix:
                    party = 'COAL'
                cands.append({'election_id': EID, 'contest_id': cid, 'candidate_id': f'{cid}-{slug(nm)}', 'name': nm, 'party': party,
                              'party_label': PARTY_LABEL.get(party, suffix or party), 'incumbent': int(row[i]['bold']), 'status': 'declared',
                              'ticket_position': None, 'source': 'Wikipedia, Candidates of the 2026 Victorian state election', 'retrieved': retrieved})
    # ---- Legislative Council: alternating header rows ("<Party> | candidates") and candidate rows
    for region, rows in d['lc'].items():
        rid = f'vicr-{slug(region.replace("North Eastern", "North-Eastern").replace("South Eastern", "South-Eastern"))}'
        contests.append({'election_id': EID, 'contest_id': rid, 'contest_name': region.replace('North Eastern', 'North-Eastern').replace('South Eastern', 'South-Eastern'), 'house': 'LC', 'held_by': ''})
        cols = None
        for row in rows:
            cells = [c['text'] for c in row]
            if cells and all(('candidates' in c.lower()) or not c for c in cells) and any(cells):
                cols = [LABEL_PARTY.get(c.replace('| candidates', '').replace('candidates', '').strip().lower(), 'OTH') for c in cells]
                labels = [c.replace('| candidates', '').replace('candidates', '').strip() for c in cells]
                continue
            if cols is None or not any(cells):
                continue
            for i, cell in enumerate(cells):
                for pos, who in enumerate(split_names(cell), start=1):
                    nm, party, suffix = name_party(who, cols[i])
                    cands.append({'election_id': EID, 'contest_id': rid, 'candidate_id': f'{rid}-{slug(nm)}', 'name': nm, 'party': party,
                                  'party_label': PARTY_LABEL.get(party, labels[i]), 'incumbent': int(row[i]['bold']), 'status': 'declared',
                                  'ticket_position': pos, 'source': 'Wikipedia, Candidates of the 2026 Victorian state election', 'retrieved': retrieved})
    # ---- retiring members
    retiring = []
    for party, items in d['retiring'].items():
        for it in items:
            m = re.match(r'^\(?(.+?)\s*(†)?\s*(MLA|MLC)\s*\((.+?)\)\s*[–-]\s*announced\s*(.+?)(?:\s*\((.+)\))?$', it)
            if m:
                retiring.append({'election_id': EID, 'name': m.group(1).strip().rstrip(',').strip(), 'house': 'LA' if m.group(3) == 'MLA' else 'LC', 'seat': m.group(4).replace(' Region', ''),
                                 'party': LABEL_PARTY.get(party.lower(), party), 'announced': m.group(5).strip(), 'note': (m.group(6) or '') + (' (deceased)' if m.group(2) else '')})
            else:
                retiring.append({'election_id': EID, 'name': it, 'house': '', 'seat': '', 'party': party, 'announced': '', 'note': 'unparsed'})
    # ---- withdrawals / disendorsements
    wd = []
    for row in d['withdrawals'][1:]:
        cells = [c['text'] for c in row if c['text'] != '']
        if len(cells) >= 4:
            wd.append({'election_id': EID, 'date': cells[0], 'party': cells[1], 'candidate': cells[2], 'seat': cells[3], 'details': cells[4] if len(cells) > 4 else ''})
    # ---- links: Wikipedia article (captured with the register), Parliament of Victoria profile for sitting members
    links = d.get('links', {})
    slugs = {}
    sp = os.path.join(out, 'parliament_slugs.json')
    if os.path.exists(sp):
        slugs = json.load(open(sp))
    for c in cands:
        wp = links.get(c['name'])
        c['wikipedia_url'] = 'https://en.wikipedia.org' + wp if wp else ''
        c['parliament_url'] = ('https://www.parliament.vic.gov.au/members/' + slugs[c['name']]) if c['incumbent'] and slugs.get(c['name']) else ''
        if c['contest_id'].startswith('vicr-') and c['incumbent'] and slugs and not slugs.get(c['name']):
            c['incumbent'] = 0   # upper-house bold marks the whole ticket; keep the flag only for names with a Parliament page
        c['party_url'] = PARTY_URL.get(c['party'], '')
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(contests).to_csv(f'{out}/contests.csv', index=False)
    pd.DataFrame(cands).to_csv(f'{out}/candidates.csv', index=False)
    pd.DataFrame(retiring).to_csv(f'{out}/retiring.csv', index=False)
    pd.DataFrame(wd).to_csv(f'{out}/withdrawals.csv', index=False)
    json.dump({'source': 'Wikipedia, Candidates of the 2026 Victorian state election', 'page_last_edited': d.get('lastmod', ''), 'retrieved': retrieved,
               'key_dates': {'writs': '2026-11-03', 'roll_close': '2026-11-03', 'nominations_open': '2026-11-04', 'nominations_close': '2026-11-09',
                             'early_voting_open': '2026-11-18', 'early_voting_close': '2026-11-27', 'election_day': '2026-11-28'},
               'key_dates_source': 'https://www.vec.vic.gov.au/voting/2026-state-election',
               'voting': {
                   'postal': {'applications_open': '2026-11-04T09:00', 'applications_close': '2026-11-25T18:00', 'packs_posted_from': '2026-11-11',
                              'url': 'https://www.vec.vic.gov.au/voting/2026-state-election/postal-voting',
                              'note': 'Anyone can apply; the online form appears on the VEC page from 9 am Wednesday 4 November. General postal voters need not apply.'},
                   'early': {'open': '2026-11-18', 'close': '2026-11-27', 'hours': '9 am to 6 pm daily except Sunday 22 November; closes 6 pm Friday 27 November',
                             'url': 'https://www.vec.vic.gov.au/voting/2026-state-election/voting-options',
                             'note': 'Every early voting centre is also an election-day voting centre this year. The VEC publishes locations closer to the voting period.'},
                   'low_sensory': {'date': '2026-11-17', 'note': 'one low-sensory mobile voting session per district, 10 am to 4 pm'},
                   'election_day': {'date': '2026-11-28', 'hours': '8 am to 6 pm', 'note': 'vote at any voting centre in Victoria'},
                   'district_page': 'https://www.vec.vic.gov.au/electoral-boundaries/state-districts/{slug}-district',
                   'results_page': 'https://www.vec.vic.gov.au/results/state-election-results/2026-state-election-results',
                   'nominations_note': 'Nominations close 12 noon Monday 9 November; the VEC candidate list replaces the Wikipedia register then.'
               }}, open(f'{out}/meta.json', 'w'), indent=1)
    c = pd.DataFrame(cands)
    print(f'{len(contests)} contests, {len(c)} declared candidates ({(c.contest_id.str.startswith("vic-")).sum()} LA, {(c.contest_id.str.startswith("vicr-")).sum()} LC), {len(retiring)} retiring, {len(wd)} withdrawals')
    print(c[c.contest_id.str.startswith('vic-')].party.value_counts().to_dict())
    la = c[c.contest_id.str.startswith('vic-')]
    print('districts with no declared candidate:', sorted(set(x['contest_id'] for x in contests if x['house'] == 'LA') - set(la.contest_id)))
    print('districts with candidates:', la.contest_id.nunique())


if __name__ == '__main__':
    main(*sys.argv[1:4])
