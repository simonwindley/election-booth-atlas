"""Parse PBO 2022 post-election costing packs (pdftotext -layout) into leaf funding items, and tag each to 2022 electorates.
usage: python3 commit_parse_2022.py alp|lnp"""
import re, sys, json, collections, importlib.util
import pandas as pd
R = '/'.join(__file__.split('/')[:-3]); P = sys.argv[1]
spec = importlib.util.spec_from_file_location('tg', f'{R}/data/analysis/commit_tag_2026.py')
src = open(f'{R}/data/analysis/commit_tag_2026.py').read().split("c = pd.read_csv")[0]     # reuse the place dictionary + amount()
ns = {'__file__': f'{R}/data/analysis/commit_tag_2026.py'}; exec(compile(src.replace("Y = sys.argv[1] if len(sys.argv) > 1 else '2026'", "Y='2022'"), 'tg', 'exec'), ns)
pat, names, dnames, amount = ns['pat'], ns['names'], ns['dnames'], ns['amount']
txt = open(f'{R}/data/commitments/{P}2022_costings.txt').read()
blocks = re.split(r'\n\s*Publicly-announced policy costing\s*\n', txt)
items = []
for b in blocks[1:]:
    title = b.strip().split('\n')[0].strip()
    m = re.search(r'Policy summary\s+(.*?)\n(?:Election commitment|Budget baseline)', b, re.S)
    if not m: continue
    lines = [l.rstrip() for l in m.group(1).split('\n')]
    # rebuild bullets: '▪' level 0, '–' level 1; continuation lines join the previous bullet
    buls, head = [], []
    for l in lines:
        s = l.strip()
        if s.startswith('▪'): buls.append([0, s[1:].strip()])
        elif s.startswith('–'): buls.append([1, s[1:].strip()])
        elif buls: buls[-1][1] += ' ' + s
        else: head.append(s)
    leaves = []
    for i, (lv, t) in enumerate(buls):
        has_kids = lv == 0 and i + 1 < len(buls) and buls[i + 1][0] == 1
        if not has_kids: leaves.append(t)
    if not leaves: leaves = [' '.join(head)]
    for t in leaves:
        t = re.sub(r'\s+', ' ', t)
        hits = []
        for mm in pat.finditer(t):
            if not mm.group(1)[0].isupper(): continue
            k = mm.group(1).lower()
            if k not in hits and not any(k in h for h in hits): hits.append(k)
        dn = [k for k in hits if k in dnames]
        if dn: hits = dn
        w = collections.Counter()
        for k in hits:
            for d, f in names[k].items(): w[d] += f / len(hits)
        items.append(dict(party=P.upper(), policy=title, item=t, amount=amount(t), places='; '.join(hits), districts=json.dumps({d: round(f, 3) for d, f in w.items()})))
o = pd.DataFrame(items); o.to_csv(f'{R}/data/commitments/pbo_2022_{P}_items_tagged.csv', index=False)
loc = o[o.places != '']
print(P, 'policies', o.policy.nunique(), 'items', len(o), 'placed', len(loc), 'placed with $', loc.amount.notna().sum(), 'placed $m', round(loc.amount.sum() / 1e6))
print(loc.sample(min(15, len(loc)), random_state=2)[['amount', 'places', 'item']].to_string(max_colwidth=75))
