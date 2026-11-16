"""Short, shareable addresses for every electorate and region: electionboothatlas.org/seat/richmond, /region/northern-victoria.

Writes, from site/index.html and site/og/pages.json (none of these outputs are committed; the Pages workflow runs this on every deploy):
  site/seat/<slug>/index.html, site/region/<slug>/index.html
      the atlas itself, with that electorate's own title, description and preview image for search engines and link previews.
      A first script moves the address back to the site root (/#seat/vic-richmond) before anything loads, so the page
      behaves exactly like the home page.
  site/404.html    sends near-misses (/seat/Richmond, /seats/albert park, /electorate/richmond) to the right page
  site/sitemap.xml every page, for search engines
usage: python3 tools/build_pages.py     (site/build.py runs it too)
"""
import json, os, re, html, shutil, datetime

SITE = 'https://electionboothatlas.org'
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site')
pages = json.load(open(os.path.join(ROOT, 'og', 'pages.json')))
base = open(os.path.join(ROOT, 'index.html')).read()
esc = lambda s: html.escape(s, quote=True)


def meta(doc, title, desc, url, image, alt):
    subs = [
        (r'<title>.*?</title>', f'<title>{esc(title)}</title>'),
        (r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{esc(desc)}">'),
        (r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="{esc(title)}">'),
        (r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{esc(desc)}">'),
        (r'<meta property="og:url" content="[^"]*">', f'<meta property="og:url" content="{url}">'),
        (r'<meta property="og:image" content="[^"]*">', f'<meta property="og:image" content="{image}">'),
        (r'<meta property="og:image:alt" content="[^"]*">', f'<meta property="og:image:alt" content="{esc(alt)}">'),
        (r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{url}">'),
    ]
    for pat, rep in subs:
        doc, n = re.subn(pat, lambda m: rep, doc, count=1)
        if not n: raise SystemExit(f'build_pages: {pat!r} not found in site/index.html (check the meta tags at the top of site/app.html)')
    return doc


def first_script(hash_):
    # runs before any relative URL (data/, favicons) is read: move to the site root, keeping ?ref= and any #view
    return ('<script>(function () { var root = location.pathname.replace(/(seat|region)\\/[^\\/]+\\/?(index\\.html)?$/, \'\'); '
            f'var h = location.hash && location.hash !== \'#\' ? location.hash : {json.dumps(hash_)}; '
            'try { history.replaceState(null, \'\', root + location.search + h); } catch (e) { location.replace(root + location.search + h); } })();</script>\n')


# ---- a plain-HTML summary of each page, written into the page itself ----
# Search engines and slow phones see this before the atlas loads; the atlas then replaces it with the full view.
import gzip, collections
def table(name):
    d = json.load(gzip.open(os.path.join(ROOT, 'data', name)))
    return [dict(zip(d['cols'], r)) for r in d['rows']]
DAILY = json.load(open(os.path.join(ROOT, 'data', 'live', 'daily.json')))
HELD = {r['contest_id']: r['held_by'] for r in table('c2026_contests.json.gz')}
CANDS = {(r['election_id'], r['contest_id'], r['candidate_id']): r for r in table('candidates.json.gz')}
TCP = collections.defaultdict(list)
for r in table('contest_tcp.json.gz'): TCP[(r['election_id'], r['contest_id'])].append(r)
VENUES, BOOTHS_BY = collections.defaultdict(set), collections.defaultdict(set)
for r in table('booths.json.gz'):
    if r['booth_type'] != 'ordinary' or not r['election_id'].startswith('vic'): continue
    VENUES[r['contest_id']].add(r['venue_id'] or r['booth_name'])
    BOOTHS_BY[(r['election_id'], r['contest_id'])].add(r['booth_name'])
HTV = collections.Counter(c['contest_id'] for c in DAILY['htv']['cards'] if c.get('pdf'))
BY_REGION = collections.defaultdict(list)
for q in pages:
    if q['kind'] == 'seat': BY_REGION[q['region']].append(q)
link = lambda q: f'<a href="/{q["kind"]}/{q["slug"]}/">{esc(q["name"])}{" Region" if q["kind"] == "region" else ""}</a>'
REGION_PAGE = {q['name']: q for q in pages if q['kind'] == 'region'}
HELD_AS = {'Labor': 'Labor', 'Liberal': 'the Liberals', 'National': 'the Nationals', 'Greens': 'the Greens', 'Independent': 'an independent'}
def pname(r):
    if r.get('party') == 'IND' or (r.get('party_name') or '').strip().upper() in ('IND', 'INDEPENDENT', ''): return 'independent'
    return re.sub(r'\s*[-–(]\s*Victorian (Branch|Division)\)?$', '', r['party_name']).strip()
nm = lambda r: f"{r['given_name']} {r['surname'].title() if r['surname'].isupper() else r['surname']}"
plural = lambda n, w: f'{n:,} {w}{"" if n == 1 else "s"}'

def summary(p):
    out = ['<div class="static-summary" style="max-width:760px;margin:0 auto;padding:28px 20px;line-height:1.55">']
    if p['kind'] == 'seat':
        cid = p['cid']; reg = REGION_PAGE.get(p['region'])
        out.append(f'<h1>{esc(p["name"])}</h1>')
        held = HELD.get(cid)
        out.append(f'<p>{esc(p["name"])} is a Victorian Legislative Assembly electorate in the {link(reg) if reg else esc(p["region"]) + " Region"}'
                   + (f', held by {esc(HELD_AS.get(held, held))} going into the 2026 state election' if held else '') + '. Polling day is Saturday 28 November 2026.</p>')
        last_el = 'vic2022'
        for el, label in (('vic2023n', 'At the 2023 supplementary election'), ('vic2022', 'At the 2022 state election')):
            t = TCP.get((el, cid))
            if t and len(t) == 2:
                tot = sum(r['votes'] for r in t); t = sorted(t, key=lambda r: -r['votes'])
                w, l = (CANDS.get((el, cid, r['candidate_id'])) for r in t)
                if w and l:
                    out.append(f'<p>{label}, {esc(nm(w))} ({esc(pname(w))}) won with {100 * t[0]["votes"] / tot:.1f}% of the '
                               f'two-candidate-preferred vote against {esc(nm(l))} ({esc(pname(l))}).</p>')
                    last_el = el
                break
        cands = DAILY['candidates']['districts'].get(cid, {}).get('candidates', [])
        if cands:
            out.append(f'<h2>2026 candidates, in ballot order</h2><ol>' + ''.join(f'<li>{esc(c["name"])} ({esc(pname(c))})</li>' for c in sorted(cands, key=lambda c: c.get('ballot_position') or 99)) + '</ol>')
        if HTV.get(cid): out.append(f'<p>All {plural(HTV[cid], "how-to-vote card")} registered with the VEC for {esc(p["name"])} so far are linked in the atlas, whoever registered them.</p>')
        b = sorted(BOOTHS_BY.get((last_el, cid), ()))
        if b: out.append(f'<h2>Election-day polling places in {"2023" if last_el == "vic2023n" else "2022"}</h2><p>{esc(", ".join(b))}.</p>')
        if VENUES.get(cid): out.append(f'<p>The atlas maps results for {plural(len(VENUES[cid]), "polling place")} used in {esc(p["name"])} at Victorian state elections since 1999, with census profiles of each one\'s neighbourhood.</p>')
        others = [q for q in BY_REGION[p['region']] if q['slug'] != p['slug']]
        if others: out.append(f'<p>Other electorates in the {esc(p["region"])} Region: ' + ', '.join(link(q) for q in others) + '.</p>')
    else:
        out.append(f'<h1>{esc(p["name"])} Region</h1>')
        seats = BY_REGION[p['name']]
        out.append(f'<p>{esc(p["name"])} Region elects five members to Victoria\'s Legislative Council, the upper house. It covers {len(seats)} Legislative Assembly electorates: '
                   + ', '.join(link(q) for q in seats) + '. Polling day is Saturday 28 November 2026.</p>')
        rcid = 'vicr-' + p['slug']
        if HTV.get(rcid): out.append(f'<p>All {plural(HTV[rcid], "how-to-vote card")} registered with the VEC for the region\'s upper-house ballot so far are linked in the atlas.</p>')
        out.append('<p>Other regions: ' + ', '.join(link(q) for q in pages if q['kind'] == 'region' and q['slug'] != p['slug']) + '.</p>')
    out.append('<p><a href="/">The Election Booth Atlas</a>: every booth, every election, mapped from official VEC and AEC results since 1999.</p></div>')
    return ''.join(out)

def with_summary(doc, p):
    # show the electorate view (with the summary in it) instead of the map until the atlas takes over
    for a, b in (('<section class="view v2" id="view-seat"><div id="seat-root" style="width:100%"></div></section>',
                  f'<section class="view v2 active" id="view-seat"><div id="seat-root" style="width:100%">{summary(p)}</div></section>'),
                 ('<section class="view active" id="view-map">', '<section class="view" id="view-map">')):
        if doc.count(a) != 1: raise SystemExit(f'build_pages: {a[:50]!r} not found once in site/index.html')
        doc = doc.replace(a, b)
    return doc


for kind in ('seat', 'region'):
    shutil.rmtree(os.path.join(ROOT, kind), ignore_errors=True)
for p in pages:
    url = f"{SITE}/{p['kind']}/{p['slug']}/"
    image = f"{SITE}/og/{p['kind']}-{p['slug']}.png"
    if p['kind'] == 'seat':
        title = f"{p['name']}: every polling booth, results and 2026 candidates · Election Booth Atlas"
        desc = (f"{p['name']}, a Victorian electorate in the {p['region']} Region: results for every polling booth back to 1999, "
                "the 2026 candidates in ballot order, census profiles of each booth's neighbourhood, and live counts on election night, 28 November.")
        hash_ = f"#seat/{p['cid']}"
    else:
        title = f"{p['name']} Region: upper-house ballot and booth results · Election Booth Atlas"
        desc = (f"{p['name']} Region, Victorian Legislative Council: the 2026 upper-house ballot, booth-by-booth results, and its "
                f"{len(p['districts'])} electorates ({', '.join(p['districts'])}). Live counts on election night, 28 November.")
        hash_ = f"#region/{p['slug']}"
    doc = meta(base, title, desc, url, image, f"Map of the polling booths in {p['name']}" + (' Region' if p['kind'] == 'region' else ''))
    doc = re.sub(r'(<meta charset="utf-8">\n)', lambda m: m.group(1) + first_script(hash_), doc, count=1)
    doc = with_summary(doc, p)
    d = os.path.join(ROOT, p['kind'], p['slug']); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'index.html'), 'w').write(doc)

# 404: forgiving about case, spaces, plurals and synonyms; anything else goes home
known = {p['kind'] + '/' + p['slug']: 1 for p in pages}
open(os.path.join(ROOT, '404.html'), 'w').write(f'''<!doctype html>
<html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Election Booth Atlas</title><meta name="robots" content="noindex">
<script>
(function () {{
  var known = {json.dumps(known, separators=(',', ':'))};
  var path = decodeURIComponent(location.pathname).toLowerCase();
  var root = /\\.github\\.io$/.test(location.hostname) ? '/' + path.split('/')[1] + '/' : '/';
  var m = path.match(/\\/(seats?|electorates?|districts?|regions?)\\/(vicr?-)?([^\\/]+)/);
  var to = root;
  if (m) {{
    var kind = /^region/.test(m[1]) ? 'region' : 'seat';
    var slug = m[3].replace(/\\.html?$/, '').replace(/[\\s_+'’.]+/g, '-').replace(/-region$/, '').replace(/-+/g, '-').replace(/^-|-$/g, '');
    if (!known[kind + '/' + slug]) {{
      var flat = slug.replace(/-/g, '');
      for (var k in known) if (k.split('/')[1].replace(/-/g, '') === flat) {{ kind = k.split('/')[0]; slug = k.split('/')[1]; }}
      if (kind === 'seat' && !known['seat/' + slug] && known['region/' + slug]) kind = 'region';
    }}
    if (known[kind + '/' + slug]) to = root + kind + '/' + slug + '/';
  }}
  location.replace(to + location.search);
}})();
</script></head><body><p><a href="/">The Election Booth Atlas</a></p></body></html>
''')

today = datetime.date.today().isoformat()
urls = [SITE + '/'] + [f"{SITE}/{p['kind']}/{p['slug']}/" for p in pages]
open(os.path.join(ROOT, 'sitemap.xml'), 'w').write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                                   + ''.join(f'  <url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n')
print(f'build_pages: {len(pages)} pages, 404.html, sitemap.xml ({len(urls)} addresses)')
