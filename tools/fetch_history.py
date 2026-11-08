"""Fetch the older elections the Atlas does not have yet.

Victorian state elections 1999, 2002 and 2006: the VEC's old results site, as the Internet Archive kept it
(result summary, first preferences by voting centre, two-candidate-preferred by voting centre and the
distribution of preferences for every district), written in the shape `src.load_vec` reads:

    python3 tools/fetch_history.py vec 2006 raw/vec/2006
    python3 tools/fetch_history.py vec 2002 raw/vec/2002
    python3 tools/fetch_history.py vec 1999 raw/vec/1999

Federal elections 2004 (event 12246) and 2007 (event 13745): the AEC Tally Room CSVs `src.load_aec` reads:

    python3 tools/fetch_history.py aec 2007 raw/aec/2007
    python3 tools/fetch_history.py aec 2004 raw/aec/2004

Standard library only. Every page or file fetched is kept under <out>/html/ or <out>/, so a re-run only fetches
what is missing (delete a file to refetch it). The Wayback Machine rate-limits: the script waits between requests
and backs off on 429/5xx; expect 10-15 minutes per state election.
"""
import sys, os, re, json, time, gzip, io
import urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser

UA = 'ElectionBoothAtlas/1.0 (+https://github.com/simonwindley/election-booth-atlas)'
WB = 'https://web.archive.org'
AEC_BASE = {'2007': 'https://results.aec.gov.au/13745/Website/Downloads/', '2004': 'https://results.aec.gov.au/12246/results/Downloads/'}
AEC_EVENT = {'2007': '13745', '2004': '12246'}
AEC_FILES = ['GeneralPollingPlacesDownload-{ev}.csv', 'HouseCandidatesDownload-{ev}.csv', 'HouseDopByDivisionDownload-{ev}.csv',
             'HouseFirstPrefsByCandidateByVoteTypeDownload-{ev}.csv', 'HouseStateFirstPrefsByPollingPlaceDownload-{ev}-VIC.csv',
             'HouseTcpByCandidateByPollingPlaceDownload-{ev}.csv', 'HouseTppByPollingPlaceDownload-{ev}.csv',
             'HouseTcpByCandidateByVoteTypeDownload-{ev}.csv', 'HouseMembersElectedDownload-{ev}.csv']


def get(url, tries=6, pause=1.0):
    """GET with retries; returns bytes. Follows Wayback's redirects to the nearest capture."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                time.sleep(pause)
                return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                return None
            wait = 5 * (2 ** i) if e.code in (429, 503, 504, 502) else 2
            print(f'    HTTP {e.code} on {url[-80:]} - waiting {wait}s', flush=True)
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            last = e
            print(f'    {type(e).__name__}: {e} - retrying', flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f'gave up on {url}: {last}')


# ---------------------------------------------------------------- HTML tables -> row arrays (like innerText)
class Tables(HTMLParser):
    """Collects every <table> as a list of rows of cell strings (innermost cells only for nested tables),
    plus h1 text and the hrefs of links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []; self.stack = []; self.links = []; self.h1 = ''; self._h1 = False; self._cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'table':
            self.stack.append({'rows': []}); self._cell = None
        elif tag == 'tr' and self.stack:
            self.stack[-1]['rows'].append([])
        elif tag in ('td', 'th') and self.stack:
            if not self.stack[-1]['rows']:
                self.stack[-1]['rows'].append([])
            self._cell = []
            self.stack[-1]['rows'][-1].append(self._cell)
        elif tag == 'br' and self._cell is not None:
            self._cell.append('\n')
        elif tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        elif tag == 'h1':
            self._h1 = True

    def handle_endtag(self, tag):
        if tag == 'table' and self.stack:
            t = self.stack.pop()
            rows = [[clean(''.join(c)) for c in r] for r in t['rows']]
            self.tables.append(rows)
            self._cell = None
        elif tag in ('td', 'th'):
            self._cell = None
        elif tag == 'h1':
            self._h1 = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._h1:
            self.h1 += data


def clean(s):
    s = s.replace('\xa0', ' ')
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', ln).strip() for ln in s.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def parse(html):
    p = Tables(); p.feed(html); return p


def biggest(tables):
    return max(tables, key=lambda t: len(t) * max((len(r) for r in t), default=0)) if tables else []


# ---------------------------------------------------------------- VEC (old results site via the Wayback Machine)
def cdx(pattern):
    # prefix match only: the wildcard must be the last character
    url = f'{WB}/cdx/search/cdx?url={urllib.parse.quote(pattern, safe="/*")}&collapse=urlkey&fl=original,timestamp,statuscode&limit=3000'
    data = get(url)
    return [ln.split(' ') for ln in (data or b'').decode().splitlines() if ln.strip()]


def wb_fetch(path, year, cache_dir):
    """Fetch an old VEC results page through the Wayback Machine, cached as html/<file>."""
    fn = os.path.join(cache_dir, path.split('/')[-1])
    if os.path.exists(fn):
        return open(fn, encoding='utf-8', errors='replace').read()
    # 2011-2012 captures are the complete, final ones; "id_" returns the page without the archive's banner
    data = get(f'{WB}/web/2011id_/http://www.vec.vic.gov.au/Results/{path}')
    if data is None:
        data = get(f'{WB}/web/2010id_/http://vec.vic.gov.au/Results/{path}')
    if data is None:
        return None
    html = data.decode('utf-8', errors='replace')
    with open(fn, 'w', encoding='utf-8') as f:
        f.write(html)
    return html


def vec_record(year, dname, cache_dir, verbose=True):
    """One district -> the record shape src.load_vec reads (as normalise_2018 produces it)."""
    base = f'state{year}result{dname}District.html'
    html = wb_fetch(base, year, cache_dir)
    if html is None:
        print(f'  !! no capture of {base}', flush=True); return None
    p = parse(html)
    name = re.sub(r'^State Election \d{4}\s*:\s*', '', clean(p.h1)).replace(' District', '').strip() or dname
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    # elected member: the first small table ("THWAITES, John\nAUSTRALIAN LABOR PARTY - VICTORIAN BRANCH")
    elected = ''
    for t in p.tables:
        txt = ' '.join(c for r in t for c in r if c)
        if re.search(r'[A-Z]{2,}, [A-Z][a-z]', txt) and len(t) == 1:
            elected = ' '.join(txt.split('\n')); break
    enrol = {}
    for t in p.tables:
        for r in t:
            if len(r) == 2 and r[0].endswith(':'):
                enrol[r[0].lower()] = r[1]
    g = lambda k: next((v for kk, v in enrol.items() if k in kk), '')
    summary = (f"Elected member {elected} Recheck votes Total enrolment as at close of rolls: {g('enrolment')} "
               f"Formal votes: {g('formal')} Informal votes: {g('informal')} Total votes: {g('total votes')}")
    def cand_table(kind):
        for t in p.tables:
            if t and t[0] and t[0][0] == 'Candidate' and kind in ' '.join(t[0]).lower():
                return [t[0]] + [[c.replace('\n', ' ').strip() for c in r] for r in t[1:] if len(r) >= 3 and re.fullmatch(r'[\d,]+', r[2].replace(' ', ''))]
        return []
    fp_tbl = cand_table('1st pref')
    dist_tbl = cand_table('distribution')
    tcp_tbl = cand_table('preferred')
    if not dist_tbl and tcp_tbl:
        dist_tbl = tcp_tbl
    if not dist_tbl and len(fp_tbl) == 3:  # two candidates: first preferences decide
        dist_tbl = [['Candidate', 'Party', 'Votes after distribution', '% votes']] + [r[:4] for r in fp_tbl[1:]]
    pages = {}
    sub = {f'{slug}-district-results-by-voting-centre': 'FPVbyVotingCentre', f'{slug}-2cp-results-by-voting-centre': 'TCPbyVC',
           f'{slug}-results-distribution': 'distribution'}
    links = {}
    for l in p.links:
        fn_ = l.split('/')[-1]
        m = re.match(rf'state{year}([A-Za-z]+?){re.escape(dname)}District\.html', fn_, re.I)
        if m and not m.group(1).lower().startswith('result'):
            links[m.group(1)] = fn_
    for key, kind in sub.items():
        fn = links.get(kind) or f'state{year}{kind}{dname}District.html'
        if kind not in links and kind != 'FPVbyVotingCentre':
            continue  # the district page links the pages it has; FPV always exists
        h2 = wb_fetch(fn, year, cache_dir)
        if h2 is None:
            print(f'  !! no capture of {fn}', flush=True); continue
        big = biggest(parse(h2).tables)
        if kind == 'distribution':
            big = [[c.replace('\n', ' ') for c in r] for r in big]
        pages[key] = [big] if big else []
    headings = ['Elections', f'State Election {year} : {name} District', 'Elected member', 'Recheck votes', 'Recheck first preference votes']
    if dist_tbl: headings.append('Results after distribution of preferences')
    if tcp_tbl: headings.append('Two candidate preferred vote')
    if verbose:
        fpv = pages.get(f'{slug}-district-results-by-voting-centre', [[]])
        print(f'  {name:24} cands {max(len(fp_tbl) - 1, 0):2}  booth rows {len(fpv[0]) if fpv else 0:3}  '
              f'{"2cp" if f"{slug}-2cp-results-by-voting-centre" in pages else "   "} {"dist" if f"{slug}-results-distribution" in pages else "    "}', flush=True)
    return {'href': f'{dname}District', 'name': f'{name} District results', 'headings': headings, 'summary': summary,
            'tables': [fp_tbl, dist_tbl], 'pages': pages, 'sub': list(pages.keys()), 'elected': elected}


def fetch_vec(year, out):
    cache = os.path.join(out, 'html'); os.makedirs(cache, exist_ok=True)
    print(f'VEC {year}: listing district pages in the Wayback Machine', flush=True)
    rows = cdx(f'vec.vic.gov.au/Results/state{year}result*')
    names = sorted({m.group(1) for r in rows if r[-1] == '200' for m in [re.search(rf'state{year}result([A-Za-z-]+)District\.html', r[0], re.I)] if m})
    if not names:
        print('  the listing came back empty; trying the other host spelling', flush=True)
        rows = cdx(f'www.vec.vic.gov.au/Results/state{year}result*')
        names = sorted({m.group(1) for r in rows if r[-1] == '200' for m in [re.search(rf'state{year}result([A-Za-z-]+)District\.html', r[0], re.I)] if m})
    print(f'  {len(names)} districts', flush=True)
    if len(names) < 80:
        print('  (fewer than expected - the archive listing may be incomplete; the run can be repeated later)')
    recs = []
    for i, dn in enumerate(names, 1):
        print(f'[{i}/{len(names)}]', end=' ', flush=True)
        rec = vec_record(year, dn, cache)
        if rec:
            recs.append(rec)
    path = os.path.join(out, 'districts.json')
    json.dump(recs, open(path, 'w'))
    print(f'wrote {path}: {len(recs)} districts', flush=True)


# ---------------------------------------------------------------- AEC Tally Room CSVs
def fetch_aec(year, out):
    os.makedirs(out, exist_ok=True)
    ev = AEC_EVENT[year]; base = AEC_BASE[year]
    for f in AEC_FILES:
        fn = f.format(ev=ev); path = os.path.join(out, fn)
        if os.path.exists(path):
            print(f'  have {fn}'); continue
        data = get(base + fn, pause=0.5)
        if data is None:
            print(f'  !! {fn} not found'); continue
        open(path, 'wb').write(data)
        print(f'  {fn}: {len(data) // 1024} KB', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in ('vec', 'aec'):
        print(__doc__); sys.exit(1)
    (fetch_vec if sys.argv[1] == 'vec' else fetch_aec)(sys.argv[2], sys.argv[3])
