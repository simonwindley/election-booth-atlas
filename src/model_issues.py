"""Modelled issue priorities for each Victorian district (2022 boundaries, used again in 2026).

What it is: an estimate of how each seat would answer the Herald Sun / Freshwater Strategy issue questions,
given who lives there. It is built only from the pollster's published breakdowns (by age, household income,
degree and housing tenure) and the 2021 Census make-up of each district. It is NOT a poll of the seat: it cannot
see local issues, only the demographic mix.

Method (post-stratification on one-way margins):
  1. For each issue i and each group g (e.g. 18-34), the group's gap from everyone, pooled over all waves that asked
     the question, weighted by the group's sample size:  d[g,i] = sum_w n[g,w] (r[g,i,w] - T[i,w]) / sum_w n[g,w].
  2. For each dimension D (age, income, degree, tenure) and seat s, the shift implied by the seat's mix:
     shift[D,s,i] = sum_{g in D} (p[s,g] - p[state,g]) * d[g,i]  (p from the Census; differences from the state
     share, so the pollster's sample make-up cancels out).
  3. The dimensions overlap (older seats are also owner-occupier seats), so adding their shifts double-counts.
     The shifts are combined as  sum_D shift[D,s,i] * 1 / (1 + (k - 1) * rho), where k is the number of dimensions and
     rho the mean pairwise correlation of the shifts across seats for that issue: the effective number of
     independent dimensions. Uncorrelated dimensions add in full; dimensions that move together count once.
  4. The level is the latest wave's statewide figure:  est[s,i] = T[i,latest] + combined shift, floored at 0.

Census inputs (2021, SA2s apportioned to districts, raw/abs/c21_sa2_vic.json): adults by single year of age (G04),
household income bands (G33, with the poll's 2026 dollar thresholds deflated to 2021 by wage growth), bachelor
degree or higher of adults (G49 over G04), and dwelling tenure (G37, applied to people as an approximation; the
poll's "living with parents" group has no Census counterpart and is left out).

Adds indicators `issue_<question>_<measure>_<slug>` (shares 0-1, flagged `modelled: true`) to
site/data/demog_vic_la_2022.json.gz (and its plain copy in site/data_plain/ if that folder exists).
Usage: python3 -m src.model_issues
"""
import json, gzip, os, re, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAGE_2021_TO_2026 = 1.18   # Wage Price Index growth, Sept 2021 to Sept 2026 (approx.): $75k in 2026 is about $63.6k in 2021 dollars
QUESTIONS = [('most', 'gov', 'most', 'Issue priority (modelled): single most important for the state government'),
             ('priority', 'gov', 'any', 'Issue priority (modelled): in the top three for the state government'),
             ('vote_issue', 'vote', 'any', 'Issues that will sway the vote (modelled): in the top three')]
DIMS = {'age': ['18-34', '35-54', '55+'], 'income': ['HHI less than $75k', 'HHI $75k-$150k', 'HHI over $150k'],
        'degree': ['Degree educated', 'No degree'], 'tenure': ['Homeowner (with mortgage)', 'Homeowner (without mortgage)', 'Renting']}
SKIP = {'Other', 'Unsure', 'Nothing', 'None of these'}
slug = lambda s: re.sub(r'[^a-z0-9]+', '_', s.lower().replace('&', 'and')).strip('_')[:40]


def census_shares():
    cap = json.load(open(os.path.join(ROOT, 'raw/abs/c21_sa2_vic.json')))
    cells = {}
    for g, t in cap['tables'].items():
        m = defaultdict(dict)
        for r in t['rows']:
            m[r[0]][tuple(r[1:-1])] = r[-1]
        cells[g] = m
    hind = cap['tables']['G33']['labels']['HIND']
    lo_hi = {}
    for c, name in hind.items():
        nums = [int(x.replace(',', '')) for x in re.findall(r'\$([\d,]+)', name)]
        if c in ('_T', '_N', '18'):
            continue
        if c == '1':
            lo_hi[c] = (0, 0)
        elif 'or more' in name:
            lo_hi[c] = (nums[0], nums[0] * 1.5)
        else:
            lo_hi[c] = (nums[0], nums[1] + 1)
    cut1, cut2 = 75000 / 52 / WAGE_2021_TO_2026, 150000 / 52 / WAGE_2021_TO_2026

    def frac_below(lo, hi, cut):
        if hi <= cut: return 1.0
        if lo >= cut: return 0.0
        return (cut - lo) / (hi - lo)
    out = {}
    adult_bands = [str(a) for a in range(18, 80)] + ['80_84', '85_89', '90_94', '95_99', 'GE100']
    for cid in cells['G04']:
        a = cells['G04'][cid]
        g = lambda keys: sum(a.get((k,), 0) for k in keys)
        y = g([str(x) for x in range(18, 35)]); m = g([str(x) for x in range(35, 55)]); o = g([str(x) for x in range(55, 80)] + ['80_84', '85_89', '90_94', '95_99', 'GE100'])
        adults = y + m + o
        if not adults:
            continue
        rec = {'18-34': y / adults, '35-54': m / adults, '55+': o / adults}
        inc = cells['G33'][cid]; tot = 0; b = [0, 0, 0]
        for c, (lo, hi) in lo_hi.items():
            n = inc.get((c, '_T'), 0); tot += n
            f1 = frac_below(lo, hi, cut1); f2 = frac_below(lo, hi, cut2)
            b[0] += n * f1; b[1] += n * (f2 - f1); b[2] += n * (1 - f2)
        if tot:
            rec.update({'HHI less than $75k': b[0] / tot, 'HHI $75k-$150k': b[1] / tot, 'HHI over $150k': b[2] / tot})
        q = cells['G49'][cid]; deg = sum(q.get((k,), 0) for k in ('1', '2', '3'))
        rec['Degree educated'] = min(1, deg / adults); rec['No degree'] = 1 - rec['Degree educated']
        t = cells['G37'][cid]; own, mort, rent = t.get(('1', '_T'), 0), t.get(('2', '_T'), 0), t.get(('R_T', '_T'), 0)
        if own + mort + rent:
            s3 = own + mort + rent
            rec.update({'Homeowner (without mortgage)': own / s3, 'Homeowner (with mortgage)': mort / s3, 'Renting': rent / s3})
        rec['_adults'] = adults; rec['_households'] = tot
        out[cid] = rec
    # state shares, weighted by adults (households for income and tenure)
    state = {}
    for dim, groups in DIMS.items():
        wkey = '_households' if dim in ('income', 'tenure') else '_adults'
        W = sum(r[wkey] for r in out.values() if groups[0] in r)
        for gname in groups:
            state[gname] = sum(r[gname] * r[wkey] for r in out.values() if gname in r) / W
    return out, state


def gaps(waves, key):
    """pooled group gaps from everyone, per issue, and the latest statewide level"""
    have = [w for w in waves if w.get(key)]
    if not have:
        return None, None, None
    latest = have[-1][key]
    level = {r['issue']: r['v'][0] for r in latest['rows'] if r['issue'] not in SKIP and r['v'][0] is not None}
    num, den = defaultdict(float), defaultdict(float)
    for w in have:
        T = w[key]; ci = {c: k for k, c in enumerate(T['cols'])}
        for r in T['rows']:
            if r['issue'] not in level:
                continue
            tot = r['v'][0]
            for dim, groups in DIMS.items():
                for gname in groups:
                    k = ci.get(gname)
                    if k is None or r['v'][k] is None:
                        continue
                    n = (T['n'][k] if k < len(T['n']) and T['n'][k] else 100)
                    num[(gname, r['issue'])] += n * (r['v'][k] - tot); den[(gname, r['issue'])] += n
    d = {kk: num[kk] / den[kk] for kk in num}
    return level, d, have


def corr(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return 0 if not sa or not sb else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def main():
    polls = json.load(open(os.path.join(ROOT, 'site/data/polls_vic2026.json')))
    waves = polls['issues']['waves']
    shares, state = census_shares()
    path = os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')
    D = json.load(gzip.open(path))
    D['indicators'] = [x for x in D['indicators'] if not x['id'].startswith('issue_')]
    for rec in list(D['districts'].values()) + [D['state']]:
        for k in [k for k in rec if k.startswith('issue_')]:
            del rec[k]
    seats = [cid for cid in D['districts'] if cid in shares]
    summary = []
    for key, q, m, group in QUESTIONS:
        level, d, have = gaps(waves, key)
        if not level:
            continue
        waves_used = ', '.join(w['fieldwork'] for w in have)
        for issue, T in sorted(level.items(), key=lambda kv: -kv[1]):
            shifts = {}
            for dim, groups in DIMS.items():
                shifts[dim] = [sum((shares[s].get(g, state[g]) - state[g]) * d.get((g, issue), 0) for g in groups) for s in seats]
            dims = [k for k in shifts if any(abs(x) > 1e-9 for x in shifts[k])]
            rs = [corr(shifts[a], shifts[b]) for i, a in enumerate(dims) for b in dims[i + 1:]]
            rho = max(0.0, sum(rs) / len(rs)) if rs else 0.0
            wgt = 1 / (1 + (len(dims) - 1) * rho) if dims else 0
            iid = f'issue_{q}_{m}_{slug(issue)}'
            D['indicators'].append({'id': iid, 'group': group, 'label': issue, 'kind': 'share', 'modelled': True,
                                    'note': f'Modelled from {have[-1]["firm"]} / {have[-1]["client"]} breakdowns ({waves_used}) and the 2021 Census mix of each seat; not a poll of the seat.'})
            D['state'][iid] = T / 100
            vals = []
            for i, s in enumerate(seats):
                v = max(0.0, T + wgt * sum(shifts[k][i] for k in dims))
                D['districts'][s][iid] = round(v / 100, 4); vals.append(v)
            summary.append((iid, T, min(vals), max(vals), round(rho, 2)))
    D['issues_model'] = {'source': polls['issues']['source'], 'dimensions': list(DIMS), 'wage_deflator': WAGE_2021_TO_2026,
                         'method': 'Group gaps from the pollster\'s one-way breakdowns (pooled across waves), applied to each seat\'s 2021 Census mix relative to the state, combined with an overlap correction, on the latest statewide level.'}
    with open(path, 'wb') as raw_fh, gzip.GzipFile(fileobj=raw_fh, mode='wb', mtime=0) as fh:   # mtime=0: unchanged data gives an unchanged file
        fh.write(json.dumps(D, separators=(',', ':')).encode())
    plain = os.path.join(ROOT, 'site/data_plain')
    if os.path.isdir(plain):
        json.dump(D, open(os.path.join(plain, 'demog_vic_la_2022.json'), 'w'), separators=(',', ':'))
    for iid, T, lo, hi, rho in summary:
        print(f'{iid:60s} state {T:5.1f}  seats {lo:5.1f}..{hi:5.1f}  rho {rho}')
    print(len(summary), 'modelled indicators ->', path)


if __name__ == '__main__':
    main()
