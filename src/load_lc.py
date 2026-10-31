"""Load VEC Legislative Council (upper house) results from the per-region spreadsheets.

Inputs (per region, from the VEC's Azure blob store):
  <Region>-Votes Received.xls            votes by voting centre x group/candidate (ATL + BTL)
  <Region>-Distribution of Preferences.xls  the STV count, count by count

Outputs (long CSVs in <out_dir>): lc_contests, lc_candidates, lc_votes, lc_dop.
LC booth ids reuse the Legislative Assembly ids (vic-<district>-<centre>) so they share venues.

Usage: python3 -m src.load_lc <year> <lc_dir> <out_dir>
"""
import sys, os, re, glob, warnings
import pandas as pd
from .parties import canon_from_name
from .load_vec import slug

warnings.filterwarnings('ignore')
DECL = {'absent': 'absent', 'early vote': 'early', 'marked as voted': 'marked_as_voted',
        'postal vote': 'postal', 'provisional': 'provisional'}


def s(v):
    return '' if pd.isna(v) else str(v).strip()


def num(v):
    if pd.isna(v) or s(v) == '':
        return 0
    try:
        return int(float(str(v).replace(',', '')))
    except ValueError:
        return 0


def parse_votes_received(path, eid, region, rid):
    df = pd.read_excel(path, header=None)
    rows = df.values.tolist()
    cands, votes = {}, []
    district = None
    cols = None  # list of (col_idx, group, party, candidate_or_ATL)
    for r in rows:
        label = s(r[0])
        if label.endswith(' District') and any('Group' in s(x) for x in r[1:]):
            district = label.replace(' District', '')
            cols = []
            for i, h in enumerate(r):
                h = s(h)
                if not h or i == 0:
                    continue
                parts = [p.strip() for p in h.split('\n')]
                if parts[0].startswith('Group') and len(parts) in (2, 3) and parts[-1] != 'TOTAL':
                    g = parts[0].replace('Group ', '')
                    cols.append((i, g, parts[1] if len(parts) == 3 else '', parts[-1]))
                elif parts[0] == 'Ungrouped' and len(parts) == 2:
                    cols.append((i, 'UG', '', parts[1]))
                elif parts[0].startswith('Total Informal'):
                    cols.append((i, None, None, 'INFORMAL'))
            for i, g, party, who in cols:
                if who in ('INFORMAL',):
                    continue
                key = (g, who)
                if key not in cands:
                    cands[key] = {'election_id': eid, 'contest_id': rid, 'candidate_id': f'{rid}-{g}-{slug(who)}',
                                  'group': g, 'party_name': party, 'party': canon_from_name(party) if party else 'IND',
                                  'name': who, 'is_atl': int(who == 'ATL')}
            continue
        if cols is None or not label:
            continue
        key = label.lower()
        if key.startswith('total') or key.startswith('district total') or key.startswith('region'):
            continue
        kind = DECL.get(key)
        did = f'vic-{slug(district)}'
        bid = f'{did}-{kind}' if kind else f'{did}-{slug(label)}'
        for i, g, party, who in cols:
            v = num(r[i]) if i < len(r) else 0
            cid = 'INFORMAL' if who == 'INFORMAL' else cands[(g, who)]['candidate_id']
            if v:
                votes.append({'election_id': eid, 'contest_id': rid, 'district_id': did, 'booth_id': bid,
                              'booth_type': kind or 'ordinary', 'candidate_id': cid, 'votes': v})
    return list(cands.values()), votes


def parse_distribution(path, eid, rid):
    df = pd.read_excel(path, header=None)
    rows = df.values.tolist()
    meta = {}
    for r in rows[:12]:
        t = s(r[0])
        for k, pat in [('vacancies', r'Election of (\d+)'), ('formal', r'Formal Ballot Papers[^\d]*([\d,]+)'),
                       ('informal', r'Informal Ballot Papers[^\d]*([\d,]+)'), ('quota', r'Quota:\s*([\d,]+)')]:
            m = re.search(pat, t)
            if m:
                meta[k] = int(m.group(1).replace(',', ''))
    hdr_i = next(i for i, r in enumerate(rows) if s(r[0]).startswith('Count') and 'No' in s(r[0]))
    hdr = rows[hdr_i]
    cand_cols = [(i, s(h)) for i, h in enumerate(hdr) if i >= 4 and s(h) and 'elected' not in s(h).lower()]
    elected_col = next((i for i, h in enumerate(hdr) if 'elected' in s(h).lower()), None)
    out = []
    i = hdr_i + 1
    count_no, desc, tv = None, None, None
    while i < len(rows):
        r = rows[i]
        if s(r[0]):
            try:
                count_no = int(float(r[0]))
            except ValueError:
                i += 1; continue
            desc, tv = s(r[1]), (float(r[2]) if s(r[2]) not in ('', 'nan') else None)
        sub = s(r[3])
        if count_no is not None and elected_col is not None and s(r[elected_col]) not in ('', 'nan'):
            names = [c for _, c in cand_cols]
            cell = s(r[elected_col])
            for who in sorted(names, key=len, reverse=True):
                if who in cell:
                    cell = cell.replace(who, '')
                    out.append({'election_id': eid, 'contest_id': rid, 'count_no': count_no, 'description': desc,
                                'transfer_value': tv, 'column': who, 'field': 'elected', 'amount': 1.0})
        if count_no is not None and (sub in ('BPs', 'Value', 'PTotal') or desc == '1st Preferences'):
            field = {'BPs': 'ballot_papers', 'Value': 'value', 'PTotal': 'progressive_total', '': 'progressive_total'}[sub]
            for ci, cname in cand_cols:
                v = r[ci] if ci < len(r) else None
                if s(v) in ('', 'nan'):
                    continue
                out.append({'election_id': eid, 'contest_id': rid, 'count_no': count_no, 'description': desc,
                            'transfer_value': tv, 'column': cname, 'field': field, 'amount': float(v)})
        i += 1
    d = pd.DataFrame(out)
    if len(d):
        d = d.pivot_table(index=['election_id', 'contest_id', 'count_no', 'description', 'transfer_value', 'column'],
                          columns='field', values='amount', aggfunc='first').reset_index()
    return meta, d


def load(year, lc_dir, out):
    eid = f'vic{year}'
    contests, cands, votes, dops = [], [], [], []
    for vr in sorted(glob.glob(f'{lc_dir}/*Votes*Received*.xls')):
        base = os.path.basename(vr)
        if '-Votes Received' in base:   # 2022 naming: "<Region> Region-Votes Received.xls"
            region = base.split('-Votes')[0].replace(' Region', '')
            dist = vr.replace('Votes Received', 'Distribution of Preferences')
        else:                           # 2018 naming: "<Region>RegionVotesReceived.xls"
            region = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base.replace('RegionVotesReceived.xls', ''))
            dist = vr.replace('VotesReceived', 'Distributions')
        rid = f'vicr-{slug(region)}'
        c, v = parse_votes_received(vr, eid, region, rid)
        meta, d = parse_distribution(dist, eid, rid)
        contests.append({'election_id': eid, 'contest_id': rid, 'contest_name': region, 'house': 'LC', **meta})
        cands += c; votes += v; dops.append(d)
        print(f'{region}: {len(c)} candidate columns, {len(v)} vote rows, {d.count_no.max() if len(d) else 0} counts')
    os.makedirs(out, exist_ok=True)
    pd.DataFrame(contests).to_csv(f'{out}/lc_contests.csv', index=False)
    pd.DataFrame(cands).to_csv(f'{out}/lc_candidates.csv', index=False)
    pd.DataFrame(votes).to_csv(f'{out}/lc_votes.csv', index=False)
    pd.concat(dops, ignore_index=True).to_csv(f'{out}/lc_dop.csv', index=False)


if __name__ == '__main__':
    load(*sys.argv[1:4])
