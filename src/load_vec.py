"""Load VEC Legislative Assembly results scraped from the VEC website into the common schema.

Input: a JSON list (one entry per district) as produced by the browser scraper:
  {name, href, headings, summary, tables: [[rows]], pages: {<slug>: [[rows]]}}
where pages hold the "results by voting centre" (first preferences), "2cp results by
voting centre" and "results distribution" tables as row arrays.

Usage: python3 -m src.load_vec <year> <districts.json> <out_dir>
"""
import sys, os, re, json
import pandas as pd
from .parties import canon_from_name

VOTE_TYPE_ROWS = {
    'absent votes': 'absent', 'early votes': 'early', 'marked as voted votes': 'marked_as_voted',
    'postal votes': 'postal', 'provisional votes': 'provisional', 'all votes votes': 'all_votes',
    'declaration votes': 'provisional',   # the 1999-2006 name for the enrolment-declaration (provisional) votes
}
SKIP_ROWS = {'ordinary votes total', 'total', 'percentage of formal vote polled by candidate', ''}


def _norm(x):
    return re.sub(r'[^a-z]', '', str(x).lower())


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def num(s):
    s = str(s).replace(',', '').strip()
    return int(s) if re.fullmatch(r'-?\d+', s) else None


def parse_summary(text):
    g = lambda pat: (re.search(pat, text) or [None, None])[1]
    return {
        'enrolment': num(g(r'close of rolls:\s*(\d+)')),
        'formal': num(g(r'Formal votes:\s*(\d+)')),
        'informal': num(g(r'Informal votes:\s*(\d+)')),
        'total_votes': num(g(r'Total votes:\s*(\d+)')),
        'elected': g(r'Elected member\s+(.+?)\s+(?:Recheck|Final)'),
    }


def parse_booth_table(rows, cand_index):
    """rows[0] = ['', cand1, cand2, ..., '', ''] ; rows[1] = ['Voting Centres', party1, ..., 'Informal votes', 'Total votes polled']
    Returns (booth_rows, candidate_cols) where booth_rows = list of (label, kind, {cand_name: votes}, informal, total)."""
    names = rows[0][1:]
    hdr2 = [h.lower() for h in rows[1]]
    # candidate columns are those whose row-0 label is non-empty
    cand_cols = [(i + 1, n) for i, n in enumerate(names) if n]
    inf_col = next((i for i, h in enumerate(hdr2) if 'informal' in h), None)
    tot_col = next((i for i, h in enumerate(hdr2) if 'total' in h), None)
    mis_col = next((i for i, h in enumerate(hdr2) if 'mis-sort' in h), None)
    out = []
    for r in rows[2:]:
        if not r or not r[0]:
            continue
        label = r[0].strip()
        key = label.lower()
        if key in SKIP_ROWS:
            continue
        kind = VOTE_TYPE_ROWS.get(key, 'ordinary')
        if kind == 'ordinary' and (re.search(r'\bE Centre$', label) or label == 'Melbourne Airport'):
            kind = 'early_centre'   # 1999-2006: an early voting centre (often another district's, or the airport) listed among the ordinary rows
        if len(r) < len(rows[1]):
            continue
        votes = {n: num(r[i]) for i, n in cand_cols}
        out.append({'label': label, 'kind': kind, 'votes': votes,
                    'informal': num(r[inf_col]) if inf_col is not None else None,
                    'total': num(r[tot_col]) if tot_col is not None else None,
                    'missorts': num(r[mis_col]) if mis_col is not None else None})
    return out


def parse_distribution(rows):
    """Returns list of dicts: count_no, candidate, transfer, progressive_total, excluded_candidate."""
    cands = [c for c in rows[0][1:] if c and c.upper() != 'TOTAL']
    out = []
    count_no = 0
    excluded_at = {}
    # first prefs row
    fp = rows[1]
    for i, c in enumerate(cands):
        out.append({'count_no': 0, 'candidate': c, 'transfer': 0, 'progressive_total': num(fp[i + 1]), 'excluded': 0})
    i = 2
    while i < len(rows):
        r = rows[i]
        m = re.match(r'Transfer of (\d+) ballot[- ]papers of (.+?) \((\d+)(?:st|nd|rd|th) excluded candidate\)', r[0])
        if m:
            count_no += 1
            excl = m.group(2).strip()
            transfers = r
            prog = rows[i + 1] if i + 1 < len(rows) and rows[i + 1][0].lower().startswith(('progressive', 'final')) else None
            for j, c in enumerate(cands):
                t = num(transfers[j + 1]) if j + 1 < len(transfers) else None
                p = num(prog[j + 1]) if prog and j + 1 < len(prog) else None
                if c == excl:
                    t = -int(m.group(1)); p = 0
                if c in excluded_at:
                    continue  # already out
                out.append({'count_no': count_no, 'candidate': c, 'transfer': t or 0, 'progressive_total': p,
                            'excluded': int(c == excl)})
            excluded_at[excl] = count_no
            i += 2 if prog else 1
        else:
            i += 1
    return out


def load(year, src, out):
    eid = f'vic{year}'
    data = json.load(open(src))
    contests, candidates, booths, fp_votes, tcp_votes, dop, tpp = [], [], [], [], [], [], []
    final_pair = []
    for d in data:
        dname = d['name'].replace(' District results', '').strip()
        cid = f'vic-{slug(dname)}'
        s = parse_summary(d['summary'])
        contests.append({'election_id': eid, 'contest_id': cid, 'contest_name': dname, 'house': 'LA', **s})
        # candidates from the district page FP table (ballot order)
        fp_tbl = d['tables'][0]
        cand_ids = {}
        for pos, r in enumerate(fp_tbl[1:], start=1):
            name, party = r[0], r[1]
            cand_id = f'{cid}-{pos}'
            cand_ids[name] = cand_id
            sur, _, given = name.partition(',')
            candidates.append({'election_id': eid, 'contest_id': cid, 'candidate_id': cand_id,
                               'surname': sur.strip().title(), 'given_name': given.strip(),
                               'party_name': party, 'party_ab_src': '', 'party': canon_from_name(party),
                               'ballot_position': pos, 'elected': int(_norm(name) == _norm(s['elected']) or _norm(s['elected'] or '').startswith(_norm(name)))})
        # official "votes after distribution of preferences" table on the district page: the final two
        if len(d['tables']) > 1 and d['tables'][1]:
            for r in d['tables'][1][1:]:
                if len(r) >= 3 and r[0] in cand_ids and num(r[2]) is not None:
                    final_pair.append({'election_id': eid, 'contest_id': cid, 'candidate_id': cand_ids[r[0]], 'votes': num(r[2])})
        # TPP table (if the 2CP wasn't ALP v LIB/NAT the VEC also reports a TPP)
        if 'Two party preferred vote' in d['headings']:
            for t in d['tables']:
                if t and t[0][:1] == ['Candidate'] and 'distribution' not in t[0][2].lower() and 'pref' not in t[0][2].lower():
                    pass
        pages = {k.lower(): v for k, v in d['pages'].items()}
        fp_key = next((k for k in pages if k.endswith('district-results-by-voting-centre')), None)
        tcp_key = next((k for k in pages if k.endswith('2cp-results-by-voting-centre')), None)
        dist_key = next((k for k in pages if k.endswith('results-distribution')), None)
        booth_seen = {}
        def booth_id_for(label, kind):
            if kind in ('ordinary', 'early_centre'):
                bid = f'{cid}-{slug(label)}'
                if bid not in booth_seen:
                    booth_seen[bid] = {'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'booth_name': label,
                                       'booth_type': 'ordinary' if kind == 'ordinary' else 'early', 'premises': '', 'address': '', 'suburb': '', 'postcode': '',
                                       'lat': None, 'lon': None}
            else:
                bid = f'{cid}-{kind}'
                if bid not in booth_seen:
                    booth_seen[bid] = {'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'booth_name': f'{dname} {kind}',
                                       'booth_type': kind, 'premises': '', 'address': '', 'suburb': '', 'postcode': '',
                                       'lat': None, 'lon': None}
            return bid
        if not (fp_key and pages[fp_key]) and fp_tbl:
            # no booth table survives (Ferntree Gully 2006 was never archived): keep the district totals as one 'all_votes' row
            bid = booth_id_for('all votes', 'all_votes')
            for r in fp_tbl[1:]:
                if r[0] in cand_ids and num(r[2]) is not None:
                    fp_votes.append({'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'candidate_id': cand_ids[r[0]], 'votes': num(r[2])})
            if s['informal'] is not None:
                fp_votes.append({'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'candidate_id': 'INFORMAL', 'votes': s['informal']})
        if fp_key and pages[fp_key]:
            for b in parse_booth_table(pages[fp_key][0], cand_ids):
                bid = booth_id_for(b['label'], b['kind'])
                for cname, v in b['votes'].items():
                    if cname in cand_ids and v is not None:
                        fp_votes.append({'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'candidate_id': cand_ids[cname], 'votes': v})
                if b['informal'] is not None:
                    fp_votes.append({'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'candidate_id': 'INFORMAL', 'votes': b['informal']})
        if tcp_key and pages[tcp_key]:
            for b in parse_booth_table(pages[tcp_key][0], cand_ids):
                bid = booth_id_for(b['label'], b['kind'])
                for cname, v in b['votes'].items():
                    if cname in cand_ids and v is not None:
                        tcp_votes.append({'election_id': eid, 'contest_id': cid, 'booth_id': bid, 'candidate_id': cand_ids[cname], 'votes': v})
        if dist_key and pages[dist_key]:
            for r in parse_distribution(pages[dist_key][0]):
                dop.append({'election_id': eid, 'contest_id': cid, 'count_no': r['count_no'],
                            'candidate_id': cand_ids.get(r['candidate'], r['candidate']),
                            'transfer': r['transfer'], 'progressive_total': r['progressive_total'], 'excluded': r['excluded']})
        booths.extend(booth_seen.values())

    os.makedirs(out, exist_ok=True)
    for name, rows in [('contests', contests), ('candidates', candidates), ('booths', booths),
                       ('fp_votes', fp_votes), ('tcp_votes', tcp_votes), ('dop', dop), ('final_pair', final_pair)]:
        df = pd.DataFrame(rows)
        df.to_csv(f'{out}/{name}.csv', index=False)
        print(f'{eid} {name}: {len(df)} rows')


if __name__ == '__main__':
    load(*sys.argv[1:4])


def load_indicative(year, files_dir, out, contests_csv):
    """Parse the VEC 'indicative distribution of preferences' spreadsheets (districts where the
    winner had a majority before the distribution finished) into dop_indicative.csv."""
    import glob
    cands_df = pd.read_csv(f'{out}/candidates.csv')
    eid = f'vic{year}'
    rows = []
    for path in sorted(glob.glob(f'{files_dir}/*_District.xls*')):
        dname = os.path.basename(path).split('_District')[0].replace('_', ' ')
        cid = f'vic-{slug(dname)}'
        sheet = pd.read_excel(path, header=None)
        # find the candidates header row
        hdr_i = next(i for i, v in enumerate(sheet[0]) if str(v).startswith('Candidates Names'))
        sub = sheet.iloc[hdr_i:].dropna(axis=1, how='all')
        table = [[('' if pd.isna(v) else str(v).replace('\n', ' ').replace('  ', ' ').strip()) for v in r] for r in sub.values.tolist()]
        table = [r for r in table if r[0]]
        # numbers come through as floats ("2249.0") -> ints
        table = [[re.sub(r'^(\d+)\.0$', r'\1', c) for c in r] for r in table]
        table[0][0] = ''
        cmap = {}
        for c in cands_df[cands_df.contest_id == cid].itertuples():
            cmap[f'{c.surname.upper()}, {c.given_name}'] = c.candidate_id
        def cid_for(name):
            if name in cmap:
                return cmap[name]
            sur = name.split(',')[0].strip().upper()
            hits = [v for k, v in cmap.items() if k.split(',')[0] == sur]
            return hits[0] if len(hits) == 1 else name
        for r in parse_distribution(table):
            rows.append({'election_id': eid, 'contest_id': cid, 'count_no': r['count_no'],
                         'candidate_id': cid_for(r['candidate']), 'transfer': r['transfer'],
                         'progressive_total': r['progressive_total'], 'excluded': r['excluded']})
    df = pd.DataFrame(rows)
    df.to_csv(f'{out}/dop_indicative.csv', index=False)
    unmapped = df[~df.candidate_id.str.startswith('vic-')]
    print(f'{eid} dop_indicative: {len(df)} rows, {df.contest_id.nunique()} districts, unmapped candidates: {unmapped.candidate_id.unique().tolist()}')


def normalise_2018(rec):
    """Convert a record scraped from the 2018 results site (Wayback) into the 2022 page shape."""
    import re as _re
    tabs = rec['tables']
    elected_raw = tabs[0][0][0] if tabs and tabs[0] and tabs[0][0] else ''
    m = _re.match(r'^(.+?[a-z])([A-Z][A-Z].*)$', elected_raw)  # party is upper case; names end in lower case
    elected = f'{m.group(1)} {m.group(2)}' if m else elected_raw
    enrol = {r[0].lower(): r[1] for r in tabs[1] if len(r) == 2} if len(tabs) > 1 else {}
    g = lambda k: next((v for kk, v in enrol.items() if k in kk), '')
    summary = (f"Elected member {elected} Recheck votes Total enrolment as at close of rolls: {g('enrolment')} "
               f"Formal votes: {g('formal')} Informal votes: {g('informal')} Total votes: {g('total votes')}")
    summary = _re.sub(r'(\d+) \(', r'\1 (', summary)
    fp_tbl = next((t for t in tabs if t and t[0] and t[0][0] == 'Candidate' and 'pref' in ' '.join(t[0]).lower()), [])
    dist_tbl = next((t for t in tabs if t and t[0] and t[0][0] == 'Candidate' and 'distribution' in ' '.join(t[0]).lower()), [])
    pages = {}
    for k, tables in rec['pages'].items():
        big = max(tables, key=lambda t: len(t) * max((len(r) for r in t), default=0)) if tables else []
        pages[k] = [big] if big else []
    return {'href': rec['href'], 'name': rec['name'], 'headings': rec['headings'], 'summary': summary,
            'tables': [fp_tbl, dist_tbl], 'pages': pages, 'sub': list(pages.keys())}
