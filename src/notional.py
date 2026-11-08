"""Notional results: the last election's votes re-cut onto the new boundaries, for every redistribution in the Atlas.

  state    1999 on the 2001 districts (for 2002), 2010 on 2013 (for 2014), 2018 on 2022 (for 2022)
  federal  2007 on the 2010 divisions (for 2010), 2016 on 2018 (for 2019), 2019 on 2021 (for 2022), 2022 on 2024 (for 2025)

Method (in the spirit of the published notionals, done with the Atlas's own pieces):
  * Population is the yardstick. Census SA1s (2011, 2016 or 2021 edition, the nearest in time) are split by area
    across the old election's booth catchments and across the new boundaries; an SA1's people are assumed spread
    evenly over it.
  * Votes cast at an election-day booth follow its catchment: a booth whose catchment is 70% inside new seat A and 30%
    inside B (by population) sends 70% of its votes to A.
  * Every other vote of the old seat (postal, early, absent, provisional, booths with no location) follows the old
    seat's population: if 20% of the old seat's people are now in seat B, so are 20% of those votes.
  * Two-party preferred (Labor v Coalition) comes from the two-candidate counts where the final two was Labor v
    Coalition. Where it was not (v Greens, v independent), a booth's two-party vote is estimated from its first
    preferences, with flows fitted to the classic booths of the same election (Labor, Coalition, Greens, others);
    the share of each notional two-party vote that is estimated is recorded.

Outputs data/analysis/notionals.json: per redistribution, per new seat: notional first preferences by party and group,
two-party Labor share and margin, notional holder, where its people came from (old seat, share, holder, member),
and the actual result at the next election.
Usage  python3 -m src.notional
"""
import os, json, csv, re, sqlite3, math
from collections import defaultdict
import numpy as np
from shapely.geometry import shape
from shapely.strtree import STRtree
from shapely.validation import make_valid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUP = {'LIB': 'COAL', 'NAT': 'COAL', 'LCP': 'COAL', 'CLP': 'COAL'}
REDIST = [   # (old election, new election, old boundaries, new boundaries, SA1 edition)
    ('vic1999', 'vic2002', 'vic_la_1991', 'vic_la_2001', 2011),
    ('vic2010', 'vic2014', 'vic_la_2001', 'vic_la_2013', 2011),
    ('vic2018', 'vic2022', 'vic_la_2013', 'vic_la_2022', 2016),
    ('fed2007', 'fed2010', 'fed_2003', 'fed_2010', 2011),
    ('fed2016', 'fed2019', 'fed_2010', 'fed_2018', 2016),
    ('fed2019', 'fed2022', 'fed_2018', 'fed_2021', 2016),
    ('fed2022', 'fed2025', 'fed_2021', 'fed_2024', 2021)]
FLOW_GROUPS = ['ALP', 'COAL', 'GRN', 'OTH']


def geoms(path, key):
    g = json.load(open(path)); out = {}
    for f in g['features']:
        if not f.get('geometry'):
            continue
        s = shape(f['geometry'])
        if not s.is_valid:
            s = make_valid(s)
        out[f['properties'][key]] = s
    return out


def sa1_pop(year):
    if year == 2011:
        f, col, code = 'raw/abs/datapacks/csv/2011/2011Census_B01_VIC_SA1_short.csv', 'Tot_P_P', None
    else:
        f, col = f'raw/abs/datapacks/csv/{year}/{year}Census_G01_VIC_SA1.csv', 'Tot_P_P'
    pop = {}
    path = os.path.join(ROOT, f)
    if os.path.exists(path):
        fh = open(path)
    else:                                   # read straight from the DataPack zip if it has not been unpacked
        import glob, zipfile, io
        want = os.path.basename(f).replace('_short', '')
        for z in glob.glob(os.path.join(ROOT, f'raw/abs/datapacks/{year}_*SA1*.zip')):
            zf = zipfile.ZipFile(z)
            m = [n for n in zf.namelist() if os.path.basename(n).replace('_short', '') == want]
            if m:
                fh = io.TextIOWrapper(zf.open(m[0]), encoding='utf-8-sig'); break
        else:
            raise SystemExit(f'SA1 population table not found: {f} (or a {year} DataPack zip in raw/abs/datapacks/)')
    with fh:
        r = csv.reader(fh); hdr = next(r); i = hdr.index(col)
        for row in r:
            pop[row[0]] = float(row[i] or 0)
    return pop


def load_sa1(year):
    polys = geoms(os.path.join(ROOT, f'raw/boundaries/abs/sa1_{year}_vic.geojson'), 'sa1')
    pop = sa1_pop(year)
    if pop and all(len(k) == 7 for k in list(pop)[:50]):          # 2011/2016 DataPacks key by the 7-digit code
        pop = {m: pop.get(m[0] + m[5:11], 0.0) for m in polys}
    return polys, {k: pop.get(k, 0.0) for k in polys}


def split(polys, targets):
    """{poly_id: {target_id: share of poly's area}} (pieces under 0.5% dropped, renormalised)"""
    ids = list(targets); tree = STRtree([targets[i] for i in ids]); out = {}
    for pid, p in polys.items():
        a = p.area
        if a <= 0:
            continue
        w = {}
        for j in tree.query(p):
            t = targets[ids[j]]
            if t.contains(p):
                w = {ids[j]: 1.0}; break
            x = p.intersection(t).area / a
            if x > 0.005:
                w[ids[j]] = x
        s = sum(w.values())
        if s > 0:
            out[pid] = {k: v / s for k, v in w.items()}
    return out


def pop_matrix(sa1w_src, sa1w_new, pop):
    """{source_id: {new_id: people}} from SA1 shares of source areas and new seats"""
    M = defaultdict(lambda: defaultdict(float))
    for s, ws in sa1w_src.items():
        p = pop.get(s, 0)
        if p <= 0 or s not in sa1w_new:
            continue
        for src, a in ws.items():
            for new, b in sa1w_new[s].items():
                M[src][new] += p * a * b
    return M


def normalise(M):
    return {k: {n: v / sum(d.values()) for n, v in d.items()} for k, d in M.items() if sum(d.values()) > 0}


def votes(c, eid):
    party = {k: p for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (eid,))}
    fp = defaultdict(lambda: defaultdict(float)); tcp = defaultdict(lambda: defaultdict(float))
    for cid, bid, k, v in c.execute("select contest_id, booth_id, candidate_id, votes from fp_votes where election_id = ? and candidate_id <> 'INFORMAL'", (eid,)):
        fp[(cid, bid)][party.get(k, 'OTH') or 'OTH'] += v or 0
    for cid, bid, k, v in c.execute('select contest_id, booth_id, candidate_id, votes from tcp_votes where election_id = ?', (eid,)):
        tcp[(cid, bid)][GROUP.get(party.get(k), party.get(k)) or 'OTH'] += v or 0
    return fp, tcp


def grp(p):
    g = GROUP.get(p, p)
    return g if g in ('ALP', 'COAL', 'GRN') else 'OTH'


def fit_flows(fp, tcp, classic):
    """two-party Labor share = sum_g b_g * first-preference share_g, fitted on booths in Labor v Coalition contests"""
    X, y, w = [], [], []
    for key, f in fp.items():
        if key[0] not in classic or key not in tcp:
            continue
        t = tcp[key]; tot = sum(f.values()); tt = t.get('ALP', 0) + t.get('COAL', 0)
        if tot < 50 or tt <= 0:
            continue
        g = defaultdict(float)
        for p, v in f.items():
            g[grp(p)] += v / tot
        X.append([g[k] for k in FLOW_GROUPS]); y.append(t.get('ALP', 0) / tt); w.append(math.sqrt(tot))
    X, y, w = np.array(X), np.array(y), np.array(w)
    b, *_ = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)
    return dict(zip(FLOW_GROUPS, b)), float(np.sqrt(np.average((X @ b - y) ** 2, weights=w ** 2)))


def notional(c, t0, t1, old_set, new_set, year, sa1):
    polys, pop = sa1
    new = geoms(os.path.join(ROOT, f'data/boundaries/{new_set}.geojson'), 'contest_id')
    old = geoms(os.path.join(ROOT, f'data/boundaries/{old_set}.geojson'), 'contest_id')
    cat = geoms(os.path.join(ROOT, f'data/catchments/{t0}.geojson'), 'booth_id')
    w_new, w_old, w_cat = split(polys, new), split(polys, old), split(polys, cat)
    M_old = pop_matrix(w_old, w_new, pop); M_cat = pop_matrix(w_cat, w_new, pop)
    S_old, S_cat = normalise(M_old), normalise(M_cat)
    for b, g in cat.items():                 # unpopulated catchments: split by area instead
        if b not in S_cat:
            S_cat[b] = split({b: g}, new).get(b, {})
    name = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (t0,))}
    name1 = {cid: nm for cid, nm in c.execute('select contest_id, contest_name from contests where election_id = ?', (t1,))}
    bnames = {f['properties']['contest_id']: f['properties']['name'] for f in json.load(open(os.path.join(ROOT, f'data/boundaries/{new_set}.geojson')))['features']}
    for cid, nm in bnames.items():
        name1.setdefault(cid, nm)
    fp, tcp = votes(c, t0)
    pairs = defaultdict(set)
    for (cid, bid), t in tcp.items():
        pairs[cid] |= {k for k, v in t.items() if v > 0}
    classic = {cid for cid, p in pairs.items() if p == {'ALP', 'COAL'}}
    flows, rmse = fit_flows(fp, tcp, classic)
    # notional sums
    NF = defaultdict(lambda: defaultdict(float)); N2 = defaultdict(lambda: defaultdict(float)); comp = defaultdict(lambda: defaultdict(float))
    O2 = defaultdict(lambda: defaultdict(float))      # the old seats' own two-party result, by the same method
    by_contest = defaultdict(list)
    for (cid, bid) in fp:
        by_contest[cid].append(bid)
    for cid, bids in by_contest.items():
        for bid in bids:
            f = fp[(cid, bid)]; tot = sum(f.values())
            if tot <= 0:
                continue
            route = S_cat.get(bid) or S_old.get(cid) or {}
            if cid in classic and (cid, bid) in tcp:
                t = tcp[(cid, bid)]; tt = t.get('ALP', 0) + t.get('COAL', 0)
                alp = t.get('ALP', 0) / tt if tt else None
                est = alp is None
            else:
                est = True; alp = None
            if alp is None:
                g = defaultdict(float)
                for p, v in f.items():
                    g[grp(p)] += v / tot
                alp = min(1, max(0, sum(flows[k] * g[k] for k in FLOW_GROUPS)))
            O2[cid]['ALP'] += tot * alp; O2[cid]['COAL'] += tot * (1 - alp)
            for n, s in route.items():
                for p, v in f.items():
                    NF[n][p] += v * s
                N2[n]['ALP'] += tot * s * alp; N2[n]['COAL'] += tot * s * (1 - alp)
                N2[n]['est'] += tot * s * est
                comp[n][cid] += tot * s
    # winners at t0 and members
    win0 = {cid: (GROUP.get(p, p), f'{g} {s}') for cid, p, g, s in c.execute('select contest_id, party, given_name, surname from candidates where election_id = ? and elected = 1', (t0,))}
    win1 = {cid: GROUP.get(p, p) for cid, p in c.execute('select contest_id, party from candidates where election_id = ? and elected = 1', (t1,))}
    act = defaultdict(lambda: defaultdict(float))
    party1 = {k: p for k, p in c.execute('select candidate_id, party from candidates where election_id = ?', (t1,))}
    for cid, k, v in c.execute('select contest_id, candidate_id, sum(votes) from tcp_votes where election_id = ? group by 1, 2', (t1,)):
        act[cid][GROUP.get(party1.get(k), party1.get(k)) or 'OTH'] += v or 0
    seats = []
    for n in sorted(NF, key=lambda k: name1.get(k, k)):
        tot = sum(NF[n].values()); two = N2[n]['ALP'] + N2[n]['COAL']
        if tot <= 0:
            continue
        fps = {p: round(v / tot, 4) for p, v in sorted(NF[n].items(), key=lambda x: -x[1]) if v / tot >= 0.001}
        groups = defaultdict(float)
        for p, v in NF[n].items():
            groups[GROUP.get(p, p)] += v / tot
        alp = N2[n]['ALP'] / two
        src = sorted(((cid, v / sum(comp[n].values())) for cid, v in comp[n].items()), key=lambda x: -x[1])
        top_fp = sorted(groups.items(), key=lambda x: -x[1])
        # notional holder: the two-party winner, unless the largest source seat was won by a non-major party that is
        # still competitive (a Greens or independent seat, where two-party is not the contest)
        main_src = src[0][0]
        holder = 'ALP' if alp >= 0.5 else 'COAL'
        h0 = win0.get(main_src, (None,))[0]
        if h0 not in ('ALP', 'COAL') and src[0][1] > 0.5 and groups.get(h0, 0) > 0.2:
            holder = h0
        a1 = act.get(n, {}); a1t = sum(a1.values())
        seats.append({'contest_id': n, 'seat': name1.get(n, n), 'formal': round(tot), 'fp': fps, 'fp_group': {k: round(v, 4) for k, v in top_fp if v >= 0.001},
                      'alp_2pp': round(alp, 4), 'margin_2pp': round(abs(alp - 0.5), 4), 'holder': holder, 'estimated_share': round(N2[n]['est'] / two, 3),
                      'sources': [{'contest_id': cid, 'seat': name.get(cid, cid), 'share': round(s, 4), 'holder': win0.get(cid, (None, None))[0], 'member': win0.get(cid, (None, None))[1]} for cid, s in src if s >= 0.005],
                      'same_name_share': round(sum(s for cid, s in src if name.get(cid) == name1.get(n)), 4),
                      'actual_winner': win1.get(n), 'actual_alp_2cp': round(a1.get('ALP', 0) / a1t, 4) if a1t and set(a1) == {'ALP', 'COAL'} else None})
    # old seats that disappeared, and what share of each old seat stayed with its namesake
    abolished = sorted(nm for cid, nm in name.items() if nm not in set(name1.values()))
    created = sorted(nm for cid, nm in name1.items() if nm not in set(name.values()))
    print(f'{t0} on {new_set}: {len(seats)} seats, flows {", ".join(f"{k} {v:.2f}" for k, v in flows.items())} (rmse {rmse:.3f}); abolished {abolished}; new {created}')
    return {'from': t0, 'for': t1, 'old_boundaries': old_set, 'new_boundaries': new_set, 'sa1_edition': year, 'flows': {k: round(v, 3) for k, v in flows.items()},
            'flow_rmse': round(rmse, 4), 'abolished': abolished, 'created': created, 'seats': seats,
            'old_seats': {name.get(cid, cid): {'contest_id': cid, 'alp_2pp': round(d['ALP'] / (d['ALP'] + d['COAL']), 4), 'holder': win0.get(cid, (None, None))[0], 'member': win0.get(cid, (None, None))[1]}
                          for cid, d in O2.items() if d['ALP'] + d['COAL'] > 0}}


def main():
    c = sqlite3.connect(os.path.join(ROOT, 'data/elections.sqlite'))
    cache, out = {}, []
    for t0, t1, os_, ns, yr in REDIST:
        if yr not in cache:
            cache[yr] = load_sa1(yr)
            print(f'SA1 {yr}: {len(cache[yr][0])} areas, {sum(cache[yr][1].values()):,.0f} people')
        out.append(notional(c, t0, t1, os_, ns, yr, cache[yr]))
    json.dump({'method': __doc__.split('\n\n')[1].strip(), 'redistributions': out}, open(os.path.join(ROOT, 'data/analysis/notionals.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
