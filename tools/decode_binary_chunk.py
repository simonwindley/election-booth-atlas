#!/usr/bin/env python3
"""Decode a {label|filename: base64(gzip(bytes))} payload saved from the browser into files."""
import sys, json, base64, gzip, os, re

src, outdir = sys.argv[1], sys.argv[2]
arr = json.load(open(src))
txt = arr[0]['text']
if 'truncated' in txt[-200:]:
    sys.exit('TRUNCATED payload — re-fetch in smaller chunks')
d = json.loads(txt[:txt.rfind('}') + 1])
os.makedirs(outdir, exist_ok=True)
for k, v in d.items():
    label, fn = k.split('|')
    name = re.sub(r'[^A-Za-z0-9]+', '_', label.split(' - ')[0].split(' (')[0]).strip('_') + os.path.splitext(fn)[1]
    data = gzip.decompress(base64.b64decode(v))
    open(os.path.join(outdir, name), 'wb').write(data)
    print(name, len(data))
