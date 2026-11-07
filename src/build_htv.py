"""Site data for the how-to-vote cards: the card orders per seat, how far each party's voters followed their card
(from src.htv_follow), and each party's typical ordering of the other parties, which the browser model needs to
apply a changed 2026 card relative to a no-card baseline.

    python3 -m src.build_htv vic2022     -> site/data/htv_vic2022.json
    python3 -m src.build_htv vic2026     -> site/data/htv_vic2026.json  (orders only; follow rates come from 2022)
"""
import os, sys, json, gzip
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.pref_flows import KEEP  # noqa: E402

# follow rates that the 2022 regression cannot identify (cards that never varied within the election):
# the Liberal figure is the 2018->2022 natural experiment (Liberal cards moved the Greens from below to above
# Labor and the Liberal pile's Greens share rose by about 22 points); Labor/Nationals are assumed at the same level.
ASSUMED = {'LIB': (0.22, 'Liberal cards swapped Labor and the Greens between 2018 and 2022; the Liberal pile moved 22 points'),
           'NAT': (0.22, 'assumed the same as Liberal voters'), 'ALP': (0.3, 'assumed; Labor cards did not vary within 2022')}


def mparty(p):
    return p if p in KEEP else 'OTH'


def main(eid):
    cards = json.load(open(os.path.join(ROOT, f'raw/htv/cards_{eid}.json')))['cards']
    c = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz')))
    cands = {r[2]: dict(zip(c['cols'], r)) for r in c['rows'] if r[0] == eid}
    if eid == 'vic2026' and not cands:
        c26 = json.load(gzip.open(os.path.join(ROOT, 'site/data/c2026_candidates.json.gz')))
        cands = {r[c26['cols'].index('candidate_id')]: dict(zip(c26['cols'], r)) for r in c26['rows']}
    out_cards = defaultdict(list)
    seen = set()
    for reg, e in sorted(cards.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        for cid, r in e['contests'].items():
            if r.get('status') != 'complete' or not r.get('owner'):
                continue
            key = (cid, r['owner'], tuple(r['order']))
            if key in seen:
                continue
            seen.add(key)
            out_cards[cid].append({'owner': r['owner'], 'party': r.get('party') or cands.get(r['owner'], {}).get('party'),
                                   'order': r['order'], 'reg': reg, 'registered': e.get('registered'), 'registrant': e.get('registrant')})
    # typical ordering of the other parties on each party's cards: mean rank of each destination party across seats
    pos = defaultdict(lambda: defaultdict(list))
    for cid, lst in out_cards.items():
        for card in lst:
            p = mparty(card['party'] or 'OTH')
            others = [mparty(cands[x]['party']) for x in card['order'] if x != card['owner'] and x in cands]
            n = len(others)
            seen_p = set()
            for i, q in enumerate(others):
                if q in seen_p:
                    continue
                seen_p.add(q)
                pos[p][q].append(i / max(1, n - 1))
    party_order = {}
    for p, d in pos.items():
        ranked = sorted(d.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        party_order[p] = [{'party': q, 'rank': round(sum(v) / len(v), 3), 'seats': len(v)} for q, v in ranked]
    # pairwise: of the party's cards naming both q1 and q2, how many put q1 above q2. The browser picks the usual card
    # pick among the parties still standing as the one its cards put above every other at least 75% of the time, and backs
    # that usual effect out of the fitted flow; independents' cards are personal, so they never get a 'usual' pick
    pw = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))
    for cid, lst in out_cards.items():
        for card in lst:
            p = mparty(card['party'] or 'OTH')
            if p in ('IND', 'OTH'):
                continue
            pos_q = {}
            for i, x in enumerate(card['order']):
                if x == card['owner'] or x not in cands:
                    continue
                q = mparty(cands[x]['party'])
                pos_q.setdefault(q, i)
            qs = list(pos_q)
            for q1 in qs:
                for q2 in qs:
                    if q1 != q2:
                        pw[p][q1][q2][1] += 1
                        if pos_q[q1] < pos_q[q2]:
                            pw[p][q1][q2][0] += 1
    pairwise = {p: {q1: {q2: v for q2, v in d.items()} for q1, d in dd.items()} for p, dd in pw.items()}
    consistent = {p: bool(lst) and p not in ('IND', 'OTH') for p, lst in party_order.items()}
    # the ordering the previous election's cards had, for running that election's flows on these cards: the same, except
    # that the 2018 Liberal and National cards put Labor ahead of the Greens (swapped on the 2022 cards)
    import copy
    party_order_prev = copy.deepcopy(party_order); pairwise_prev = copy.deepcopy(pairwise)
    if eid == 'vic2022':
        for p in ('LIB', 'NAT'):
            lst = party_order_prev.get(p)
            if lst:
                ia = next((i for i, x in enumerate(lst) if x['party'] == 'ALP'), None); ig = next((i for i, x in enumerate(lst) if x['party'] == 'GRN'), None)
                if ia is not None and ig is not None and ia > ig:
                    lst[ia], lst[ig] = lst[ig], lst[ia]
            d = pairwise_prev.get(p)
            if d and 'ALP' in d and 'GRN' in d.get('ALP', {}):
                n = d['ALP']['GRN'][1]; d['ALP']['GRN'] = [n, n]; d['GRN']['ALP'] = [0, n]
    out = {'election': eid, 'cards': dict(out_cards), 'party_order': party_order, 'party_order_prev': party_order_prev, 'consistent': consistent, 'pairwise': pairwise, 'pairwise_prev': pairwise_prev,
           'n_cards': sum(len(v) for v in out_cards.values()), 'n_seats': len(out_cards)}
    fpath = os.path.join(ROOT, f'raw/htv/follow_{eid}.json')
    if os.path.exists(fpath):
        f = json.load(open(fpath))
        follow = {}
        for p, s in f['summary'].items():
            fr = s.get('follow')
            follow[p] = {'concordance': s['concordance'], 'lift': s['lift'], 'exclusions': s['exclusions'], 'votes': s['votes'],
                         'f': fr['f'] if fr else None, 'f_obs': fr['obs'] if fr else 0, 'f_seats': fr['seats'] if fr else 0, 'source': 'fitted' if fr else None}
        for p, (v, note) in ASSUMED.items():
            if p not in follow or follow[p]['f'] is None or follow[p]['f_seats'] < 5:
                follow.setdefault(p, {'concordance': None, 'lift': None, 'exclusions': 0, 'votes': 0, 'f_obs': 0, 'f_seats': 0})
                follow[p].update({'f': v, 'source': 'assumed', 'note': note})
        out['follow'] = follow
        out['follow_default'] = 0.25
        # seat-level concordance for the demographics work: per contest, per party of the excluded candidate
        seat = defaultdict(dict)
        for r in f['rows']:
            seat[r['contest']][r['party']] = {'conc': r['concordance'], 'lift': r['lift'], 'votes': r['votes'], 'pick': r['pick_party']}
        out['seat'] = dict(seat)
    json.dump(out, open(os.path.join(ROOT, f'site/data/htv_{eid}.json'), 'w'), separators=(',', ':'))
    print(f"{out['n_cards']} card orders in {out['n_seats']} seats; parties with a typical order: {list(party_order)}")
    for p, lst in party_order.items():
        print(f'  {p:4} ' + ' > '.join(x['party'] for x in lst[:8]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'vic2022')
