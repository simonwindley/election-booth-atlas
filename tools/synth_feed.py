"""A synthetic election-night feed for testing the 2026 pages: the 2022 results re-cast as a 2026 count, with a uniform
swing applied and only part of the vote in, in the live feed's format (site/data/live/latest.json).

    python3 tools/synth_feed.py OUT.json --swing-coal 4 --swing-grn 1 --reported 0.6 --pools early,postal --seed 1

--swing-coal / --swing-grn: points moved from Labor to the Coalition / the Greens at every booth (booths vary around it);
--reported: share of election-day booths reported; --pools: which non-booth pools have been counted; --tcp: fraction of
reported booths with a two-candidate count (same pair as 2022).
"""
import sys, os, json, gzip, random, argparse
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--swing-coal', type=float, default=3.0); ap.add_argument('--swing-grn', type=float, default=1.0)
    ap.add_argument('--reported', type=float, default=0.6); ap.add_argument('--pools', default='early'); ap.add_argument('--tcp', type=float, default=0.8); ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--noise', type=float, default=3.0, help='sd of the booth-level swing around the uniform swing, points')
    a = ap.parse_args(); random.seed(a.seed)
    def gz(n): return json.load(gzip.open(os.path.join(ROOT, 'site/data', n + '.json.gz')))
    cand = gz('candidates'); C = [dict(zip(cand['cols'], r)) for r in cand['rows'] if r[0] == 'vic2022']
    bo = gz('booths'); B = [dict(zip(bo['cols'], r)) for r in bo['rows'] if r[0] == 'vic2022']
    fp = gz('fp'); FP = defaultdict(dict)
    for e, b, c, v in fp['rows']:
        if e == 'vic2022': FP[b][c] = v
    tc = gz('tcp'); TCP = defaultdict(dict)
    for r in tc['rows']:
        r = dict(zip(tc['cols'], r))
        if r['election_id'] == 'vic2022': TCP[r['booth_id']][r['candidate_id']] = r['votes']
    ct = gz('contests'); CT = {r[1]: dict(zip(ct['cols'], r)) for r in ct['rows'] if r[0] == 'vic2022'}
    pools = set(a.pools.split(',')) if a.pools else set()
    byC = defaultdict(list)
    for c in C: byC[c['contest_id']].append(c)
    out = {'election_id': 'vic2026', 'base': 'synthetic', 'fetched_at': '2026-11-28T09:30:00+00:00', 'contests': {}, 'n_changed_booths': 0, 'n_changed_contests': 0}
    grp = lambda p: 'COAL' if p in ('LIB', 'NAT') else p
    for cid, cands in byC.items():
        if CT.get(cid, {}).get('house') == 'LC': continue
        booths = [b for b in B if b['contest_id'] == cid]
        if not booths: continue
        lc = {'contest_id': cid, 'name': CT[cid]['contest_name'], 'election_id': 'vic2026', 'enrolment': CT[cid].get('enrolment'), 'candidates': [], 'final_pair': [], 'tcp_total': [], 'tpp': [], 'tcp_pair': [], 'booths': {}, 'dop': [], 'stage': 'First preference count', 'elected': None, 'updated_at': out['fetched_at'], 'first_seen': out['fetched_at']}
        for c in cands:
            lc['candidates'].append({'candidate_id': c['candidate_id'], 'name': f"{c['surname'].upper()}, {c['given_name']}", 'surname': c['surname'], 'given_name': c['given_name'], 'party_name': c['party_name'], 'party': c['party'], 'ballot_position': c['ballot_position'], 'fp_votes': 0, 'elected': 0})
        pair = sorted(TCP[next((b['booth_id'] for b in booths if TCP.get(b['booth_id'])), '')].keys()) if any(TCP.get(b['booth_id']) for b in booths) else []
        lc['tcp_pair'] = pair
        by_type = defaultdict(int); n_ord = n_rep = 0; tot = {}; informal = 0; tcp_tot = defaultdict(int)
        for b in booths:
            row = FP.get(b['booth_id'], {}); f = {k: v for k, v in row.items() if k != 'INFORMAL'}
            if not f: continue
            is_ord = b['booth_type'] == 'ordinary'
            if is_ord: n_ord += 1
            reported = (random.random() < a.reported) if is_ord else (b['booth_type'] in pools)
            entry = {'booth_id': b['booth_id'], 'name': b['booth_name'], 'type': b['booth_type'], 'fp': {}, 'informal': row.get('INFORMAL', 0), 'total': 0, 'tcp': {}, 'reported': reported, 'sig': 'synth', 'updated_at': out['fetched_at'], 'first_seen': out['fetched_at']}
            if reported:
                if is_ord: n_rep += 1
                formal = sum(f.values()); sc = (a.swing_coal + random.gauss(0, a.noise)) / 100 if is_ord else a.swing_coal / 100; sg = (a.swing_grn + random.gauss(0, a.noise / 2)) / 100 if is_ord else a.swing_grn / 100
                g = defaultdict(float)
                for c in cands:
                    g[grp(c['party'])] += f.get(c['candidate_id'], 0)
                # move votes: Labor -> Coalition and Labor -> Greens, scaled to the booth
                newf = {}
                for c in cands:
                    v = f.get(c['candidate_id'], 0); G = grp(c['party'])
                    if G == 'ALP': v -= formal * (sc + sg)
                    elif G == 'COAL' and g['COAL'] > 0: v += formal * sc * v / g['COAL']
                    elif G == 'GRN' and g['GRN'] > 0: v += formal * sg * v / g['GRN']
                    newf[c['candidate_id']] = max(0, int(round(v)))
                entry['fp'] = newf; entry['total'] = sum(newf.values()) + entry['informal']
                for k, v in newf.items(): tot[k] = tot.get(k, 0) + v
                by_type[b['booth_type']] += sum(newf.values()); informal += entry['informal']
                t = TCP.get(b['booth_id'])
                if t and pair and (random.random() < a.tcp or not is_ord):
                    tt = sum(t.values()); shift = sum(newf.values()) - formal
                    # keep the 2022 booth 2CP, shifted by the swing between the pair's party groups
                    pg = [grp(next(c['party'] for c in cands if c['candidate_id'] == k)) for k in pair]
                    sh = {k: t[k] / tt for k in pair}
                    if 'COAL' in pg and 'ALP' in pg: sh[pair[pg.index('COAL')]] += sc; sh[pair[pg.index('ALP')]] -= sc
                    elif 'GRN' in pg and 'ALP' in pg: sh[pair[pg.index('GRN')]] += sg; sh[pair[pg.index('ALP')]] -= sg
                    for k in pair: sh[k] = min(0.95, max(0.05, sh[k]))
                    s2 = sum(sh.values()); newtot = sum(newf.values())
                    entry['tcp'] = {k: int(round(newtot * sh[k] / s2)) for k in pair}
                    for k in pair: tcp_tot[k] += entry['tcp'][k]
            lc['booths'][b['booth_id']] = entry
        for c in lc['candidates']: c['fp_votes'] = tot.get(c['candidate_id'], 0)
        formal = sum(tot.values())
        for c in lc['candidates']: c['pct'] = f"{100 * c['fp_votes'] / formal:.2f}%" if formal else '0%'
        lc['formal'] = formal; lc['informal'] = informal; lc['total_votes'] = formal + informal
        lc['tcp_total'] = [{'candidate_id': k, 'votes': v, 'pct': ''} for k, v in tcp_tot.items()]
        lc['counted'] = {'by_type': dict(by_type), 'booths_reported': n_rep, 'booths_listed': n_ord, 'pct_enrolment': round(100 * (formal + informal) / CT[cid]['enrolment'], 1) if CT[cid].get('enrolment') else None}
        out['contests'][cid] = lc
    json.dump(out, open(a.out, 'w'))
    print(f"{len(out['contests'])} electorates; booths reported {sum(c['counted']['booths_reported'] for c in out['contests'].values())} of {sum(c['counted']['booths_listed'] for c in out['contests'].values())}")


if __name__ == '__main__':
    main()
