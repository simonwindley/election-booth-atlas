"""Tag PBO election commitments (2022 or 2026 trackers, 2022 boundaries) to electorates by place names; extract the headline dollar figure."""
import re, json, collections, sys
import pandas as pd
R = '/'.join(__file__.split('/')[:-3]); Y = sys.argv[1] if len(sys.argv) > 1 else '2026'
L = json.load(open(f'{R}/site/data/localities.json'))
D = L['d']                                                    # district slugs, e.g. 'albert-park'
names = {}
for x in L['s'].split('|'):
    i = x.rfind(':'); nm = x[:i].strip(); ds = ['vic-' + D[int(n)] for n in x[i + 1:].split(',')]
    names.setdefault(nm.lower(), {d: 1 / len(ds) for d in ds})
dnames = {}
for s in D: dnames[s.replace('-', ' ')] = 'vic-' + s
for k, v in dnames.items(): names[k] = {v: 1}               # electorate names win
for city, ds in {'ballarat': ['wendouree', 'eureka'], 'geelong': ['geelong', 'lara', 'bellarine', 'south-barwon'], 'bendigo': ['bendigo-east', 'bendigo-west'],
                 'latrobe valley': ['morwell', 'narracan'], 'wangaratta': ['ovens-valley'], 'warrnambool': ['south-west-coast'], 'traralgon': ['morwell'], 'wodonga': ['benambra'], 'mornington peninsula': ['nepean', 'mornington', 'hastings']}.items():
    ds = ['vic-' + d for d in ds if d in D]
    if ds: names[city] = {d: 1 / len(ds) for d in ds}
STOP = {'park', 'central', 'east', 'west', 'north', 'south', 'city', 'hill', 'hills', 'lake', 'beach', 'point', 'bay', 'island', 'creek', 'river', 'valley', 'melbourne', 'victoria', 'state', 'heights', 'gardens', 'mount', 'port', 'reservoir', 'kingston', 'clyde', 'research', 'bulla', 'golden square', 'wonga park', 'glen', 'french island', 'carrum', 'docklands' and None, 'regional', 'metropolitan', 'northern', 'southern', 'eastern', 'western'}
STOP.discard(None); STOP.discard(False)
keys = sorted([k for k in names if k not in STOP and len(k) >= 4], key=len, reverse=True)
pat = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keys) + r')\b', re.I)  # case checked per match
def amount(t):
    best = None
    for m in re.finditer(r'\$\s?([\d,.]+)\s*(billion|bn|b|million|m|k)?\b', t, re.I):
        v = float(m.group(1).replace(',', '') or 0); u = (m.group(2) or '').lower()
        v *= 1e9 if u in ('b', 'bn', 'billion') else 1e6 if u in ('m', 'million') else 1e3 if u == 'k' else 1
        best = v if best is None or v > best else best
    return best
c = pd.read_csv(f'{R}/data/commitments/pbo_commitments_{Y}.csv')
txtcol = [x for x in ('commitment', 'specification') if x in c]
P = {'Labor': 'ALP', 'Australian Labor Party': 'ALP', 'Libs–Nats': 'COAL', 'Liberals and Nationals': 'COAL', 'Greens': 'GRN', 'Australian Greens': 'GRN'}
rows = []
for _, r in c.iterrows():
    t = ' '.join(str(r[x]) for x in txtcol if pd.notna(r[x]))
    hits = []
    for m in pat.finditer(t):
        if not m.group(1)[0].isupper(): continue    # place names are capitalised: skip 'speed', 'sale'
        k = m.group(1).lower()
        if k not in hits and not any(k in h for h in hits): hits.append(k)
    dn = [k for k in hits if k in dnames]
    if dn: hits = dn
    w = collections.Counter()
    for k in hits:
        for d, f in names[k].items(): w[d] += f / len(hits)
    amt = amount(t)
    if amt is None and 'funding_announced_aud' in c and pd.notna(r.get('funding_announced_aud')): amt = float(r['funding_announced_aud'])
    rows.append(dict(date=r.date, party=P.get(r.party, r.party), commitment=r.commitment, amount=amt, places='; '.join(hits), districts=json.dumps({d: round(f, 3) for d, f in w.items()})))
o = pd.DataFrame(rows); o.to_csv(f'{R}/data/commitments/pbo_commitments_{Y}_tagged.csv', index=False)
loc = o[o.places != '']
print(Y, 'commitments', len(o), 'placed', len(loc), 'placed with $', loc.amount.notna().sum())
print(loc.groupby('party').agg(n=('commitment', 'size'), dollars_m=('amount', lambda s: round(s.sum() / 1e6))).to_string())
tot = collections.Counter()
for _, r in loc[loc.amount.notna() & loc.party.isin(['ALP', 'COAL'])].iterrows():
    for d, f in json.loads(r.districts).items(): tot[(d, r.party)] += r.amount * f / 1e6
seats = collections.Counter(); [seats.update({d: v}) for (d, p), v in tot.items()]
print('top seats by local $m (Labor + Coalition):', [(d.replace('vic-', ''), round(v)) for d, v in seats.most_common(12)])
print(loc.sample(15, random_state=5)[['party', 'amount', 'places', 'commitment']].to_string(max_colwidth=60))
