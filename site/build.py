"""Wrap app.html (artifact body) into a standalone index.html for static hosting, with a basemap."""
import sys
body = open('site/app.html').read()
basemap = sys.argv[1] if len(sys.argv) > 1 else 'https://tiles.openfreemap.org/styles/positron'
head = f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<script>window.__BASEMAP = {basemap!r}; window.__DATA_BASE = 'data/';</script>
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
open('site/index.html', 'w').write(html)
print('site/index.html', len(html), 'bytes; basemap =', basemap)
