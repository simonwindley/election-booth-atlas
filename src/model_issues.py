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

Census inputs (2021 SA1 DataPack aggregated to districts and booth catchments, raw/abs/sa1_census_2021.json): adults by
age band (G04), household income bands (G33, with the poll's 2026 dollar thresholds deflated to 2021 by wage growth),
bachelor degree or higher of adults (G49 over G04), and dwelling tenure (G37, applied to people as an approximation;
the poll's "living with parents" group has no Census counterpart and is left out).

Adds indicators `issue_<question>_<measure>_<slug>` (shares 0-1, flagged `modelled: true`) to
site/data/demog_vic_la_2022.json.gz and (as extra columns) site/data/demog_booth_vic2022.json.gz, plus plain copies in
site/data_plain/ if that folder exists.
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


HI_BANDS = [('negative_nil_income', 0, 0), ('hi_1_149', 1, 150), ('hi_150_299', 150, 300), ('hi_300_399', 300, 400), ('hi_400_499', 400, 500), ('hi_500_649', 500, 650), ('hi_650_799', 650, 800),
            ('hi_800_999', 800, 1000), ('hi_1000_1249', 1000, 1250), ('hi_1250_1499', 1250, 1500), ('hi_1500_1749', 1500, 1750), ('hi_1750_1999', 1750, 2000), ('hi_2000_2499', 2000, 2500),
            ('hi_2500_2999', 2500, 3000), ('hi_3000_3499', 3000, 3500), ('hi_3500_3999', 3500, 4000), ('hi_4000_more', 4000, 6000)]


def census_shares(units):
    """units: {id: record with the mi_* model-input counts from src.load_sa1_census} -> ({id: group shares}, state shares)"""
    cut1, cut2 = 75000 / 52 / WAGE_2021_TO_2026, 150000 / 52 / WAGE_2021_TO_2026

    def frac_below(lo, hi, cut):
        if hi <= cut: return 1.0
        if lo >= cut: return 0.0
        return (cut - lo) / (hi - lo)
    out = {}
    for uid, r in units.items():
        y, m, o = r.get('mi_adults_18_34', 0), r.get('mi_adults_35_54', 0), r.get('mi_adults_55_plus', 0)
        adults = y + m + o
        if not adults:
            continue
        rec = {'18-34': y / adults, '35-54': m / adults, '55+': o / adults}
        tot = 0; b = [0, 0, 0]
        for band, lo, hi in HI_BANDS:
            n = r.get('mi_hhi_' + band, 0); tot += n
            f1 = frac_below(lo, hi, cut1); f2 = frac_below(lo, hi, cut2)
            b[0] += n * f1; b[1] += n * (f2 - f1); b[2] += n * (1 - f2)
        if tot:
            rec.update({'HHI less than $75k': b[0] / tot, 'HHI $75k-$150k': b[1] / tot, 'HHI over $150k': b[2] / tot})
        rec['Degree educated'] = min(1, r.get('mi_degree', 0) / adults); rec['No degree'] = 1 - rec['Degree educated']
        own, mort, rent = r.get('mi_tenure_own', 0), r.get('mi_tenure_mortgage', 0), r.get('mi_tenure_rent', 0)
        if own + mort + rent:
            s3 = own + mort + rent
            rec.update({'Homeowner (without mortgage)': own / s3, 'Homeowner (with mortgage)': mort / s3, 'Renting': rent / s3})
        rec['_adults'] = adults; rec['_households'] = tot
        out[uid] = rec
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


def model(waves, shares, state, units):
    """-> (indicator defs, {unit: {iid: value}}, state values, summary rows)"""
    inds, vals, sval, summary = [], {u: {} for u in units}, {}, []
    for key, q, m, group in QUESTIONS:
        level, d, have = gaps(waves, key)
        if not level:
            continue
        waves_used = ', '.join(w['fieldwork'] for w in have)
        for issue, T in sorted(level.items(), key=lambda kv: -kv[1]):
            shifts = {}
            for dim, groups in DIMS.items():
                shifts[dim] = [sum((shares[s].get(g, state[g]) - state[g]) * d.get((g, issue), 0) for g in groups) for s in units]
            dims = [k for k in shifts if any(abs(x) > 1e-9 for x in shifts[k])]
            rs = [corr(shifts[a], shifts[b]) for i, a in enumerate(dims) for b in dims[i + 1:]]
            rho = max(0.0, sum(rs) / len(rs)) if rs else 0.0
            wgt = 1 / (1 + (len(dims) - 1) * rho) if dims else 0
            iid = f'issue_{q}_{m}_{slug(issue)}'
            inds.append({'id': iid, 'group': group, 'label': issue, 'kind': 'share', 'modelled': True,
                         'note': f'Modelled from {have[-1]["firm"]} / {have[-1]["client"]} breakdowns ({waves_used}) and the 2021 Census mix; not a poll.'})
            sval[iid] = T / 100
            vs = []
            for i, s in enumerate(units):
                v = max(0.0, T + wgt * sum(shifts[k][i] for k in dims))
                vals[s][iid] = round(v / 100, 4); vs.append(v)
            summary.append((iid, T, min(vs), max(vs), round(rho, 2)))
    return inds, vals, sval, summary


def main():
    polls = json.load(open(os.path.join(ROOT, 'site/data/polls_vic2026.json')))
    waves = polls['issues']['waves']
    c21 = json.load(open(os.path.join(ROOT, 'raw/abs/sa1_census_2021.json')))
    method = {'source': polls['issues']['source'], 'dimensions': list(DIMS), 'wage_deflator': WAGE_2021_TO_2026,
              'method': 'Group gaps from the pollster\'s one-way breakdowns (pooled across waves), applied to each area\'s 2021 Census mix relative to the state, combined with an overlap correction, on the latest statewide level.'}
    # districts
    path = os.path.join(ROOT, 'site/data/demog_vic_la_2022.json.gz')
    D = json.load(gzip.open(path))
    D['indicators'] = [x for x in D['indicators'] if not x['id'].startswith('issue_')]
    for rec in list(D['districts'].values()) + [D['state']]:
        for k in [k for k in rec if k.startswith('issue_')]:
            del rec[k]
    shares, state = census_shares(c21['districts'])
    seats = [cid for cid in D['districts'] if cid in shares]
    inds, vals, sval, summary = model(waves, shares, state, seats)
    D['indicators'] += inds; D['state'].update(sval)
    for s in seats:
        D['districts'][s].update(vals[s])
    D['issues_model'] = method
    with open(path, 'wb') as raw_fh, gzip.GzipFile(fileobj=raw_fh, mode='wb', mtime=0) as fh:   # mtime=0: unchanged data gives an unchanged file
        fh.write(json.dumps(D, separators=(',', ':')).encode())
    for iid, T, lo, hi, rho in summary:
        print(f'{iid:60s} state {T:5.1f}  seats {lo:5.1f}..{hi:5.1f}  rho {rho}')
    print(len(summary), 'modelled indicators ->', path)
    # booths (columnar file keyed by venue; the same state-level gaps applied to each catchment's mix)
    bpath = os.path.join(ROOT, 'site/data/demog_booth_vic2022.json.gz')
    if os.path.exists(bpath):
        B = json.load(gzip.open(bpath))
        keep = [i for i, c in enumerate(B['cols']) if not c.startswith('issue_')]
        B['cols'] = [B['cols'][i] for i in keep]; B['indicators'] = [x for x in B['indicators'] if not x['id'].startswith('issue_')]
        for rec in B['booths'].values():
            rec['v'] = [rec['v'][i] for i in keep]
        for k in [k for k in B['state'] if k.startswith('issue_')]:
            del B['state'][k]
        bshares, bstate = census_shares(c21['booths'])
        venues = [v for v in B['booths'] if v in bshares]
        binds, bvals, bsval, bsummary = model(waves, bshares, state, venues)   # the district-based state mix keeps booth and seat estimates on one footing
        B['indicators'] += binds; B['cols'] += [x['id'] for x in binds]; B['state'].update(bsval)
        for vid, rec in B['booths'].items():
            rec['v'] += [bvals.get(vid, {}).get(x['id']) for x in binds]
        B['issues_model'] = method
        with open(bpath, 'wb') as raw_fh, gzip.GzipFile(fileobj=raw_fh, mode='wb', mtime=0) as fh:
            fh.write(json.dumps(B, separators=(',', ':')).encode())
        lo = min(x[2] for x in bsummary); hi = max(x[3] for x in bsummary)
        print(f'{len(binds)} modelled indicators for {len(venues)} booth catchments (widest range {lo:.1f}..{hi:.1f}) -> {bpath}')
        plain = os.path.join(ROOT, 'site/data_plain')
        if os.path.isdir(plain):
            json.dump(B, open(os.path.join(plain, 'demog_booth_vic2022.json'), 'w'), separators=(',', ':'))
    plain = os.path.join(ROOT, 'site/data_plain')
    if os.path.isdir(plain):
        json.dump(D, open(os.path.join(plain, 'demog_vic_la_2022.json'), 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main()
