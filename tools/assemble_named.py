#!/usr/bin/env python3
"""Reassemble a browser result delivered in {part, of, data} pieces where `data` is the JSON text of a
{label|filename: base64(gzip(bytes))} object, and write each file into <outdir>.
Handles results that arrive as a JSON string literal (quoted, escaped) with a trailing "(captured at ...)" note.
Usage: assemble_named.py <outdir> <part1.txt> <part2.txt> ..."""
import sys, json, base64, gzip, os

outdir = sys.argv[1]
os.makedirs(outdir, exist_ok=True)
parts = []
dec = json.JSONDecoder()
for p in sys.argv[2:]:
    txt = json.load(open(p))[0]['text']
    if 'truncated' in txt[-200:]:
        sys.exit(f'TRUNCATED: {p}')
    if txt.startswith('"'):
        txt, _ = dec.raw_decode(txt)          # unwrap the string literal
    d = json.loads(txt[:txt.rfind('}') + 1])
    parts.append((d['part'], d['of'], d['data']))
parts.sort()
assert [p[0] for p in parts] == list(range(1, parts[0][1] + 1)), f'missing parts: have {[p[0] for p in parts]} of {parts[0][1]}'
payload = json.loads(''.join(p[2] for p in parts))
for k, v in payload.items():
    if k.startswith('ERR'):
        print('ERROR', k, v); continue
    fn = k.split('|')[-1]
    data = gzip.decompress(base64.b64decode(v))
    open(os.path.join(outdir, fn), 'wb').write(data)
    print(fn, len(data))
