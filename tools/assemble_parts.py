#!/usr/bin/env python3
"""Reassemble a gzip+base64 payload delivered in {part, of, data} pieces into a file.
Usage: assemble_parts.py <out_file> <part1.txt> <part2.txt> ..."""
import sys, json, base64, gzip

out = sys.argv[1]
parts = []
for p in sys.argv[2:]:
    txt = json.load(open(p))[0]['text']
    if 'truncated' in txt[-200:]:
        sys.exit(f'TRUNCATED: {p}')
    d = json.loads(txt[:txt.rfind('}') + 1])
    parts.append((d['part'], d['data']))
parts.sort()
data = gzip.decompress(base64.b64decode(''.join(d for _, d in parts)))
open(out, 'wb').write(data)
print(out, len(data), 'bytes from', len(parts), 'parts')
