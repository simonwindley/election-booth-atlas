#!/usr/bin/env python3
"""Decode a {label|filename: base64(gzip(bytes))} payload into <outdir>/<filename>.
Usage: decode_named_chunk.py <outdir> <result.txt> [<result.txt> ...]"""
import sys, json, base64, gzip, os

outdir = sys.argv[1]
os.makedirs(outdir, exist_ok=True)
for src in sys.argv[2:]:
    txt = json.load(open(src))[0]['text']
    if 'truncated' in txt[-200:]:
        sys.exit(f'TRUNCATED: {src}')
    d = json.loads(txt[:txt.rfind('}') + 1])
    for k, v in d.items():
        fn = k.split('|')[-1]
        data = gzip.decompress(base64.b64decode(v))
        open(os.path.join(outdir, fn), 'wb').write(data)
        print(fn, len(data))
