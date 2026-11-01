"""Reassemble a gzip+base64 capture returned from the browser pane in {part, of, data} parts (tool-result files)."""
import sys, json, base64, gzip
out = sys.argv[1]; files = sys.argv[2:]
parts = {}
dec = json.JSONDecoder()
for f in files:
    txt = json.load(open(f))[0]['text']
    inner, _ = dec.raw_decode(txt)
    obj = json.loads(inner) if isinstance(inner, str) else inner
    parts[obj['part']] = obj['data']
b64 = ''.join(parts[i] for i in sorted(parts))
data = gzip.decompress(base64.b64decode(b64))
open(out, 'wb').write(data)
print(out, len(data), 'bytes from', len(parts), 'parts')
