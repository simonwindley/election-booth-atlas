#!/usr/bin/env python3
"""Poll the VEC's state election result pages and write a compact live feed for the Booth Atlas.

Standard library only (urllib, html.parser, json, gzip) so it runs on a stock macOS python3.

What it fetches, per cycle:
  <base>                                   the election's results index -> list of district pages
  <base>/results-by-district/<d>-district-results
      summary (enrolment, formal, informal, total, elected member), first preferences by candidate,
      "votes after distribution of preferences" (the final two) when published
  .../<d>-district-results-by-voting-centre     first preferences by voting centre (+ early/postal/absent rows)
  .../<d>-2cp-results-by-voting-centre          two-candidate-preferred by voting centre
  .../<d>-results-distribution                  full distribution of preferences (after the count)
  (the three sub-pages are only fetched when the district page links to them)

What it writes (into --out, default site/data/live):
  latest.json           the whole picture now, with per-booth and per-district `updated_at`
                        stamps so the site can outline what changed since you last looked
  changes.json          a rolling log of what changed when (most recent first, capped)
  snapshots/<ts>.json.gz  every cycle's latest.json, for replaying the night afterwards
  status.json           last cycle's timings, fetch counts and errors

Usage:
  python3 live/vec_live.py --base https://www.vec.vic.gov.au/results/state-election-results/2026-state-election-results
  python3 live/vec_live.py --loop 300            # re-poll every 5 minutes (after the previous cycle finishes)
  python3 live/vec_live.py --districts richmond,dandenong --once
  python3 live/vec_live.py --fixtures raw/vec/fixtures/2022_pages.json --election-id vic2022   # offline test
"""
import argparse, datetime, gzip, hashlib, html, importlib.util, json, os, re, sys, time
import urllib.request, urllib.error
from html.parser import HTMLParser

DEFAULT_BASE = 'https://www.vec.vic.gov.au/results/state-election-results/2026-state-election-results'
UA = 'BoothAtlas live poller (personal research; contact via GitHub) python-urllib'
VOTE_TYPE_ROWS = {
    'absent votes': 'absent', 'early votes': 'early', 'marked as voted votes': 'marked_as_voted',
    'postal votes': 'postal', 'provisional votes': 'provisional', 'all votes votes': 'all_votes',
    'early declaration votes': 'early_declaration', 'hospital votes': 'hospital',
}
SKIP_ROWS = {'ordinary votes total', 'total', 'percentage of formal vote polled by candidate', '', '\xa0'}


# ---------------------------------------------------------------- party codes (shared with src/parties.py when present)
def _load_canon():
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, '..', 'src', 'parties.py')
    if os.path.exists(p):
        spec = importlib.util.spec_from_file_location('parties', p)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.canon_from_name
    rules = [('one nation', 'ONP'), ('socialist', 'VSP'), ('green', 'GRN'), ('labor', 'ALP'), ('liberal democrat', 'LDP'),
             ('libertarian', 'LDP'), ('liberal', 'LIB'), ('national', 'NAT'), ('animal justice', 'AJP'), ('family first', 'FFP'),
             ('legalise cannabis', 'LCP'), ('shooters', 'SFF'), ('democratic labour', 'DLP'), ('reason', 'FRP'), ('freedom', 'FRP'),
             ('sustainable', 'SAP'), ('victorians party', 'AVP'), ('independent', 'IND')]
    def canon(name):
        n = (name or '').lower().strip()
        if not n:
            return 'IND'
        for k, v in rules:
            if k in n:
                return v
        return 'OTH'
    return canon

canon_from_name = _load_canon()


# ---------------------------------------------------------------- HTML helpers
class TableParser(HTMLParser):
    """Collects every <table> as a list of rows, each row a list of cell texts (entities decoded, whitespace collapsed).
    Also collects h1/h2/h3 headings and the text of the main content for the summary regexes."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.headings, self.links = [], [], []
        self._row = self._cell = None
        self._table = None
        self._heading = None
        self._text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style', 'nav', 'footer'):
            self._skip += 1
        if tag == 'table':
            self._table = []
        elif tag == 'tr' and self._table is not None:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
        elif tag in ('h1', 'h2', 'h3'):
            self._heading = []
        elif tag == 'a' and a.get('href'):
            self.links.append((a.get('id') or '', a['href']))
        elif tag == 'br' and self._cell is not None:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer'):
            self._skip = max(0, self._skip - 1)
        if tag in ('td', 'th') and self._cell is not None:
            self._row.append(re.sub(r'\s+', ' ', ''.join(self._cell)).strip())
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag == 'table' and self._table is not None:
            self.tables.append(self._table); self._table = None
        elif tag in ('h1', 'h2', 'h3') and self._heading is not None:
            self.headings.append(re.sub(r'\s+', ' ', ''.join(self._heading)).strip()); self._heading = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
        if self._heading is not None:
            self._heading.append(data)
        self._text.append(data)

    @property
    def text(self):
        return re.sub(r'[ \t\r\f\v]+', ' ', re.sub(r'\s*\n\s*', '\n', ''.join(self._text)))


def parse_html(doc):
    p = TableParser(); p.feed(doc); p.close()
    return p


def num(s):
    s = str(s).replace(',', '').strip()
    return int(s) if re.fullmatch(r'-?\d+', s) else None


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


# ---------------------------------------------------------------- fetching
class Fetcher:
    def __init__(self, base, delay=0.8, fixtures=None, log=print):
        self.base = base.rstrip('/')
        self.host = re.match(r'https?://[^/]+', self.base).group(0)
        self.delay, self.log = delay, log
        self.fixtures = None
        if fixtures:
            self.fixtures = json.load(open(fixtures))
        self.n_fetch = self.n_err = 0
        self.errors = []

    def url(self, path):
        return path if path.startswith('http') else self.host + path

    def get(self, path):
        """Return the page HTML, or None if it could not be fetched (errors are logged, not raised)."""
        if self.fixtures is not None:
            key = path.replace(self.host, '')
            return self.fixtures.get(key) or self.fixtures.get(key.rstrip('/'))
        url = self.url(path)
        for attempt, wait in enumerate([0, 5, 15, 40]):
            if wait:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html'})
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = r.read()
                    if r.headers.get('Content-Encoding') == 'gzip':
                        data = gzip.decompress(data)
                    self.n_fetch += 1
                    time.sleep(self.delay)
                    return data.decode('utf-8', 'replace')
            except urllib.error.HTTPError as e:
                self.log(f'  HTTP {e.code} {url} (attempt {attempt + 1})')
                if e.code == 404:
                    break
            except Exception as e:  # noqa
                self.log(f'  {type(e).__name__}: {e} {url} (attempt {attempt + 1})')
        self.n_err += 1
        self.errors.append(url)
        return None


# ---------------------------------------------------------------- page parsers
def district_links(index_html):
    """[(slug, path)] for every district on the results index."""
    out = {}
    for m in re.finditer(r'href="([^"]*?/results-by-district/([a-z0-9-]+?)-district-results)/?"', index_html):
        out.setdefault(m.group(2), m.group(1))
    return sorted(out.items())


def parse_summary(p):
    t = p.text
    g = lambda pat: (re.search(pat, t, re.I) or [None, None])[1]
    elected = None
    m = re.search(r'Elected member\s*\n?\s*(.+?)\s*\n', t)
    if m and not re.match(r'(recheck|election night|first pref|preliminary|total)', m.group(1), re.I):
        elected = m.group(1).strip()
    return {
        'enrolment': num(g(r'close of rolls?:\s*([\d,]+)')),
        'formal': num(g(r'Formal votes:\s*([\d,]+)')),
        'informal': num(g(r'Informal votes:\s*([\d,]+)')),
        'total_votes': num(g(r'Total votes:\s*([\d,]+)')),
        'elected': elected,
        'stage': next((h for h in p.headings if re.search(r'first preference', h, re.I)), None),
    }


def parse_candidate_table(tables):
    """The district page's first-preference table: Candidate | Party | 1st pref. votes | % votes."""
    for t in tables:
        if t and len(t[0]) >= 3 and t[0][0].lower().startswith('candidate') and 'pref' in t[0][2].lower():
            return [{'name': r[0], 'party_name': r[1], 'votes': num(r[2]), 'pct': r[3] if len(r) > 3 else ''} for r in t[1:] if len(r) >= 3 and r[0]]
    return []


def parse_final_table(tables):
    """'Results after distribution of preferences' table: Candidate | Party | Votes after distribution | % votes."""
    for t in tables:
        if t and len(t[0]) >= 3 and t[0][0].lower().startswith('candidate') and 'distribution' in t[0][2].lower():
            return [{'name': r[0], 'party_name': r[1], 'votes': num(r[2]), 'pct': r[3] if len(r) > 3 else ''} for r in t[1:] if len(r) >= 3 and r[0]]
    return []


def parse_tcp_table(tables):
    """District-page 'Two candidate preferred vote' table: Candidate | Party | Preferred votes | %. (The two-party table has Party first.)"""
    for t in tables:
        if t and len(t[0]) >= 3 and t[0][0].lower().startswith('candidate') and 'preferred' in t[0][2].lower():
            return [{'name': r[0], 'party_name': r[1], 'votes': num(r[2]), 'pct': r[3] if len(r) > 3 else ''} for r in t[1:] if len(r) >= 3 and r[0]]
    return []


def parse_tpp_table(tables):
    for t in tables:
        if t and len(t[0]) >= 3 and t[0][0].lower().startswith('party') and 'preferred' in t[0][2].lower():
            return [{'party_name': r[0], 'name': r[1], 'votes': num(r[2]), 'pct': r[3] if len(r) > 3 else ''} for r in t[1:] if len(r) >= 3 and r[0]]
    return []


def parse_booth_table(rows):
    """rows[0] = ['', cand1, ..., '', ''] ; rows[1] = ['Voting Centres', party1, ..., 'Informal votes', 'Total votes polled']"""
    if len(rows) < 2:
        return [], []
    names = rows[0][1:]
    hdr2 = [h.lower() for h in rows[1]]
    cand_cols = [(i + 1, n) for i, n in enumerate(names) if n]
    inf_col = next((i for i, h in enumerate(hdr2) if 'informal' in h), None)
    tot_col = next((i for i, h in enumerate(hdr2) if 'total' in h), None)
    out = []
    for r in rows[2:]:
        if not r or not r[0] or r[0].lower() in SKIP_ROWS:
            continue
        if len(r) < len(rows[1]):
            continue
        label = r[0].strip()
        kind = VOTE_TYPE_ROWS.get(label.lower(), 'ordinary')
        out.append({'label': label, 'kind': kind, 'votes': {n: num(r[i]) for i, n in cand_cols},
                    'informal': num(r[inf_col]) if inf_col is not None else None,
                    'total': num(r[tot_col]) if tot_col is not None else None})
    return out, [n for _, n in cand_cols]


def parse_distribution(rows):
    if len(rows) < 2:
        return []
    cands = [c for c in rows[0][1:] if c and c.upper() != 'TOTAL']
    out, count_no, excluded = [], 0, set()
    for i, c in enumerate(cands):
        out.append({'count_no': 0, 'candidate': c, 'transfer': 0, 'progressive_total': num(rows[1][i + 1]) if i + 1 < len(rows[1]) else None, 'excluded': 0})
    i = 2
    while i < len(rows):
        r = rows[i]
        m = re.match(r'Transfer of ([\d,]+) ballot papers of (.+?) \((\d+)(?:st|nd|rd|th) excluded candidate\)', r[0]) if r else None
        if m:
            count_no += 1
            excl = m.group(2).strip()
            prog = rows[i + 1] if i + 1 < len(rows) and rows[i + 1] and rows[i + 1][0].lower().startswith(('progressive', 'final')) else None
            for j, c in enumerate(cands):
                if c in excluded:
                    continue
                t = num(r[j + 1]) if j + 1 < len(r) else None
                pt = num(prog[j + 1]) if prog and j + 1 < len(prog) else None
                if c == excl:
                    t, pt = -num(m.group(1)), 0
                out.append({'count_no': count_no, 'candidate': c, 'transfer': t or 0, 'progressive_total': pt, 'excluded': int(c == excl)})
            excluded.add(excl)
            i += 2 if prog else 1
        else:
            i += 1
    return out


# ---------------------------------------------------------------- one district
def scrape_district(f, dslug, path, election_id, log=print):
    cid = f'vic-{dslug}'
    doc = f.get(path)
    if doc is None:
        return None
    p = parse_html(doc)
    title = next((h for h in p.headings if 'district' in h.lower()), dslug)
    dname = re.sub(r'\s+District.*$', '', title, flags=re.I).strip() or dslug.replace('-', ' ').title()
    summary = parse_summary(p)
    cands = parse_candidate_table(p.tables)
    cand_ids, out_c = {}, []
    for pos, c in enumerate(cands, start=1):
        cand_id = f'{cid}-{pos}'
        cand_ids[c['name']] = cand_id
        sur, _, given = c['name'].partition(',')
        out_c.append({'candidate_id': cand_id, 'name': c['name'], 'surname': sur.strip().title(), 'given_name': given.strip(),
                      'party_name': c['party_name'], 'party': canon_from_name(c['party_name']), 'ballot_position': pos,
                      'fp_votes': c['votes'], 'pct': c['pct'],
                      'elected': int(bool(summary['elected']) and _norm(summary['elected']).startswith(_norm(c['name'])))})
    final = [{'candidate_id': cand_ids.get(r['name'], r['name']), 'votes': r['votes'], 'pct': r['pct']} for r in parse_final_table(p.tables)]
    tcp_total = [{'candidate_id': cand_ids.get(r['name'], r['name']), 'votes': r['votes'], 'pct': r['pct']} for r in parse_tcp_table(p.tables)]
    tpp = [{'candidate_id': cand_ids.get(r['name'], r['name']), 'party': canon_from_name(r['party_name']), 'votes': r['votes'], 'pct': r['pct']} for r in parse_tpp_table(p.tables)]
    links = {k: v for k, v in p.links}
    hrefs = [v for _, v in p.links]
    def sub(suffix, link_id):
        if link_id in links:
            return links[link_id]
        return next((h for h in hrefs if h.rstrip('/').endswith(suffix) and dslug in h), None)
    fp_path = sub('district-results-by-voting-centre', 'FPVResultsLink')
    tcp_path = sub('2cp-results-by-voting-centre', 'TwoCPLink')
    dist_path = sub('results-distribution', 'DistributionsLink')
    booths = {}
    def booth(label, kind):
        bid = f'{cid}-{slug(label)}' if kind == 'ordinary' else f'{cid}-{kind}'
        if bid not in booths:
            booths[bid] = {'booth_id': bid, 'name': label if kind == 'ordinary' else f'{dname} {kind.replace("_", " ")}',
                           'type': kind, 'fp': {}, 'informal': None, 'total': None, 'tcp': {}, 'reported': False}
        return booths[bid]
    if fp_path:
        d2 = f.get(fp_path)
        if d2:
            rows, _ = parse_booth_table(next((t for t in parse_html(d2).tables if t and len(t) > 2 and t[1] and t[1][0].lower().startswith('voting')), []))
            for r in rows:
                b = booth(r['label'], r['kind'])
                b['fp'] = {cand_ids[n]: v for n, v in r['votes'].items() if n in cand_ids and v is not None}
                b['informal'], b['total'] = r['informal'], r['total']
                b['reported'] = bool(r['total'])
    if tcp_path:
        d3 = f.get(tcp_path)
        if d3:
            rows, _ = parse_booth_table(next((t for t in parse_html(d3).tables if t and len(t) > 2 and t[1] and t[1][0].lower().startswith('voting')), []))
            for r in rows:
                b = booth(r['label'], r['kind'])
                b['tcp'] = {cand_ids[n]: v for n, v in r['votes'].items() if n in cand_ids and v is not None}
                if not b['reported'] and r['total']:
                    b['reported'] = True
    dop = []
    if dist_path:
        d4 = f.get(dist_path)
        if d4:
            t = next((t for t in parse_html(d4).tables if t and len(t) > 1 and t[1] and t[1][0].lower().startswith('total first preference')), [])
            dop = [{**r, 'candidate_id': cand_ids.get(r.pop('candidate'), None)} for r in parse_distribution(t)]
    # the two-candidate-preferred pair: from the final table if published, else the 2CP table's two candidates
    tcp_pair = [x['candidate_id'] for x in final] if len(final) == 2 else (sorted({k for b in booths.values() for k in b['tcp']}) or [x['candidate_id'] for x in tcp_total])
    # totals by vote type (ordinary = sum of election-day booths), handy for the % counted indicator
    return {'contest_id': cid, 'name': dname, 'election_id': election_id, **summary,
            'candidates': out_c, 'final_pair': final, 'tcp_total': tcp_total, 'tpp': tpp, 'tcp_pair': tcp_pair, 'booths': booths, 'dop': dop,
            'pages': {'district': path, 'fp': fp_path, 'tcp': tcp_path, 'dist': dist_path}}


def _norm(x):
    return re.sub(r'[^a-z]', '', str(x or '').lower())


# ---------------------------------------------------------------- change stamping
def digest(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:12]


def stamp(new, prev, now):
    """Carry `first_seen`/`updated_at` forward where nothing changed; stamp `now` where it did. Returns the change log entries."""
    changes = []
    pc = (prev or {}).get('contests', {})
    for cid, c in new['contests'].items():
        old = pc.get(cid)
        sig = digest({k: c.get(k) for k in ('enrolment', 'formal', 'informal', 'total_votes', 'elected', 'candidates', 'final_pair', 'tcp_total', 'dop')})
        c['sig'] = sig
        if old and old.get('sig') == sig:
            c['updated_at'], c['first_seen'] = old.get('updated_at'), old.get('first_seen')
        else:
            c['updated_at'] = now
            c['first_seen'] = (old or {}).get('first_seen') or now
            changes.append({'at': now, 'contest_id': cid, 'booth_id': None, 'what': 'district totals' + (' + final count' if c['final_pair'] else '')})
        ob = (old or {}).get('booths', {})
        for bid, b in c['booths'].items():
            bs = digest({'fp': b['fp'], 'tcp': b['tcp'], 'informal': b['informal'], 'total': b['total']})
            b['sig'] = bs
            o = ob.get(bid)
            if o and o.get('sig') == bs:
                b['updated_at'], b['first_seen'] = o.get('updated_at'), o.get('first_seen')
            else:
                b['updated_at'] = now
                b['first_seen'] = (o or {}).get('first_seen') or now
                if b['reported']:
                    changes.append({'at': now, 'contest_id': cid, 'booth_id': bid, 'what': 'first figures' if not (o or {}).get('reported') else 'revised'})
    return changes


def counted_summary(c):
    """Votes counted so far by vote type, and the share of 2022-style enrolment that represents."""
    by = {}
    for b in c['booths'].values():
        if b['reported']:
            by[b['type']] = by.get(b['type'], 0) + (b['total'] or 0)
    n_rep = sum(1 for b in c['booths'].values() if b['type'] == 'ordinary' and b['reported'])
    n_all = sum(1 for b in c['booths'].values() if b['type'] == 'ordinary')
    return {'by_type': by, 'booths_reported': n_rep, 'booths_listed': n_all,
            'pct_enrolment': round(100.0 * (c['total_votes'] or sum(by.values())) / c['enrolment'], 1) if c.get('enrolment') else None}


# ---------------------------------------------------------------- one cycle
def run_cycle(args, log=print):
    t0 = time.time()
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    f = Fetcher(args.base, delay=args.delay, fixtures=args.fixtures, log=log)
    index = f.get(args.base if not args.fixtures else args.base.replace(f.host, ''))
    if index is None:
        log('could not fetch the results index; nothing written')
        return None
    links = district_links(index)
    if args.districts:
        want = set(args.districts.split(','))
        links = [(s, p) for s, p in links if s in want]
    log(f'{len(links)} districts listed at {args.base}')
    prev = None
    latest_path = os.path.join(args.out, 'latest.json')
    if os.path.exists(latest_path):
        try:
            prev = json.load(open(latest_path))
        except Exception:
            prev = None
    contests = {}
    for i, (dslug, path) in enumerate(links, start=1):
        d = scrape_district(f, dslug, path, args.election_id, log)
        if d is None:
            log(f'  [{i}/{len(links)}] {dslug}: not fetched' + (' (keeping previous)' if prev and f'vic-{dslug}' in prev.get('contests', {}) else ''))
            if prev and f'vic-{dslug}' in prev.get('contests', {}):
                contests[f'vic-{dslug}'] = prev['contests'][f'vic-{dslug}']
            continue
        d['counted'] = counted_summary(d)
        contests[d['contest_id']] = d
        nb = sum(1 for b in d['booths'].values() if b['reported'] and b['type'] == 'ordinary')
        log(f'  [{i}/{len(links)}] {d["name"]}: {len(d["candidates"])} candidates, {nb} booths reported, {d["counted"]["pct_enrolment"]}% of enrolment counted')
    new = {'election_id': args.election_id, 'base': args.base, 'fetched_at': now, 'contests': contests}
    changes = stamp(new, prev, now)
    new['n_changed_booths'] = sum(1 for ch in changes if ch['booth_id'])
    new['n_changed_contests'] = len({ch['contest_id'] for ch in changes})
    os.makedirs(os.path.join(args.out, 'snapshots'), exist_ok=True)
    tmp = latest_path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(new, fh, separators=(',', ':'))
    os.replace(tmp, latest_path)
    if not args.no_snapshots:
        with gzip.open(os.path.join(args.out, 'snapshots', now.replace(':', '').replace('+', 'p') + '.json.gz'), 'wt') as fh:
            json.dump(new, fh, separators=(',', ':'))
    log_path = os.path.join(args.out, 'changes.json')
    old_log = []
    if os.path.exists(log_path):
        try:
            old_log = json.load(open(log_path))
        except Exception:
            old_log = []
    json.dump((changes + old_log)[:5000], open(log_path, 'w'), separators=(',', ':'))
    status = {'fetched_at': now, 'seconds': round(time.time() - t0, 1), 'fetches': f.n_fetch, 'errors': f.errors,
              'districts': len(contests), 'changed_booths': new['n_changed_booths'], 'changed_contests': new['n_changed_contests'],
              'interval': args.loop}
    json.dump(status, open(os.path.join(args.out, 'status.json'), 'w'), indent=1)
    log(f'cycle done in {status["seconds"]}s: {f.n_fetch} fetches, {len(f.errors)} errors, {new["n_changed_booths"]} booths changed in {new["n_changed_contests"]} districts')
    if args.publish or args.publish_cmd:
        import subprocess
        root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        cmd = args.publish_cmd or ('git add site/data/live/latest.json site/data/live/status.json site/data/live/changes.json && '
                                   f'git commit -q -m "live feed {now}" && git push -q')
        try:
            r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=180)
            log('published' if r.returncode == 0 else f'publish failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}')
        except Exception as e:  # noqa
            log(f'publish failed: {e}')
    return new


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', default=DEFAULT_BASE, help='results index page for the election')
    ap.add_argument('--election-id', default='vic2026')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site', 'data', 'live'))
    ap.add_argument('--loop', type=int, default=0, help='seconds between cycles (0 = run once)')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--delay', type=float, default=0.8, help='seconds between page fetches (the VEC rate-limits with HTTP 999)')
    ap.add_argument('--districts', default='', help='comma-separated district slugs to limit to')
    ap.add_argument('--fixtures', default='', help='offline: JSON of {url path: html} instead of the network')
    ap.add_argument('--no-snapshots', action='store_true')
    ap.add_argument('--publish', action='store_true', help='after each cycle, git commit and push the feed (for a GitHub Pages site)')
    ap.add_argument('--publish-cmd', default='', help='shell command to run after each cycle instead of the git push')
    args = ap.parse_args(argv)
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    def log(msg):
        print(time.strftime('%H:%M:%S'), msg, flush=True)
    if args.base == 'auto':
        # find this year's results page from the VEC's results hub (the exact slug is only known once it is published)
        year = re.sub(r'\D', '', args.election_id) or str(datetime.date.today().year)
        hub = Fetcher('https://www.vec.vic.gov.au/results/state-election-results', delay=0).get('https://www.vec.vic.gov.au/results/state-election-results')
        m = re.search(r'href="([^"]*' + year + r'[^"]*state-election-results[^"]*)"', hub or '')
        args.base = ('https://www.vec.vic.gov.au' + m.group(1) if m.group(1).startswith('/') else m.group(1)) if m else DEFAULT_BASE.replace('2026', year)
        log(f'results page: {args.base}' + ('' if m else ' (guessed; not found on the hub yet)'))
    while True:
        try:
            run_cycle(args, log)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # keep polling through the night whatever happens
            import traceback; traceback.print_exc()
            log(f'cycle failed: {e}')
        if not args.loop or args.once:
            break
        log(f'sleeping {args.loop}s')
        try:
            time.sleep(args.loop)
        except KeyboardInterrupt:
            break


if __name__ == '__main__':
    main()
