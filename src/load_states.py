"""Load state election results from other states (the One Nation work and the national expansion).

Each source is read into two common shapes:
  seats         one row per district: election, state, district, candidates (name, party, first preferences), the
                final two-candidate result, the winner, and booth-level first preferences where published
  observations  every exclusion in every distribution of preferences: (election, district, from party, votes to each
                party still standing, the set of parties still standing) - the input of the Luce flow model

Sources (raw/national/<state>/, tools/fetch_states.py):
  qld  ECQ XML archives (2020, 2024 general elections and by-elections)
       ECQ results web pages (2017, 2015: district and booth pages, which include the distribution of preferences)
  wa   WAEC results API JSON (2025, 2021, 2017)
  nsw  NSWEC past results pages (2023, 2019 Legislative Assembly)
  sa   ECSA results API JSON (2026, 2022 and by-elections)

Output data/national/state_results.json ({'seats': [...], 'observations': [...]})
Usage  python3 -m src.load_states
"""
import os, re, json, glob, html, zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from .parties import canon_from_name, canon_from_aec

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'raw/national')
EXTRA_NAMES = [(r'one nation|hanson', 'ONP'), (r'katter', 'KAP'), (r'liberal national', 'LIB'), (r'country liberal', 'LIB'), (r'nationals? wa|wa nationals|national party', 'NAT'),
               (r'legalise cannabis', 'LCP'), (r'family first', 'FFP'), (r'united australia|trumpet of patriots', 'UAP'), (r'sustainable australia', 'SAP'), (r'shooters', 'SFF'),
               (r'animal justice', 'AJP'), (r'libertarian|liberal democrat', 'LDP'), (r'lambie', 'JLN'), (r'fair go|sarah game', 'FGA'), (r'australian family party|aust family', 'AFP'),
               (r'greens', 'GRN'), (r'labor', 'ALP'), (r'^liberal', 'LIB'), (r'independent', 'IND')]
SHORT = {'ALP': 'ALP', 'LNP': 'LIB', 'LIB': 'LIB', 'LIBS': 'LIB', 'NAT': 'NAT', 'NATS': 'NAT', 'NP': 'NAT', 'GRN': 'GRN', 'GRNS': 'GRN', 'PHON': 'ONP', 'ONP': 'ONP', 'ON': 'ONP',
         'IND': 'IND', 'KAP': 'KAP', 'SFF': 'SFF', 'AJP': 'AJP', 'LCWA': 'LCP', 'LCP': 'LCP', 'HMP': 'LCP', 'FFP': 'FFP', 'UAP': 'UAP', 'LDP': 'LDP', 'AC': 'OTH'}


def party_of(name='', code=''):
    c = (code or '').strip().upper()
    if c in SHORT:
        return SHORT[c]
    n = (name or code or '').strip().lower()
    if not n:
        return 'IND'
    for pat, p in EXTRA_NAMES:
        if re.search(pat, n):
            return p
    return canon_from_name(n)


def num(s):
    s = re.sub(r'[^\d\-]', '', str(s or ''))
    return int(s) if s not in ('', '-') else 0


# --------------------------------------------------------------------------- QLD XML (2020, 2024, by-elections)
def qld_xml():
    seats, obs = [], []
    for z in sorted(glob.glob(f'{RAW}/qld/xml/*.zip')):
        root = ET.fromstring(zipfile.ZipFile(z).read('publicResults.xml'))
        for el in root.iter('election'):
            ename = el.get('electionName', '')
            if not re.search(r'State', ename) or 'Council' in ename:
                continue
            year = el.get('electionDay', '')[:4]
            eid = f'qld{year}' if 'General' in ename else 'qldby-' + re.sub(r'[^a-z]+', '-', ename.lower().replace('state by-election', '').replace(year, '')).strip('-') + f'-{year}'
            for d in el.iter('district'):
                dname = d.get('districtName')
                cands = {}
                for c in d.find('candidates') or []:
                    cands[c.get('ballotName')] = {'name': c.get('ballotName'), 'party': party_of(c.get('party', ''), c.get('partyCode', '')), 'party_src': c.get('party', '') or 'Independent'}
                rounds = {int(r.get('round', r.get('id', 0))): r for r in d.findall('countRound')}
                fpr = next((rounds[k] for k in sorted(rounds, reverse=True) if rounds[k].get('preferences') == 'NO' and rounds[k].get('unofficial') == 'NO'), None) or next(iter(rounds.values()), None)
                fp = {c.get('ballotName'): num(c.findtext('count')) for c in (fpr.find('primaryVoteResults') if fpr is not None else [])}
                booths = []
                if fpr is not None and fpr.find('booths') is not None:
                    for b in fpr.find('booths'):
                        booths.append({'booth': b.get('name'), 'type': b.get('typeCode'), 'fp': {c.get('ballotName'): num(c.findtext('count')) for c in b.find('primaryVoteResults') or []}})
                dop = next((rounds[k] for k in sorted(rounds, reverse=True) if rounds[k].get('preferences') == 'YES' and rounds[k].get('indicative') == 'NO'), None)
                tcp = {}
                if dop is not None:
                    tcp = {c.get('ballotName'): num(c.findtext('count')) for c in (dop.find('twoCandidateVotes') or [])}
                    summ = dop.find('preferenceDistributionSummary')
                    if summ is not None:
                        prog = {c.get('ballotName'): num(c.findtext('count')) for c in (summ.find('primaryVotes') or [])}
                        live = set(prog)
                        for pdist in summ.findall('preferenceDistribution'):
                            ex = pdist.get('excludedBallotName'); live.discard(ex)
                            to = defaultdict(int)
                            for cp in pdist.findall('candidatePreferences'):
                                to[cands.get(cp.get('ballotName'), {}).get('party', 'OTH')] += num(cp.findtext('count'))
                            rem = {cands.get(x, {}).get('party', 'OTH') for x in live}
                            if ex in cands and sum(to.values()) > 0:
                                obs.append((eid, 'QLD', dname, cands[ex]['party'], dict(to), sorted(rem)))
                win = d.find('declaredCandidate')
                seats.append({'election_id': eid, 'state': 'QLD', 'district': dname, 'candidates': [dict(cands[k], fp=fp.get(k, 0)) for k in cands],
                              'tcp': {cands[k]['party']: v for k, v in tcp.items() if k in cands}, 'winner': cands.get(win.get('ballotName'), {}).get('party') if win is not None else None,
                              'booths': [{'booth': b['booth'], 'type': b['type'], 'fp': {cands[k]['party']: v for k, v in b['fp'].items() if k in cands}} for b in booths]})
    return seats, obs


# --------------------------------------------------------------------------- QLD HTML (2017, 2015)
def strip(s):
    return html.unescape(re.sub(r'<[^>]+>', ' ', s)).strip()


def rows_of(tbl):
    return [[re.sub(r'\s+', ' ', strip(c)) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S)] for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.S)]


def qld_html():
    seats, obs = [], []
    for year in ('2017', '2015'):
        for f in sorted(glob.glob(f'{RAW}/qld/html/{year}/district*.html'), key=lambda p: int(re.search(r'(\d+)\.html', p).group(1))):
            t = open(f, encoding='utf-8', errors='replace').read()
            m = re.search(r'State General Election\s*-\s*([^<]+?)\s*-\s*District Summary', t)
            if not m:
                continue
            dname = re.sub(r'\s+', ' ', html.unescape(m.group(1))).strip()
            cands = {}
            for r in rows_of(t):              # the pages nest tables, so read rows across the whole page
                if len(r) >= 3 and re.match(r"^[A-Z'\- ]+, ", r[0]) and re.match(r'^[\d,]+$', r[2] or ''):
                    cands.setdefault(r[0], {'name': r[0], 'party': party_of(r[1], r[1]), 'party_src': r[1] or 'IND', 'fp': num(r[2])})
            tcp, booths = {}, []
            bfile = f.replace('district', 'booth')
            if os.path.exists(bfile) and cands:
                b = open(bfile, encoding='utf-8', errors='replace').read()
                o, tcp, booths = qld_html_booth(year, dname, cands, b)
                obs += o
            seats.append({'election_id': f'qld{year}', 'state': 'QLD', 'district': dname, 'candidates': list(cands.values()), 'tcp': tcp,
                          'winner': max(tcp, key=tcp.get) if tcp else None, 'booths': booths})
    return seats, obs


def qld_html_booth(year, dname, cands, page):
    """ECQ 2015/2017 booth page: the booth table (candidates as column pairs) and the 'Summary of Distribution of
    Preferences' (rows 'X Excluded', candidates as (votes, %) column pairs)"""
    def col_cand(h):                      # 'LANYON, Darryl ONP' -> candidate key 'LANYON, Darryl'
        return next((k for k in cands if h.startswith(k)), None)
    obs, tcp, booths = [], {}, []
    cc, mode, live = [], None, []
    for r in rows_of(page):               # nested tables: walk rows across the whole page
        if not r:
            continue
        if r[0] in ('No.', 'Preference Distribution'):
            cc = [k for k in (col_cand(h) for h in r) if k]
            mode = 'booth' if r[0] == 'No.' else 'dop'; live = list(cc)
            continue
        if mode == 'booth' and re.match(r'^\d+$', r[0]) and len(r) >= 2 + 2 * len(cc):
            booths.append({'booth': r[1], 'type': 'ordinary', 'fp': {cands[k]['party']: num(r[2 + 2 * i]) for i, k in enumerate(cc)}})
        elif mode == 'dop':
            vals = {k: num(r[1 + 2 * i]) if 1 + 2 * i < len(r) else 0 for i, k in enumerate(cc)}
            m = re.match(r'^(.*?) Excluded$', r[0])
            if m:
                sur = m.group(1).strip().upper()
                ex = [k for k in live if k.split(',')[0].strip().upper() == sur]
                if len(ex) != 1:
                    continue
                ex = ex[0]; live.remove(ex)
                to = defaultdict(int)
                for k in live:
                    if vals[k] > 0:
                        to[cands[k]['party']] += vals[k]
                if sum(to.values()) > 0:
                    obs.append((f'qld{year}', 'QLD', dname, cands[ex]['party'], dict(to), sorted({cands[k]['party'] for k in live})))
            elif r[0] == 'District Total':
                tcp = {cands[k]['party']: v for k, v in vals.items() if v > 0}
                mode = None
    return obs, tcp, booths


# --------------------------------------------------------------------------- WA JSON (2025, 2021, 2017)
def wa():
    seats, obs = [], []
    for d in sorted(glob.glob(f'{RAW}/wa/sg*')):
        e = os.path.basename(d); year = e[2:]
        for f in sorted(glob.glob(f'{d}/*_results.json')):
            R = json.load(open(f)); code = os.path.basename(f).split('_')[0]
            name = (R.get('currentElectorate') or {}).get('ElectorateName', code)
            cands = {}
            for c in R.get('resultsCandidates') or []:
                key = f"{c['BALLOT_PAPER_NAME']} - {c.get('PARTY_AFFILIATION') or 'IND'}"
                cands[key] = {'name': c['BALLOT_PAPER_NAME'], 'party': party_of(c.get('PARTY_AFFILIATION', ''), c.get('PARTY_AFFILIATION', '')), 'party_src': c.get('PARTY_AFFILIATION') or 'IND', 'fp': num(c.get('Votes_Counted'))}
            # full distribution: rows per (level, candidate): progressive totals; derive exclusions
            byl = defaultdict(dict)
            for r in R.get('resultsFullDistribution') or []:
                byl[int(r['PREFERENCE_LEVEL'])][r['BALLOT_PAPER_NAME']] = num(r.get('FORMAL_LAST_PUBLISHED_NUMBER_ENTERED'))
            lv = sorted(byl)
            for a, b in zip(lv, lv[1:]):
                prev, cur = byl[a], byl[b]
                ex = [k for k in prev if prev[k] > 0 and cur.get(k, 0) == 0]
                if len(ex) != 1 or ex[0] not in cands:
                    continue
                to = defaultdict(int)
                for k, v in cur.items():
                    if k in cands and v - prev.get(k, 0) > 0:
                        to[cands[k]['party']] += v - prev.get(k, 0)
                rem = {cands[k]['party'] for k, v in cur.items() if v > 0 and k in cands}
                if sum(to.values()) > 0:
                    obs.append((f'wa{year}', 'WA', name, cands[ex[0]]['party'], dict(to), sorted(rem)))
            tcp = {}
            for c in R.get('results2CP') or []:
                k = c['Ballot_Paper_Name']; tcp[cands[k]['party'] if k in cands else party_of(k.split(' - ')[-1], k.split(' - ')[-1])] = num(c['Votes_Counted'])
            booths = []
            for b in R.get('resultsPollingPlace') or []:
                booths.append({'booth': b.get('BREAKDOWN_NAME'), 'type': b.get('BREAKDOWN_GROUP'), 'fp': {cands[k]['party']: num(v) for k, v in b.items() if k in cands}})
            seats.append({'election_id': f'wa{year}', 'state': 'WA', 'district': name, 'candidates': list(cands.values()), 'tcp': tcp,
                          'winner': max(tcp, key=tcp.get) if tcp else None, 'booths': booths})
    return seats, obs


# --------------------------------------------------------------------------- NSW HTML (2023, 2019)
NSW_CODES = {'LAB': 'ALP', 'CLP': 'ALP',          # NSW 'CLP' is Country Labor, not the Country Liberals
             'ON': 'ONP', 'PHON': 'ONP', 'CDP': 'CDP', 'AC': 'OTH', 'KSO': 'OTH', 'IMOP': 'OTH', 'PEP': 'OTH', 'SBP': 'OTH', 'SA': 'OTH', 'FLUX': 'OTH'}


def nsw():
    """NSWEC past results, Legislative Assembly distribution of preferences page per district: one row per candidate
    ('SURNAME Given CODE'), column 1 first preferences, then (votes distributed, progressive total) per count; the
    excluded candidate shows 'EXCLUDED' in the distributed column of the count that distributes their votes"""
    seats, obs = [], []
    for d in sorted(glob.glob(f'{RAW}/nsw/SG*')):
        e = os.path.basename(d); year = '20' + e[2:4]
        for f in sorted(glob.glob(f'{d}/*_dop.html')):
            slug = os.path.basename(f)[:-9]
            t = open(f, encoding='utf-8', errors='replace').read()
            R = rows_of(t)
            try:
                i0 = next(i for i, r in enumerate(R) if r and r[0] == 'Candidates')
                i1 = next(i for i, r in enumerate(R) if r and r[0].startswith('Total Votes in Count'))
            except StopIteration:
                continue
            crow = [r for r in R[i0 + 1:i1] if r and r[0]]
            cands = {}
            for r in crow:
                toks = r[0].split()
                code = toks[-1] if len(toks) > 2 and re.fullmatch(r'[A-Z]{2,6}', toks[-1]) else ''
                cands[r[0]] = {'name': ' '.join(toks[:-1]) if code else r[0], 'party': NSW_CODES.get(code) or (party_of(code, code) if code else 'IND'), 'party_src': code or 'IND', 'fp': num(r[1])}
            ncol = max(len(r) for r in crow)
            live = set(cands)
            for k in range(2, ncol, 2):
                ex = [r[0] for r in crow if r[0] in live and k < len(r) and 'EXCLUDED' in r[k].upper()]
                if len(ex) != 1:
                    continue
                ex = ex[0]; live.discard(ex)
                to = defaultdict(int)
                for r in crow:
                    if r[0] in live and k < len(r) and 'EXCLUDED' not in r[k].upper():
                        v = num(r[k])
                        if v > 0:
                            to[cands[r[0]]['party']] += v
                if sum(to.values()) > 0:
                    obs.append((f'nsw{year}', 'NSW', slug, cands[ex]['party'], dict(to), sorted({cands[n]['party'] for n in live})))
            # final progressive totals of those still standing (the last column with a number)
            tcp = {}
            if len(live) == 2:
                for r in crow:
                    if r[0] in live:
                        v = next((num(x) for x in reversed(r[1:]) if re.search(r'\d', x or '')), 0)
                        tcp[cands[r[0]]['party']] = tcp.get(cands[r[0]]['party'], 0) + v
            dn = re.search(r'<title>([^<]*)</title>', t)
            seats.append({'election_id': f'nsw{year}', 'state': 'NSW', 'district': slug.replace('-', ' ').title(), 'candidates': list(cands.values()), 'tcp': tcp,
                          'winner': max(tcp, key=tcp.get) if tcp else next((cands[r[0]]['party'] for r in crow if 'ELECTED' in ' '.join(r[1:2])), None), 'booths': []})
    return seats, obs


# --------------------------------------------------------------------------- SA JSON (2026, 2022, by-elections)
def sa():
    """ECSA results API: HAStatic (districts, candidates, parties) and HAChange (votes by polling place, declaration and
    absent batches, and - for 2026 only - the full distribution of preferences). The distribution uses global
    candidate ids and 'Given SURNAME' names, matched to the district's candidates by name."""
    seats, obs = [], []
    for d in sorted(glob.glob(f'{RAW}/sa/20*')):
        date = os.path.basename(d)
        if not os.path.exists(f'{d}/HAStatic.json') or not os.path.exists(f'{d}/HAChange.json'):
            continue
        S = json.load(open(f'{d}/HAStatic.json')); C = json.load(open(f'{d}/HAChange.json'))
        general = 'General' in (S.get('electionType') or '')
        sc = {di['districtName']: {c['candidateId']: c for c in di['candidates']} for di in S['districts']}
        for di in C['districts']:
            dname = di['districtId']; meta = sc.get(dname, {})
            eid = f'sa{date[:4]}' if general else f'saby-{dname.lower().replace(" ", "-")}-{date[:4]}'
            fp, tc = defaultdict(int), defaultdict(int)
            for p in di.get('pollingPlaces') or []:
                for x in p.get('pollingCandidates') or []:
                    fp[x['candidateId']] += num(x.get('formalVotes')); tc[x['candidateId']] += num(x.get('twoCandidatePref'))
            for key, tkey in (('declarations', 'twoCandidatePrefVoteCount'), ('absentOrdinary', 'twoCandidatePrefVotes')):
                for p in di.get(key) or []:
                    for x in p.get('candidateVotes') or []:
                        fp[x['candidateId']] += num(x.get('votes')); tc[x['candidateId']] += num(x.get(tkey))
            cands = {}
            for cid, m in meta.items():
                nm = m.get('candidateName', str(cid))
                cands[cid] = {'name': nm, 'party': party_of(m.get('partyName', ''), m.get('partyId', '')), 'party_src': m.get('partyName') or 'Independent', 'fp': fp.get(cid, 0)}
            def key_of(given_sur):                      # 'Dan CASEY' -> local id of 'CASEY, Dan'
                t = given_sur.split()
                sur = ' '.join(w for w in t if w.isupper() and len(w) > 1) or (t[-1] if t else '')
                hits = [cid for cid, c in cands.items() if c['name'].split(',')[0].strip().upper() == sur.upper()]
                if len(hits) > 1:
                    hits = [cid for cid in hits if t and t[0].lower() in cands[cid]['name'].lower()]
                return hits[0] if len(hits) == 1 else None
            rounds = sorted(di.get('finalDistribution') or [], key=lambda r: r.get('roundNumber', 0))
            live = set(cands)
            for r in rounds:
                res = {key_of(cr.get('candidateName', '')): cr for cr in r.get('candidateResults') or []}
                if r.get('roundNumber') == 0:
                    for cid, cr in res.items():
                        if cid in cands:
                            cands[cid]['fp'] = num(cr.get('progressiveTotal'))
                    continue
                ex = key_of(r.get('excludedCandidateName') or '')
                if ex is None or ex not in live:
                    continue
                live.discard(ex)
                to = defaultdict(int)
                for cid, cr in res.items():
                    if cid in live and num(cr.get('voteChange')) > 0:
                        to[cands[cid]['party']] += num(cr.get('voteChange'))
                if sum(to.values()) > 0:
                    obs.append((eid, 'SA', dname, cands[ex]['party'], dict(to), sorted({cands[x]['party'] for x in live})))
            tcp = {cands[cid]['party']: v for cid, v in tc.items() if v and cid in cands}
            booths = [{'booth': p.get('pollingPlaceName'), 'type': p.get('pollingPlaceTypeIdName'), 'fp': {cands[x['candidateId']]['party']: num(x.get('formalVotes')) for x in p.get('pollingCandidates') or [] if x.get('candidateId') in cands}} for p in di.get('pollingPlaces') or []]
            seats.append({'election_id': eid, 'state': 'SA', 'district': dname, 'candidates': list(cands.values()), 'tcp': tcp, 'winner': max(tcp, key=tcp.get) if tcp else None, 'booths': booths})
    return seats, obs


def main():
    seats, obs = [], []
    for name, fn in (('qld xml', qld_xml), ('qld html', qld_html), ('wa', wa), ('nsw', nsw), ('sa', sa)):
        try:
            s, o = fn()
        except Exception as ex:
            print(f'{name}: failed {ex!r}'); continue
        seats += s; obs += o
        by = defaultdict(lambda: [0, 0, 0])
        for x in s:
            by[x['election_id']][0] += 1
            by[x['election_id']][2] += any(c['party'] == 'ONP' for c in x['candidates'])
        for x in o:
            by[x[0]][1] += 1
        print(f'{name}: ' + ', '.join(f'{e}: {a} seats, {b} exclusions, One Nation in {c}' for e, (a, b, c) in sorted(by.items())))
    os.makedirs(os.path.join(ROOT, 'data/national'), exist_ok=True)
    json.dump({'seats': seats, 'observations': obs}, open(os.path.join(ROOT, 'data/national/state_results.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
