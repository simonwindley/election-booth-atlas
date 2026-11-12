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
