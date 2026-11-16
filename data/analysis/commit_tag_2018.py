"""Tag PBO 2018 election commitments to 2018 districts by place names, and extract dollar amounts."""
import re, sqlite3, collections, json
import pandas as pd
R = '/'.join(__file__.split('/')[:-3])
db = sqlite3.connect(f'{R}/data/elections.sqlite')
c = pd.read_csv(f'{R}/data/commitments/pbo_commitments_2018.csv')
dist = dict(db.execute("select contest_id, contest_name from contests where election_id='vic2018' and house in ('LA','lower','Assembly') or (election_id='vic2018' and contest_id like 'vic-%')").fetchall())
dist = {k: v.replace(' District', '').strip() for k, v in dist.items() if k.startswith('vic-')}
# suburb -> districts, from where the 2018 booths sat (venue suburb)
import gzip
bj = json.load(gzip.open(f'{R}/site/data/booths.json.gz')); bt = pd.DataFrame(bj['rows'], columns=bj['cols'])
bt = bt[(bt.election_id == 'vic2018') & bt.venue_id.notna()]
ven = pd.read_sql('select venue_id, suburb from venues where venue_id is not null', db).drop_duplicates('venue_id')
m = bt.merge(ven, on='venue_id'); m['sub'] = m.suburb.str.strip()
sub2d = m.groupby('sub').contest_id.agg(lambda s: collections.Counter(s)).to_dict()
names = {}
for cid, nm in dist.items(): names[nm.lower()] = {cid: 1}
for s, cnt in sub2d.items():
    if not isinstance(s, str) or len(s) < 4: continue
    k = s.lower()
    if k in names: continue          # district names win over suburb names
    tot = sum(cnt.values()); names[k] = {d: n / tot for d, n in cnt.items()}
# extra regional names
for city, ds in {'ballarat': ['vic-wendouree', 'vic-buninyong'], 'geelong': ['vic-geelong', 'vic-lara', 'vic-bellarine', 'vic-south-barwon'], 'bendigo': ['vic-bendigo-east', 'vic-bendigo-west'],
                 'latrobe valley': ['vic-morwell', 'vic-narracan'], 'frankston': ['vic-frankston'], 'shepparton': ['vic-shepparton'], 'mildura': ['vic-mildura'], 'wangaratta': ['vic-ovens-valley'], 'warrnambool': ['vic-south-west-coast'], 'traralgon': ['vic-morwell'], 'cranbourne': ['vic-cranbourne']}.items():
    ds = [d for d in ds if d in dist]
    if ds: names[city] = {d: 1 / len(ds) for d in ds}
# do not let generic words act as place names
STOP = {'park', 'central', 'east', 'west', 'north', 'south', 'city', 'hill', 'hills', 'lake', 'beach', 'point', 'bay', 'island', 'creek', 'river', 'valley', 'melbourne', 'victoria', 'state', 'heights', 'gardens', 'mount', 'port'}
keys = sorted([k for k in names if k not in STOP], key=len, reverse=True)
pat = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keys) + r')\b', re.I)
def amount(t):
    m_ = re.search(r'\$\s?([\d,.]+)\s*(b|bn|billion|m|million|k)?\b', t, re.I)
    if not m_: return None
    v = float(m_.group(1).replace(',', '')); u = (m_.group(2) or '').lower()
    return v * (1e9 if u in ('b', 'bn', 'billion') else 1e6 if u in ('m', 'million') else 1e3 if u == 'k' else 1)
rows = []
for _, r in c.iterrows():
    t = r.commitment; hits = []; used = ''
    for mm in pat.finditer(t):
        k = mm.group(1).lower()
        if any(k in u for u in used.split('|')): continue
        hits.append(k); used += '|' + k
    dn = [k for k in hits if k in {v.lower() for v in dist.values()}]
    if dn: hits = dn                  # an electorate named outright beats suburb names
    hits = [k for k in hits if not (k == 'reservoir' and 'reservoir site' in t.lower())]
    w = collections.Counter()
    for k in hits:
        for d, f in names[k].items(): w[d] += f / len(hits)
    rows.append(dict(date=r.date, party={'ALP Victoria': 'ALP', 'LNP Victoria': 'COAL', 'Victorian Greens': 'GRN'}[r.party], commitment=t, amount=amount(t), places='; '.join(hits), districts=json.dumps({dist[d]: round(f, 3) for d, f in w.items()})))
o = pd.DataFrame(rows); o.to_csv(f'{R}/data/commitments/pbo_commitments_2018_tagged.csv', index=False)
loc = o[o.places != '']
print('commitments', len(o), 'with a place', len(loc), 'with $ and place', loc.amount.notna().sum())
print(loc.groupby('party').agg(n=('commitment', 'size'), dollars=('amount', 'sum')))
print(loc.sample(25, random_state=3)[['party', 'amount', 'places', 'commitment']].to_string(max_colwidth=70))
