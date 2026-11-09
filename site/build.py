"""Wrap app.html (artifact body) into a standalone index.html for static hosting, with a basemap."""
import sys, os
# usage: python3 site/build.py [basemap]            -> site/index.html from site/app.html (the live site)
#        python3 site/build.py --preview [basemap]  -> site/preview/index.html from site/app_v2.html (the redesign; reads ../data/)
args = [a for a in sys.argv[1:] if a != '--preview']
PREVIEW = '--preview' in sys.argv[1:]
SRC, OUT, DATA_BASE = ('site/app_v2.html', 'site/preview/index.html', '../data/') if PREVIEW else ('site/app.html', 'site/index.html', 'data/')
body = open(SRC).read()
basemap = args[0] if args else 'https://tiles.openfreemap.org/styles/positron'
head = f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<script>window.__BASEMAP = {basemap!r}; window.__DATA_BASE = {DATA_BASE!r};</script>
<script>
// visit counts (GoatCounter: no cookies, no personal data), on the public site only (github.io or electionboothatlas.org) — never on localhost or in previews
if (/(\\.github\\.io|electionboothatlas\\.(org|com))$/.test(location.hostname)) {{
  window.__GC = true;
  const s = document.createElement('script'); s.async = true; s.src = 'https://gc.zgo.at/count.js';
  s.setAttribute('data-goatcounter', 'https://electionboothatlas.goatcounter.com/count');
  s.setAttribute('data-goatcounter-settings', '{{"no_onload": true}}');
  s.onload = () => {{ const v = document.querySelector('.view.active'); if (window.goatcounter && v) window.goatcounter.count({{ path: '/' + v.id.replace('view-', ''), title: document.title }}); }};
  document.head.append(s);
}}
</script>
"""
# move <title>, meta, link, style into head; everything else into body
import re
m = re.search(r'(.*?</style>\s*)(.*)', body, re.S)
head_part, body_part = m.group(1), m.group(2)
html = head + head_part + "</head>\n<body>\n" + body_part + "\n</body>\n</html>\n"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
if PREVIEW:
    import shutil; shutil.copy('site/logo.png', 'site/preview/logo.png')
open(OUT, 'w').write(html)
print(OUT, len(html), 'bytes; basemap =', basemap)
