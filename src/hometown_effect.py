"""The hometown (friends-and-neighbours) effect: how fast an independent's vote falls away with distance from home base.

For every independent who polled 10%+ in a Victorian Legislative Assembly or House of Representatives contest (1999-2026),
take the ordinary polling place where they did best (>=150 formal votes) as home base, then follow their share outwards.
Share at each booth is expressed relative to the candidate's own average over the seat's ordinary booths (1.0 = their average),
so a 30% independent and a 12% one sit on the same scale.

Controls (the whole point: some geographic gradient is there for anyone, because voters cluster):
  * major parties: the same procedure for the Labor, Liberal/National and Greens candidates in the same contests
  * placebo centres: each independent re-measured around a random booth instead of their peak
Peak booth itself is left out of every fit (it was chosen for being high).

Groups: urban (seat's booths median < 35 km from the Melbourne CBD) vs regional; incumbents (elected at the previous general
election at the same level, same name) vs challengers.

usage: python3 -m src.hometown_effect      -> data/analysis/hometown_effect.json, data/analysis/hometown_effect.png
"""
import os, json, math, random, sqlite3, statistics as st
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB = os.path.join(ROOT, 'data', 'elections.sqlite')
OUT = os.path.join(ROOT, 'data', 'analysis')
CBD = (-37.8136, 144.9631)
MIN_FORMAL, MIN_SHARE = 150, 0.10
BINS = [(0, 2), (2, 5), (5, 10), (10, 20), (20, 40), (40, 80), (80, 400)]
random.seed(20261112)


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def slope(pts):
    """OLS of ln(relative share) on ln(1 + km); pts = [(km, rel)] with rel > 0."""
    xs = [math.log1p(d) for d, r in pts]; ys = [math.log(r) for d, r in pts]
    if len(xs) < 6 or max(xs) - min(xs) < 0.5: return None
    mx, my = st.fmean(xs), st.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else None


def main():
    c = sqlite3.connect(DB)
    E = {e: (lvl, d) for e, lvl, d in c.execute('select election_id, level, date from elections')}
    formal = {(e, k): f for e, k, f in c.execute("select election_id, contest_id, formal from contests where house in ('LA','HoR')")}
    cands = {}
    for e, k, cid, sur, giv, party, el in c.execute('select election_id, contest_id, candidate_id, surname, given_name, party, elected from candidates'):
        if (e, k) in formal: cands[(e, cid)] = dict(e=e, k=k, cid=cid, name=f'{(giv or "").strip()} {(sur or "").strip().title()}'.strip(), party=party, elected=el)
    geo = {(e, b): (la, lo) for e, b, la, lo in c.execute("select election_id, booth_id, lat, lon from booth_geo where booth_type='ordinary' and lat is not null")}
    # votes per booth
    bv = defaultdict(dict); tot = defaultdict(int)
    for e, k, b, cid, v in c.execute('select election_id, contest_id, booth_id, candidate_id, votes from fp_votes'):
        if (e, k) not in formal: continue
        tot[(e, cid)] += v or 0
        if (e, b) in geo: bv[(e, k, b)][cid] = v or 0
    ctot = defaultdict(int)   # federal contests carry no formal total in the table: use the sum of first preferences
    for (e, cid), v in tot.items():
        if (e, cid) in cands: ctot[(e, cands[(e, cid)]['k'])] += v
    for key in formal:
        if not formal[key]: formal[key] = ctot.get(key, 0)
    booths_by_contest = defaultdict(list)
    for (e, k, b), d in bv.items():
        f = sum(d.values())
        if f >= MIN_FORMAL: booths_by_contest[(e, k)].append((b, f, d))
    # incumbency: elected at the previous general election of the same level, same name
    gens = {lvl: sorted([e for e, (l, d) in E.items() if l == lvl], key=lambda e: E[e][1]) for lvl in ('state', 'federal')}
    won = defaultdict(set)
    for (e, cid), x in cands.items():
        if x['elected']: won[e].add(x['name'].lower())
    def prev_gen(e):
        lvl, d = E[e]; base = 'state' if lvl.startswith('state') else 'federal'
        earlier = [g for g in gens[base] if E[g][1] < d]
        return earlier[-1] if earlier else None

    def measure(x, centre_mode='peak'):
        bl = booths_by_contest.get((x['e'], x['k']), [])
        if len(bl) < 8: return None
        sh = [(b, d.get(x['cid'], 0) / f, f) for b, f, d in bl]
        avg = sum(s * f for b, s, f in sh) / sum(f for b, s, f in sh)
        if avg <= 0: return None
        if centre_mode == 'peak': cb = max(sh, key=lambda t: t[1])[0]
        else: cb = random.choice(sh)[0]
        cpos = geo[(x['e'], cb)]
        pts = [(km(cpos, geo[(x['e'], b)]), s / avg) for b, s, f in sh if b != cb and s > 0]
        med_cbd = st.median(km(CBD, geo[(x['e'], b)]) for b, s, f in sh)
        return dict(slope=slope(pts), pts=pts, peak_rel=max(s for b, s, f in sh) / avg, avg=avg, urban=med_cbd < 35, centre=cb)

    rows, ctrl = [], defaultdict(list)
    for (e, cid), x in cands.items():
        share = tot[(e, cid)] / formal[(x['e'], x['k'])] if formal[(x['e'], x['k'])] else 0
        grp = {'IND': 'IND', 'ALP': 'ALP', 'LIB': 'COAL', 'NAT': 'COAL', 'LNP': 'COAL', 'GRN': 'GRN'}.get(x['party'])
        if not grp: continue
        if grp == 'IND' and share < MIN_SHARE: continue
        m = measure(x)
        if not m or m['slope'] is None: continue
        if grp == 'IND':
            pg = prev_gen(e); inc = bool(pg and x['name'].lower() in won[pg])
            plac = [measure(x, 'random') for _ in range(20)]; plac = [p['slope'] for p in plac if p and p['slope'] is not None]
            rows.append(dict(election=e, contest=x['k'], name=x['name'], share=round(share, 4), elected=bool(x['elected']), incumbent=inc, urban=m['urban'],
                             slope=round(m['slope'], 3), placebo_slope=round(st.median(plac), 3) if plac else None, peak_rel=round(m['peak_rel'], 2), pts=m['pts']))
        else:
            ctrl[grp].append(dict(slope=m['slope'], urban=m['urban'], pts=m['pts']))

    def curve(ptss):
        out = []
        for lo, hi in BINS:
            v = [r for pts in ptss for d, r in pts if lo <= d < hi]
            out.append(dict(bin=f'{lo}-{hi} km', n=len(v), median_rel=round(st.median(v), 3) if len(v) >= 20 else None))
        return out

    def summ(sl):
        sl = [s for s in sl if s is not None]
        if not sl: return None
        q = st.quantiles(sl, n=4) if len(sl) >= 4 else [min(sl), st.median(sl), max(sl)]
        return dict(n=len(sl), median_slope=round(st.median(sl), 3), iqr=[round(q[0], 3), round(q[-1], 3)])

    groups = {}
    for lab, sel in [('independents, all', lambda r: True), ('independents, urban', lambda r: r['urban']), ('independents, regional', lambda r: not r['urban']),
                     ('independents, incumbent', lambda r: r['incumbent']), ('independents, challenger', lambda r: not r['incumbent']),
                     ('independents, won', lambda r: r['elected']), ('independents, 20%+', lambda r: r['share'] >= 0.2)]:
        rs = [r for r in rows if sel(r)]
        groups[lab] = dict(slopes=summ([r['slope'] for r in rs]), placebo=summ([r['placebo_slope'] for r in rs]), curve=curve([r['pts'] for r in rs]))
    for g, lst in ctrl.items():
        for lab, sel in [('all', lambda r: True), ('urban', lambda r: r['urban']), ('regional', lambda r: not r['urban'])]:
            rs = [r for r in lst if sel(r)]
            groups[f'{g}, {lab}'] = dict(slopes=summ([r['slope'] for r in rs]), curve=curve([r['pts'] for r in rs]))
    os.makedirs(OUT, exist_ok=True)
    res = dict(about=__doc__.strip().split('\n\n')[0], method='slope = OLS of ln(booth share / own seat average) on ln(1 + km from peak booth), peak excluded; more negative = steeper fall-off.',
               min_share=MIN_SHARE, min_booth_formal=MIN_FORMAL, groups=groups,
               candidates=sorted([{k: v for k, v in r.items() if k != 'pts'} for r in rows], key=lambda r: r['slope']))
    json.dump(res, open(os.path.join(OUT, 'hometown_effect.json'), 'w'), indent=1)
    print(f'{len(rows)} independents (10%+); controls ' + ', '.join(f'{g} {len(v)}' for g, v in ctrl.items()))
    for k, v in groups.items():
        s = v['slopes']; p = v.get('placebo')
        print(f'{k:30s} n={s["n"] if s else 0:4d} slope {s["median_slope"] if s else "-":>7} IQR {s["iqr"] if s else ""}' + (f'  placebo {p["median_slope"]}' if p else ''))
        print('   ' + '  '.join(f'{b["bin"]}:{b["median_rel"]}' for b in v['curve']))
    return res, rows, ctrl


if __name__ == '__main__':
    main()
