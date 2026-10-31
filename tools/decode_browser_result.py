#!/usr/bin/env python3
"""Decode a gzip+base64 JSON payload saved from a browser javascript_tool result
into files. Usage: decode_browser_result.py <result.txt> <outdir> key=filename [key=filename ...]
"""
import sys, json, base64, gzip, os

src, outdir = sys.argv[1], sys.argv[2]
mapping = dict(a.split('=', 1) for a in sys.argv[3:])
arr = json.load(open(src))
txt = arr[0]['text']
j = txt[:txt.rfind('}') + 1]
d = json.loads(j)
os.makedirs(outdir, exist_ok=True)
for k, v in d.items():
    name = mapping.get(k, k)
    if isinstance(v, str):
        raw = gzip.decompress(base64.b64decode(v)).decode('utf-8')
        out = os.path.join(outdir, name)
        open(out, 'w').write(raw)
        print(out, len(raw.splitlines()), 'lines')
    else:
        out = os.path.join(outdir, name if name.endswith('.json') else name + '.json')
        json.dump(v, open(out, 'w'))
        print(out, 'json')
