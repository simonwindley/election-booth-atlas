"""Opinion polls for the 2026 Victorian state election, from Wikipedia's compilation page captured as expanded
table grids (raw/polls/wikipedia_vic2026_polls.json, written by the browser capture) into site/data/polls_vic2026.json.

Usage: python3 -m src.load_polls [raw.json] [out.json]
"""
import sys, re, json, datetime as dt

MONTHS = {m: i + 1 for i, m in enumerate(['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
PARTY = {'ALP': 'ALP', 'L/NP': 'COAL', 'LIB': 'LIB', 'NAT': 'NAT', 'GRN': 'GRN', 'ONP': 'ONP', 'IND': 'IND', 'Others': 'OTH', 'OTH': 'OTH',
         'LCV': 'LCP', 'DLP': 'DLP', 'LBT': 'LDP', 'SFF': 'SFF', 'FFP': 'FFP', 'AJP': 'AJP', 'VS': 'VSP', 'UND': 'UND'}


def clean(s):
    s = re.sub(r'\.mw-parser-output[^}]*}', '', s or '')
    return s.replace('—N/a', '').replace('N/a', '').replace('\xa0', ' ').strip()


def num(s):
    s = clean(s).replace('%', '').replace(',', '').replace('~', '').replace('−', '-').strip()
    if s in ('', '—', '-', '<', '^'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(label, default_year):
    """'26–29 Oct', '24 Nov – 8 Dec 2025', 'Dec 2024 – Jan 2025', '12–16 Jan& 8–14 Feb', 'July 2026', 'Mar – Apr' -> (start, end) ISO."""
    s = clean(label).replace('&', ' & ').replace('–', '-').replace('—', '-')
    years = [int(y) for y in re.findall(r'(20\d\d)', s)]
    year = years[-1] if years else default_year
    parts = re.findall(r'(\d{1,2})?\s*([A-Za-z]{3,9})\.?\s*(20\d\d)?', s)
    pts = []
    for d, m, y in parts:
        mk = m[:3].lower()
        if mk not in MONTHS:
            continue
        pts.append((int(y) if y else None, MONTHS[mk], int(d) if d else None))
    if not pts:
        return None, None
    # fill years backwards from the last known
    yy = year
    for i in range(len(pts) - 1, -1, -1):
        y, m, d = pts[i]
        if y:
            yy = y
        pts[i] = (yy, m, d)
    # a leading bare day range '26-29 Oct' -> start day 26 of the same month
    first_m = re.match(r'\s*(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]{3,9})', s)
    y0, m0, d0 = pts[0]
    if first_m:
        d_start = int(first_m.group(1))
    else:
        d_start = d0 or 1
    y1, m1, d1 = pts[-1]
    import calendar
    d_end = d1 or calendar.monthrange(y1, m1)[1]
    try:
        start = dt.date(y0, m0, min(d_start, calendar.monthrange(y0, m0)[1]))
        end = dt.date(y1, m1, min(d_end, calendar.monthrange(y1, m1)[1]))
    except ValueError:
        return None, None
    if end < start:
        start = end
    return start.isoformat(), end.isoformat()


def header_map(grid):
    """Column -> (group, name) from the first header rows, e.g. (primary, ALP), (tpp, L/NP)."""
    top, names = grid[0], grid[1]
    groups, cur = [], None
    for c in top:
        if c not in ('<', '^'):
            cur = c
        groups.append(cur)
    out = {}
    for i, n in enumerate(names):
        g = (groups[i] or '').lower()
        nm = clean(n)
        if nm in ('^', '<', ''):
            continue
        key = 'primary' if 'primary' in g or '3pp' in g or 'seat' in g else 'tpp' if '2pp' in g else 'leader' if 'leader' in g else g.replace(' ', '_')
        out[i] = (key, nm)
    return out


def parse_poll_table(grid, default_year, nrows_header):
    cols = header_map(grid)
    rows, events, last = [], [], None
    for r in grid[nrows_header:]:
        if not r:
            continue
        date, firm = clean(r[0]), clean(r[1]) if len(r) > 1 else ''
        if date == '^' or date == '':
            # continuation: alternative two-party figures for the poll above
            if last is not None:
                alt = {}
                for i, (g, nm) in cols.items():
                    if g == 'tpp' and i < len(r) and num(r[i]) is not None:
                        alt[PARTY.get(nm, nm)] = num(r[i])
                if len(alt) >= 2:
                    last.setdefault('alt_tpp', []).append(alt)
            continue
        values = [c for c in r[2:] if c not in ('<', '^')]
        if len(r) > 2 and all(c == '<' for c in r[2:]) and firm:
            s, e = parse_date(date, default_year)
            events.append({'date': e, 'text': firm})
            continue
        s, e = parse_date(date, default_year)
        rec = {'date': e, 'start': s, 'label': date, 'firm': firm, 'client': clean(r[2]) if len(r) > 2 and r[2] not in ('<', '^') else '',
               'n': num(r[3]) if len(r) > 3 else None, 'primary': {}, 'tpp': {}}
        if re.search(r'^\d{4} election$|^election$', firm, re.I):
            rec['election'] = True
        for i, (g, nm) in cols.items():
            if i >= len(r):
                continue
            v = num(r[i])
            if g in ('primary', 'tpp'):
                k = PARTY.get(nm, nm)
                if r[i] == '<':
                    continue
                if v is None:
                    continue
                rec[g][k] = v
            elif g == 'leader':
                rec.setdefault('leaders', {})[nm] = v
            else:
                rec.setdefault(g, {})[nm] = v if v is not None else clean(r[i])
        # a primary cell spanning IND+Others means the two were reported together
        if 'primary' in rec and 'IND' in rec['primary'] and 'OTH' not in rec['primary']:
            idx_ind = [i for i, (g, nm) in cols.items() if g == 'primary' and nm == 'IND']
            if idx_ind and idx_ind[0] + 1 < len(r) and r[idx_ind[0] + 1] == '<':
                rec['primary']['OTH'] = rec['primary'].pop('IND'); rec['ind_in_others'] = True
        rows.append(rec); last = rec
    return rows, events


def main(raw='raw/polls/wikipedia_vic2026_polls.json', out='site/data/polls_vic2026.json'):
    obj = json.load(open(raw))
    T = obj['tables']
    sec = lambda t: t['sec'][-1]
    polls, events = [], []
    # Legislative Assembly voting intention: one table per year
    for t in T:
        if t['sec'][0] in ('Voting intention', 'Legislative Assembly', '2026', '2025') and re.fullmatch(r'20\d\d', sec(t)):
            rows, ev = parse_poll_table(t['grid'], int(sec(t)), 3)
            polls += rows; events += ev
    seen = set(); uniq = []; have_election = False
    for p in polls:
        if p.get('election'):   # the 2022 result row repeats under every year's table; keep the first (fullest) one
            if have_election:
                continue
            have_election = True
        k = (p['date'], p['firm'], json.dumps(p['primary'], sort_keys=True))
        if k in seen:
            continue
        seen.add(k); uniq.append(p)
    polls = sorted(uniq, key=lambda p: p['date'] or '')
    out_obj = {'meta': {'source': 'Wikipedia, Opinion polling for the 2026 Victorian state election', 'url': obj['meta']['url'], 'retrieved': obj['meta']['retrieved'][:10],
                        'page_last_edited': clean(obj['meta'].get('last_edited', '')).replace('This page was last edited on ', '')},
               'polls': polls, 'events': sorted({(e['date'], e['text']) for e in events if e['date']}), 'tpp3': [], 'lc': [], 'substate': {}, 'mrp': {}, 'leaders': {'preferred': {}, 'approval': {}}, 'subpop': {}, 'seat': {}}
    out_obj['events'] = [{'date': d, 'text': t} for d, t in out_obj['events']]
    for t in T:
        name, g = sec(t), t['grid']
        top = t['sec']
        if name == 'Three-party-preferred vote':
            out_obj['tpp3'], _ = parse_poll_table(g, 2026, 2)
        elif name == 'Legislative Council' and 'Voting intention' in top:
            out_obj['lc'], _ = parse_poll_table(g, 2026, 3)
        elif 'Sub-state results' in top or name in ('Outer Melbourne', 'Melbourne', 'Provincial', 'Rural', 'Regional/Rural', 'Inner Melbourne'):
            out_obj['substate'][name], _ = parse_poll_table(g, 2026, 3)
        elif 'Electorate projections (MRP)' in top:
            rows = []
            for r in g[4:]:
                if not r or r[0] in ('^', ''):
                    continue
                vals = [num(c) for c in r[5:-1]]
                names = ['ALP', 'LIB', 'NAT', 'GRN', 'ONP', 'IND'] if name == 'Legislative Assembly' else ['ALP', 'LIB', 'NAT', 'GRN', 'ONP', 'OTH', 'UND']
                tally = {}
                for i, nm in enumerate(names):
                    if i < len(vals) and vals[i] is not None:
                        tally[nm] = int(vals[i])
                if r[7] == '<':   # Roy Morgan gives L/NP as one figure
                    tally = {'ALP': num(r[5]), 'COAL': num(r[6]), 'GRN': num(r[8]), 'ONP': num(r[9])}
                    tally.update({'IND': num(r[10])} if name == 'Legislative Assembly' else {'OTH': num(r[10]), 'UND': num(r[11])})
                    tally = {k: int(v) for k, v in tally.items() if v is not None}
                s, e = parse_date(r[0], 2026)
                rows.append({'date': e, 'start': s, 'label': clean(r[0]), 'firm': clean(r[1]), 'client': clean(r[2]).replace('<', '').replace('N/A', ''), 'type': clean(r[3]).replace('<', ''), 'n': num(r[4]), 'tally': tally, 'majority': clean(r[-1]), 'election': bool(re.search('election', r[1], re.I))})
            out_obj['mrp']['la' if name == 'Legislative Assembly' else 'lc'] = rows
        elif 'Party leaders' in g[0]:
            rows, _ = parse_poll_table(g, 2026, 3)
            out_obj['leaders']['preferred'][name] = rows
        elif len(g) > 2 and 'Pos.' in g[2]:
            # columns: leader -> Pos/Neg/DK/Net
            top_row, names = g[0], g[2]
            groups, cur = [], None
            for c in top_row:
                if c not in ('<', '^'):
                    cur = clean(c)
                groups.append(cur)
            rows = []
            for r in g[3:]:
                if not r or r[0] in ('^', '') or (len(r) > 2 and all(c == '<' for c in r[2:])):
                    continue
                s, e = parse_date(r[0], 2026)
                rec = {'date': e, 'label': clean(r[0]), 'firm': clean(r[1]), 'client': clean(r[2]), 'n': num(r[3]), 'leaders': {}}
                for i in range(4, len(r)):
                    if groups[i] in ('Date', 'Polling firm', 'Client', 'Samplesize', None):
                        continue
                    rec['leaders'].setdefault(groups[i], {})[clean(names[i]).replace('.', '')] = num(r[i])
                rows.append(rec)
            out_obj['leaders']['approval'][name] = rows
        elif 'Subpopulation results' in top or name in ('Women', 'Men', '18–34', '35–54', '55–64', '65+', 'Generation Z', 'Millennials', 'Generation X', 'Baby boomers', 'Only English spoken at home', 'Other language spoken at home'):
            out_obj['subpop'][name], _ = parse_poll_table(g, 2026, 3)
        elif 'Individual seat polling' in top:
            out_obj['seat'][name], _ = parse_poll_table(g, 2026, 3)
    import os
    win = os.path.join(os.path.dirname(raw), 'roymorgan', 'onp_winnability_2026-10.json')
    if os.path.exists(win):
        out_obj['winnability'] = json.load(open(win))
    json.dump(out_obj, open(out, 'w'), separators=(',', ':'))
    print(f"{len(polls)} statewide polls {polls[0]['date']} .. {polls[-1]['date']}; events {len(out_obj['events'])}; 3PP {len(out_obj['tpp3'])}; LC {len(out_obj['lc'])}; "
          f"sub-state {list(out_obj['substate'])}; MRP la {len(out_obj['mrp'].get('la', []))} lc {len(out_obj['mrp'].get('lc', []))}; leaders {list(out_obj['leaders']['preferred'])} / {list(out_obj['leaders']['approval'])}; subpop {list(out_obj['subpop'])}; seat {list(out_obj['seat'])}")
    return out_obj


if __name__ == '__main__':
    main(*sys.argv[1:3])
