"""Load the 2006 and 2010 Legislative Council results (the old VEC spreadsheets) into the lc_* tables.

2010: <Region>RegionVotesDetails.xls (votes by voting centre x group/candidate, with ATL) + the STV count.
2006: <Region>RegionDistributions.xls only for the totals (first preferences by candidate, the STV count);
      the parties come from <Region>RegionFPVbyVC.xls. The 2006 files carry no group letters or above/below
      the line split, so groups are lettered in ballot order by consecutive party, and lc_votes holds one
      region-total row per candidate (booth_type 'region').
2014 has the same files as 2018: use src.load_lc.

Usage: python3 -m src.load_lc_old <year> raw/vec/<year>/legislative_council data/vic<year>
"""
import sys, os, re, glob, warnings
import pandas as pd
from .parties import canon_from_name
from .load_vec import slug
from .load_lc import parse_distribution, s, num

warnings.filterwarnings('ignore')
DECL = {'absent': 'absent', 'early vote': 'early', 'marked as voted': 'marked_as_voted', 'postal vote': 'postal',
        'provisional': 'provisional', 'unenrolled': 'provisional'}
NAMES = {'SouthEasternMetropolitan': 'South-Eastern Metropolitan'}


def region_of(base, year):
    raw = re.sub(rf'^state{year}', '', base).split('Region')[0]
    return NAMES.get(raw, re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw))


def cand_name(cell):
    """'LA MANNA,\\nPat' -> 'LA MANNA, Pat'"""
    parts = [p.strip() for p in str(cell).split('\n') if p.strip()]
    return re.sub(r',\s*', ', ', ' '.join(parts)).strip()


def parse_votes_details(path, eid, rid):
    rows = pd.read_excel(path, header=None).values.tolist()
    cands, votes, cols, district = {}, [], None, None
    for r in rows:
        label = s(r[0])
        if label.upper().endswith(' DISTRICT') and any('GROUP' in s(x).upper() for x in r[1:]):
            district = label.title().replace(' District', '')
            cols = []
            for i, h in enumerate(r):
                h = s(h)
                if i == 0 or not h:
                    continue
                head, _, rest = h.partition('\n')
                m = re.match(r'GROUP ([A-Z]+)(?: - (.+))?$', head.strip())
                if m and rest.strip() and not rest.startswith('Total'):
                    g, party = m.group(1), (m.group(2) or '').strip()
                    who = 'ATL' if rest.strip() == 'ATL' else cand_name(rest)
                    cols.append((i, g, party, who))
                elif head.strip().upper().startswith('UNGROUPED') and rest.strip() and not rest.startswith('Total'):
                    cols.append((i, 'UG', '', cand_name(rest)))
                elif head.strip() == 'Informal':
                    cols.append((i, None, None, 'INFORMAL'))
            for i, g, party, who in cols:
                if who == 'INFORMAL':
                    continue
                key = (g, who)
                if key not in cands:
                    cands[key] = {'election_id': eid, 'contest_id': rid, 'candidate_id': f'{rid}-{g}-{slug(who)}', 'group': g,
                                  'party_name': party.title() if party else '', 'party': canon_from_name(party) if party else 'IND',
                                  'name': who, 'is_atl': int(who == 'ATL')}
            continue
        if cols is None or not label:
            continue
        key = label.lower()
        if key.startswith('total') or key.startswith('district total') or key.startswith('region total'):
            continue
        kind = DECL.get(key)
        did = f'vic-{slug(district)}'
        centre = re.sub(r'\s*\([^)]*District\)\s*$', '', label, flags=re.I)
        bid = f'{did}-{kind}' if kind else f'{did}-{slug(centre)}'
        for i, g, party, who in cols:
            v = num(r[i]) if i < len(r) else 0
            if v:
                cid = 'INFORMAL' if who == 'INFORMAL' else cands[(g, who)]['candidate_id']
                votes.append({'election_id': eid, 'contest_id': rid, 'district_id': did, 'booth_id': bid,
                              'booth_type': kind or 'ordinary', 'candidate_id': cid, 'votes': v})
    return list(cands.values()), votes


def ballot_2006(path):
    """(name, party) in ballot order, from the header of the votes-by-voting-centre sheet."""
    rows = pd.read_excel(path, header=None).values.tolist()[:12]
    score = lambda r: sum(1 for h in r if '\n' in s(h) and ',' in s(h).split('\n')[0])
    hdr = max(rows, key=score)
    out = []
    for h in hdr:
        h = s(h)
        if '\n' in h and ',' in h.split('\n')[0]:
            name, party = h.split('\n', 1)
            out.append((name.strip(), party.replace('\n', ' ').strip()))
    return out


def load(year, lc_dir, out):
    eid = f'vic{year}'
    contests, cands, votes, dops = [], [], [], []
    for dist in sorted(glob.glob(f'{lc_dir}/state{year}*RegionDistributions.xls')):
        base = os.path.basename(dist)
        region = region_of(base, year); rid = f'vicr-{slug(region)}'
        meta, d = parse_distribution(dist, eid, rid)
        if year == '2010':
            c, v = parse_votes_details(dist.replace('Distributions', 'VotesDetails'), eid, rid)
        else:
            ballot = ballot_2006(dist.replace('Distributions', 'FPVbyVC'))
            first = d[d.count_no == 1]
            nk = lambda x: re.sub(r'[^a-z]', '', x.lower())
            col_of = {nk(cn): cn for cn in first.column}
            c, v, g, prev = [], [], 0, None
            for bname, p in ballot:
                name = col_of.get(nk(bname), bname)
                if not p or p != prev:
                    g += 1
                prev = p if p else None
                letter = chr(64 + g) if g <= 26 else 'A' + chr(64 + g - 26)
                cid_ = f'{rid}-{letter}-{slug(name)}'
                c.append({'election_id': eid, 'contest_id': rid, 'candidate_id': cid_, 'group': letter, 'party_name': p.title() if p else '',
                          'party': canon_from_name(p) if p else 'IND', 'name': name, 'is_atl': 0})
                fp = first[first.column == name].progressive_total
                n = int(fp.iloc[0]) if len(fp) and not pd.isna(fp.iloc[0]) else 0
                if n:
                    v.append({'election_id': eid, 'contest_id': rid, 'district_id': '', 'booth_id': f'{rid}-all', 'booth_type': 'region', 'candidate_id': cid_, 'votes': n})
            if year != '2010':   # names in the count the header spelt differently: keep them, as their own group
                used = {x['name'] for x in c}
                for cn in pd.unique(first.column):
                    if cn in used or cn in ('Exhausted', 'TOTAL') or 'Fraction' in cn:
                        continue
                    fp = first[first.column == cn].progressive_total; n = int(fp.iloc[0]) if len(fp) and not pd.isna(fp.iloc[0]) else 0
                    if not n:
                        continue
                    g += 1; letter = chr(64 + g) if g <= 26 else 'A' + chr(64 + g - 26); cid_ = f'{rid}-{letter}-{slug(cn)}'
                    c.append({'election_id': eid, 'contest_id': rid, 'candidate_id': cid_, 'group': letter, 'party_name': '', 'party': 'IND', 'name': cn, 'is_atl': 0})
                    v.append({'election_id': eid, 'contest_id': rid, 'district_id': '', 'booth_id': f'{rid}-all', 'booth_type': 'region', 'candidate_id': cid_, 'votes': n})
                    print(f'  note: {cn} is in the count but not the ballot header')
        contests.append({'election_id': eid, 'contest_id': rid, 'contest_name': region, 'house': 'LC', **meta})
        cands += c; votes += v; dops.append(d)
        tot = sum(x['votes'] for x in v if x['candidate_id'] != 'INFORMAL')
        print(f'{region}: {len(c)} candidate columns, {len(v)} vote rows, {tot:,} formal (count says {meta.get("formal", 0):,}), {d.count_no.max() if len(d) else 0} counts')
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(contests).to_csv(f'{out}/lc_contests.csv', index=False)
    pd.DataFrame(cands).to_csv(f'{out}/lc_candidates.csv', index=False)
    pd.DataFrame(votes).to_csv(f'{out}/lc_votes.csv', index=False)
    pd.concat(dops, ignore_index=True).to_csv(f'{out}/lc_dop.csv', index=False)


if __name__ == '__main__':
    load(*sys.argv[1:4])
