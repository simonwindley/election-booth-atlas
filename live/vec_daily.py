#!/usr/bin/env python3
"""Daily capture of what the VEC publishes in the lead-up to the 2026 state election.

Standard library only. Run once a day (or whenever) on the Mac:

    python3 live/vec_daily.py            # writes site/data/live/daily.json (+ a dated snapshot)
    python3 live/vec_daily.py --publish  # and git commit/push it for the GitHub Pages site
    (--full-htv re-fetches every how-to-vote table; --candidates re-reads the candidate lists, skipped once final)

What it looks for, in order of when the VEC publishes it:
  enrolment      the "District statistics" spreadsheet on the electoral roll statistics page (monthly; the
                 close-of-roll figures appear after 3 Nov) -> electors per district
  htv            registered how-to-vote cards (10-20 Nov): registrant, district/region, date, PDF link
  candidates     the results index + district pages once nominations are declared (9 Nov): names, parties,
                 ballot order (parsed with the election-night poller's own parser)
  stats          anything the VEC posts as early-voting / postal-vote / turnout statistics: pages are
                 discovered from the 2026 election page by link text, every table on them is kept, and any
                 table with a District column is turned into a per-district series keyed by capture date
  centres        early voting centre lists (addresses), when published

Everything captured is kept raw as well (daily.json -> "raw"), so a page the parsers do not understand
yet is still saved for the next version of this script. Pages that do not exist yet are simply skipped.
URLs are guesses from the 2022 layout until the real pages appear; add or fix them in live/daily_sources.json.
"""
import argparse, datetime, gzip, io, json, os, re, sys, time, zipfile, html as htmlmod
import urllib.request, urllib.error, urllib.parse
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vec_live import TableParser, parse_html, num, slug, canon_from_name, parse_candidate_table, parse_summary, district_links  # noqa: E402

VEC = 'https://www.vec.vic.gov.au'
UA = 'BoothAtlas daily capture (personal research) python-urllib'
DEFAULT_SOURCES = {
    'election_page': ['/voting/2026-state-election'],
    'roll_stats': ['/enrolment/electoral-roll-statistics'],
    'htv_page': ['/voting/2026-state-election/how-to-vote-cards'],
    'results_index': ['/results/state-election-results/2026-state-election-results'],
    'postal': ['/voting/2026-state-election/postal-voting'],
    'early': ['/voting/2026-state-election/voting-options', '/voting/2026-state-election/early-voting'],
    # discovered from the election page by link text; listed here only so they can be pinned once known
    'stats': [],
    'centres': [],
}
DISCOVER = {  # link text / href patterns -> source key
    'stats': r'statistic|early vot\w* (figure|number|data)|postal vote (figure|number|statistic|application)|turnout',
    'centres': r'early voting centre|voting centre location|where to vote|find a voting centre',
    'candidates': r'candidate list|nominated candidates|who are the candidates',
}


class OrderedParser(TableParser):
    """TableParser that also records the nearest heading before each table (the HTV pages group by party)."""
    def __init__(self):
        super().__init__()
        self.table_headings, self._last_heading = [], ''
        self.cell_links = []
        self._cur_links = None

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        a = dict(attrs)
        if tag == 'table':
            self.table_headings.append(self._last_heading)
            self._cur_links = []
        if tag == 'tr' and self._cur_links is not None:
            self._cur_links.append([])
        if tag == 'a' and a.get('href') and self._cur_links and self._cell is not None:
            self._cur_links[-1].append(a['href'])

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2', 'h3') and self._heading is not None:
            self._last_heading = re.sub(r'\s+', ' ', ''.join(self._heading)).strip()
        if tag == 'table' and self._cur_links is not None:
            self.cell_links.append(self._cur_links); self._cur_links = None
        super().handle_endtag(tag)


def fetch(url, binary=False, log=print, timeout=40):
    url = url if url.startswith('http') else VEC + url
    for attempt, wait in enumerate([0, 4, 12]):
        if wait:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.decompress(data)
                time.sleep(0.8)
                return data if binary else data.decode('utf-8', 'replace'), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None, None
            log(f'  HTTP {e.code} {url}')
        except Exception as e:  # noqa
            log(f'  {type(e).__name__}: {e} {url}')
    return None, None


def first_ok(paths, log):
    for p in paths:
        doc, final = fetch(p, log=log)
        if doc and 'Page not found' not in doc[:4000]:
            return doc, final
    return None, None


# ------------------------------------------------------------------ xlsx without openpyxl
def xlsx_rows(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % ns['m'])))
    sheet = next(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter('{%s}row' % ns['m']):
        cells = []
        for c in row.findall('m:c', ns):
            v = c.find('m:v', ns); t = c.get('t')
            if v is None:
                cells.append(None); continue
            if t == 's':
                cells.append(shared[int(v.text)])
            else:
                try:
                    f = float(v.text); cells.append(int(f) if f == int(f) else f)
                except ValueError:
                    cells.append(v.text)
        rows.append(cells)
    return rows


def capture_enrolment(src, log):
    page, _ = first_ok(src['roll_stats'], log)
    if not page:
        return None
    p = OrderedParser(); p.feed(page); p.close()
    # the page text links: "District statistics - September 2026 (xlsx, ...)" -> pick the last district one
    cands = [h for _, h in p.links if h.endswith('.xlsx')]
    m = re.findall(r'href="([^"]+\.xlsx)"[^>]*>\s*District statistics[^<]*', page)
    target = (m or cands or [None])[-1]
    if not target:
        return None
    data, _ = fetch(target, binary=True, log=log)
    if not data:
        return None
    rows = xlsx_rows(data)
    out, extracted = {}, None
    for r in rows:
        vals = [c for c in r if c is not None]
        if len(vals) >= 2 and str(vals[0]).startswith('Date Extracted'):
            v = vals[1]
            extracted = (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))).isoformat() if isinstance(v, (int, float)) else str(v)
        if len(vals) >= 3 and isinstance(vals[0], int) and isinstance(vals[2], int) and isinstance(vals[1], str):
            out[f'vic-{slug(vals[1])}'] = {'name': vals[1], 'electors': vals[2]}
    log(f'  enrolment: {len(out)} districts, extracted {extracted}, from {target}')
    return {'date_extracted': extracted, 'source': target, 'districts': out}


HTV_KIND = {'by party': 'party', 'by independent candidate': 'independent', 'by non-candidate registrations': 'non_candidate'}


def htv_table(html):
    """rows of one GetTable fragment: (cells, links) per body row"""
    rows = []
    for tr in re.findall(r'<tr\b.*?</tr>', html, flags=re.S | re.I):
        cells = [htmlmod.unescape(re.sub(r'<[^>]+>', ' ', c)).split() for c in re.findall(r'<td\b.*?</td>', tr, flags=re.S | re.I)]
        links = [htmlmod.unescape(h) for h in re.findall(r'href="([^"]+)"', tr)]
        if cells:
            rows.append(([' '.join(c) for c in cells], links))
    return rows


def capture_htv(src, log, prev=None, full=False):
    """2026: one accordion page; each area x category table loads from /api/sitecore/HtvcResults/GetTable.
    The page itself carries every area's id and a card count per category, so only non-empty tables are fetched."""
    page, url = first_ok(src.get('htv_page', ['/voting/2026-state-election/how-to-vote-cards']), log)
    if not page:
        return None
    out, raw, n_expected = [], {'url': url, 'tables': {}}, 0
    prev = prev or {}; prev_counts = {} if full else (prev.get('counts') or {}); prev_cards = prev.get('cards') or []
    counts, reused, fetched = {}, 0, 0
    parts = re.split(r'(?=<button[^>]*js-category-link)', page)
    for part in parts[1:]:
        attrs = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', part[:part.index('>') + 1]))
        cat = attrs.get('category-key', ''); area = htmlmod.unescape(attrs.get('area-name', ''))
        m = re.search(r'Number of registered cards:\s*(\d+)', part[:3000])
        n = int(m.group(1)) if m else 0
        if 'registration date' in cat:
            n_expected += n; continue
        kind = next((k for c, k in HTV_KIND.items() if c in cat), None)
        if not n or not kind:
            continue
        counts[f'{area}|{cat}'] = n
        if prev_counts.get(f'{area}|{cat}') == n:   # unchanged since the last run: keep those cards, spare the VEC a request
            keep = [c for c in prev_cards if c.get('area') == area and c.get('kind') == kind]
            if len(keep) == n:
                out += keep; reused += 1; continue
        fetched += 1
        q = urllib.parse.urlencode({'areaType': attrs.get('area-type', ''), 'areaItemId': attrs.get('area-id', ''), 'category': cat})
        frag, _ = fetch('/api/sitecore/HtvcResults/GetTable?' + q, log=log)
        if not frag:
            continue
        raw['tables'][f'{area}|{cat}'] = frag
        is_d = area.endswith('District')
        cid = ('vic-' if is_d else 'vicr-') + slug(re.sub(r' (District|Region)$', '', area))
        for cells, links in htv_table(frag):
            if len(cells) < 4:
                continue
            pdf = next((l for l in links if 'ViewCard' in l or '.pdf' in l.lower()), None)
            out.append({'kind': kind, 'registrant': cells[0], 'area': area, 'contest_id': cid, 'house': 'LA' if is_d else 'LC',
                        'registered': cells[1], 'registration': cells[2], 'type': cells[3] if len(cells) >= 5 else '',
                        'pdf': (VEC + pdf) if pdf and pdf.startswith('/') else pdf})
    by = {k: sum(1 for c in out if c['kind'] == k) for k in HTV_KIND.values()}
    log(f'  htv: {len(out)} cards {by}; the page counts {n_expected}; {fetched} tables fetched, {reused} unchanged and kept')
    old = [c for c in out if re.search(r'\b(19|20)\d\d\b', c['registered'] or '') and not re.search(r'\b2026\b', c['registered'])]
    if old:
        out = [c for c in out if c not in old]
    return {'cards': out, 'raw': raw, 'counts': counts}


def capture_nominations(src, log):
    """Who has nominated so far: the VEC lists candidates per district at
    /electoral-boundaries/state-districts/<district>-district/nominations from 4 Nov (name + party; the contact
    details on the page are not kept). Until the ballot draw the order is the order of nomination."""
    index, url = first_ok(src.get('districts_index', ['/electoral-boundaries/state-districts']), log)
    if not index:
        return None
    paths = sorted(set(re.findall(r'href="(/electoral-boundaries/state-districts/[a-z0-9-]+-district)"', index)))
    if not paths:
        return None
    out, n = {}, 0
    for path in paths:
        doc, _ = fetch(path + '/nominations', log=log)
        if not doc:
            continue
        dslug = path.rsplit('/', 1)[1].replace('-district', '')
        cands = []
        for m in re.finditer(r'<td>\s*([^<]+?)\s*(?:<p>([^<]*)</p>)?\s*</td>', doc):
            name = htmlmod.unescape(m.group(1)).strip(); party = htmlmod.unescape(m.group(2) or '').strip()
            sur = name.split(',', 1)[0]   # VEC writes SURNAME, Given: allow any letters and case (McCOLL, de VIETRI, DOLEJSÍ, O'BRIEN), but need a capitalised run
            if not (re.match(r"^[^\W\d_][^\W\d_'’ .-]*(?:[ '’.-]+[^\W\d_][^\W\d_'’.-]*)*,\s*\S", name) and re.search(r'[^\W\d_a-z]{2}', sur) and sur == sur.upper().replace('MC', 'Mc') or (re.match(r"^[^\W\d_]", name) and ',' in name and sum(c.isupper() for c in sur) >= max(2, len([c for c in sur if c.isalpha()]) - 3))):
                continue
            cands.append({'name': name, 'party_name': party or 'Independent', 'party': canon_from_name(party) if party else 'IND', 'ballot_position': len(cands) + 1})
        if cands:
            out[f'vic-{dslug}'] = {'enrolment': None, 'candidates': cands}; n += len(cands)
    log(f'  nominations: {len(out)} districts with nominations so far, {n} candidates')
    try:   # sanity check against the pre-nomination list: a known candidate missing usually means a parsing miss, not a withdrawal
        B = json.load(gzip.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site', 'data', 'c2026_candidates.json.gz')))
        ci = {c: i for i, c in enumerate(B['cols'])}
        for r in B['rows']:
            cid, nm = r[ci['contest_id']], r[ci['name']]
            got = ' '.join(c['name'] for c in out.get(cid, {}).get('candidates', [])).lower()
            if cid in out and nm.split()[-1].lower() not in got:
                log(f'  CHECK: {nm} ({r[ci["party"]]}) was expected in {cid} but is not in the VEC list: withdrawn, or a parsing miss?')
    except Exception as e:
        log(f'  (sanity check skipped: {e})')
    return {'source': url, 'districts': out, 'order': 'nomination', 'declared': False}


def capture_candidates(src, log):
    index, url = first_ok(src['results_index'], log)
    if not index:
        return None
    links = district_links(index)
    if not links:
        return None
    out = {}
    for dslug, path in links:
        doc, _ = fetch(path, log=log)
        if not doc:
            continue
        p = parse_html(doc)
        cands = parse_candidate_table(p.tables)
        s = parse_summary(p)
        out[f'vic-{dslug}'] = {'enrolment': s['enrolment'], 'candidates': [{'name': c['name'], 'party_name': c['party_name'], 'party': canon_from_name(c['party_name']), 'ballot_position': i} for i, c in enumerate(cands, start=1)]}
    log(f'  candidates: {len(out)} district pages, {sum(len(v["candidates"]) for v in out.values())} candidates')
    return {'source': url, 'districts': out}


def district_series(tables):
    """Tables with a District column and numeric columns -> {district_id: {column: value}}."""
    out = {}
    for t in tables:
        if not t or len(t) < 2:
            continue
        hdr = [h.lower() for h in t[0]]
        di = next((i for i, h in enumerate(hdr) if 'district' in h or 'electorate' in h), None)
        if di is None:
            continue
        for r in t[1:]:
            if len(r) <= di or not r[di]:
                continue
            name = re.sub(r'\s*District$', '', r[di]).strip()
            vals = {t[0][j]: num(r[j]) for j in range(len(r)) if j != di and j < len(t[0]) and num(r[j]) is not None}
            if vals:
                out.setdefault(f'vic-{slug(name)}', {}).update(vals)
    return out


def capture_pages(src, keys, log):
    """Fetch every configured/discovered page for these keys; keep tables raw and any per-district figures."""
    raw, series = {}, {}
    for key in keys:
        for path in src.get(key, []):
            if re.search(r'local-council|council-election', path):   # council statistics turn up in discovery: not this election
                continue
            doc, url = fetch(path, log=log)
            if not doc or 'Page not found' in doc[:4000]:
                continue
            p = parse_html(doc)
            text = re.sub(r'\s+', ' ', p.text)[:3000]
            raw[url] = {'key': key, 'headings': p.headings[:30], 'tables': p.tables, 'text': text}
            ds = district_series(p.tables)
            if ds:
                series[url] = ds
            # headline numbers in prose ("123,456 early votes")
            nums = re.findall(r'([\d,]{4,})\s+(early vot\w*|postal vote\w*|applications?|votes)', text, re.I)
            if nums:
                raw[url]['figures'] = nums[:10]
            log(f'  {key}: {url} ({len(p.tables)} tables{", district figures" if ds else ""})')
    return raw, series


def discover(src, log):
    page, url = first_ok(src['election_page'], log)
    if not page:
        return
    for m in re.finditer(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href, text = m.group(1), re.sub(r'<[^>]+>', ' ', m.group(2))
        text = re.sub(r'\s+', ' ', htmlmod.unescape(text)).strip()
        for key, pat in DISCOVER.items():
            if re.search(pat, text, re.I) or re.search(pat.replace(' ', '[-_ ]'), href, re.I):
                if href not in src.setdefault(key, []):
                    src[key].append(href); log(f'  discovered {key}: {href} ({text[:50]})')


def run(args, log):
    src = json.loads(json.dumps(DEFAULT_SOURCES))
    cfg = os.path.join(HERE, 'daily_sources.json')
    if os.path.exists(cfg):
        for k, v in json.load(open(cfg)).items():
            if isinstance(v, list): src[k] = v + [x for x in src.get(k, []) if x not in v]
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, 'daily.json')
    prev = json.load(open(path)) if os.path.exists(path) else {}
    out = {'captured_at': now, 'date': today, 'enrolment': prev.get('enrolment'), 'htv': prev.get('htv'), 'candidates': prev.get('candidates'),
           'series': prev.get('series', {}), 'raw': {}, 'sources': {}}
    log('discovering pages')
    discover(src, log)
    log('enrolment')
    e = capture_enrolment(src, log)
    if e:
        out['enrolment'] = e
    log('how-to-vote cards')
    hv = capture_htv(src, log, prev.get('htv'), full=args.full_htv)
    if hv and hv['cards']:
        out['htv'] = {'captured': today, 'cards': hv['cards'], 'counts': hv.get('counts', {})}
    out['raw']['htv'] = (hv or {}).get('raw', {})
    pc = prev.get('candidates') or {}
    if len(pc.get('districts') or {}) >= 88 and not args.candidates:
        log('candidates: nominations are final (88 districts captured); keeping them (--candidates to re-read)')
    else:
        log('candidates (results pages)')
        c = capture_candidates(src, log)
        if not c or not c.get('districts'):
            log('candidates (nominations so far)')
            c = capture_nominations(src, log)
        if c and c['districts']:
            out['candidates'] = {'captured': today, **c}
    log('statistics pages')
    raw, series = capture_pages(src, ['stats', 'postal', 'early', 'centres'], log)
    out['raw']['pages'] = raw
    for url, ds in series.items():
        for cid, vals in ds.items():
            out['series'].setdefault(cid, {}).setdefault(today, {}).update({f'{k}': v for k, v in vals.items()})
    out['sources'] = {k: v for k, v in src.items() if v}
    # the site loads daily.json on every visit: it carries what the pages use, not the raw VEC pages.
    # The full capture (raw pages included) is kept as a dated snapshot outside the published site.
    full = dict(out); pub = {k: v for k, v in out.items() if k != 'raw'}
    tmp = path + '.tmp'
    json.dump(pub, open(tmp, 'w'), separators=(',', ':')); os.replace(tmp, path)
    snap = os.path.abspath(os.path.join(HERE, '..', 'data', 'live_snapshots')); os.makedirs(snap, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
    with gzip.open(os.path.join(snap, stamp + '.json.gz'), 'wt') as f:
        json.dump(full, f, separators=(',', ':'))
    log(f'wrote {path}: enrolment {"yes" if out["enrolment"] else "no"}, htv cards {len((out["htv"] or {}).get("cards", []))}, '
        f'candidates {len((out["candidates"] or {}).get("districts", {}))} districts, district series {len(out["series"])}')
    if args.publish or args.publish_cmd:
        import subprocess
        root = os.path.abspath(os.path.join(HERE, '..'))
        cmd = args.publish_cmd or 'git add site/data/live/daily.json data/live_snapshots && (git diff --cached --quiet || (git commit -q -m "daily capture %s" && git push -q))' % today
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=180)
        log('published' if r.returncode == 0 else f'publish failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'site', 'data', 'live'))
    ap.add_argument('--publish', action='store_true')
    ap.add_argument('--publish-cmd', default='')
    ap.add_argument('--candidates', action='store_true', help='re-read the candidate lists (skipped once all 88 districts are captured)')
    ap.add_argument('--full-htv', action='store_true', help='re-fetch every how-to-vote table, not just those whose count changed')
    args = ap.parse_args(argv)
    args.out = os.path.abspath(args.out)
    def log(msg):
        print(time.strftime('%H:%M:%S'), msg, flush=True)
    run(args, log)


if __name__ == '__main__':
    main()
