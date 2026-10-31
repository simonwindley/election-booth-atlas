#!/usr/bin/env python3
"""Reassemble {part, of, data} pieces (data = base64 of gzip of a JSON/text document) into <out_file>.
Handles results wrapped as a JSON string literal with trailing notes/padding.
Usage: assemble_json_parts.py <out_file> <part1.txt> ..."""
import sys, json, base64, gzip
dec = json.JSONDecoder()
parts = []
for p in sys.argv[2:]:
    txt = json.load(open(p))[0]['text'].strip()
    if 'truncated' in txt[-200:]:
        sys.exit(f'TRUNCATED: {p}')
    if txt.startswith('"'):
        txt, _ = dec.raw_decode(txt)
    txt = txt.strip()
    d = json.loads(txt[:txt.rfind('}') + 1])
    parts.append((d['part'], d['of'], d['data']))
parts.sort()
assert [p[0] for p in parts] == list(range(1, parts[0][1] + 1)), f'missing parts: {[p[0] for p in parts]} of {parts[0][1]}'
data = gzip.decompress(base64.b64decode(''.join(p[2] for p in parts)))
open(sys.argv[1], 'wb').write(data)
print(sys.argv[1], len(data), 'bytes')
