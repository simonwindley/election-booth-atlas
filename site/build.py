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
"""
# move <title>, meta, link, style into head; everything else into body
import re
m = re.search(r'(.*?</style>\s*)(.*)', body, re.S)
head_part, body_part = m.group(1), m.group(2)
html = head + head_part + "</head>\n<body>\n" + body_part + "\n</body>\n</html>\n"
open('site/index.html', 'w').write(html)
print('site/index.html', len(html), 'bytes; basemap =', basemap)
