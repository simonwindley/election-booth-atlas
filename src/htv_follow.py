"""How closely did each party's voters follow its how-to-vote card? Cards (parsed by tools/parse_htv.py) against
the actual distribution of preferences, exclusion by exclusion.

For every exclusion in a count, the excluded candidate's card (their party's registered card for that district, or
their own if independent) says who should get the pile next: the first name on the card still in the count. The
share that actually went there is the card's concordance. Concordance overstates following - many voters would
have gone there anyway - so two further measures are kept:

 * lift: concordance minus what the party-level flow model (fitted on the same election, no cards) expects for
   that destination party, i.e. how much better the card's pick did than the average pile from that party.
 * follow rate: a fixed-effects regression across exclusions. For each remaining candidate r in an exclusion of
   X: share to r = a[party(X), party(r)] + f[party(X)] * [r is the card's pick] + noise. The pair effects soak up
   the natural affinity between parties, so f is identified only where cards from the same party point different
   ways in different seats (independents, minor parties; the majors mostly do not vary within one election).

Usage: python3 -m src.htv_follow vic2022   -> raw/htv/follow_vic2022.json, site/data/htv_vic2022.json
"""
import os, sys, json, gzip
from collections import defaultdict, Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.pref_flows import KEEP  # noqa: E402


def load(eid):
    d = json.load(gzip.open(os.path.join(ROOT, 'site/data/dop.json.gz')))
    rows = [dict(zip(d['cols'], r)) for r in d['rows'] if r[0] == eid]
    c = json.load(gzip.open(os.path.join(ROOT, 'site/data/candidates.json.gz')))
    cands = {r[2]: dict(zip(c['cols'], r)) for r in c['rows'] if r[0] == eid}
    cards = json.load(open(os.path.join(ROOT, f'raw/htv/cards_{eid}.json')))['cards']
    pf = json.load(open(os.path.join(ROOT, 'site/data/pref_flows.json')))
    W = pf['per_election'].get(eid, {}).get('weights', {})
    return rows, cands, cards, W


def mparty(p):
    return p if p in KEEP else 'OTH'


def card_orders(cards, cands):
    """{(contest, owner candidate_id): [order lists]} from complete cards"""
    out = defaultdict(list)
    for reg, e in cards.items():
        for cid, r in e['contests'].items():
            if r.get('status') == 'complete' and r.get('owner'):
                out[(cid, r['owner'])].append((reg, r['order']))
    return out


def exclusions(rows, cands):
    by = defaultdict(list)
    for r in rows:
        by[(r['contest_id'], r['count_no'])].append(r)
    for (cid, cn), rs in sorted(by.items()):
        if cn == 0:
            continue
        exc = [r for r in rs if r['transfer'] < 0]
        if len(exc) != 1:
            continue
        x = exc[0]['candidate_id']
        out = -exc[0]['transfer']
        remaining = [r['candidate_id'] for r in rs if r['candidate_id'] != x and r['progressive_total'] > 0]
        to = {r['candidate_id']: r['transfer'] for r in rs if r['candidate_id'] != x and r['transfer'] > 0}
        if out > 0 and to and remaining:
            yield cid, cn, x, out, remaining, to


def luce_share(W, fp, remaining_parties, q):
    w = W.get(fp)
    if not w:
        return None
    s = sum(w.get(p, 0) for p in remaining_parties)
    return (w.get(q, 0) / s) if s > 0 else None


def main(eid):
    rows, cands, cards, W = load(eid)
    orders = card_orders(cards, cands)
    recs = []
    no_card = Counter(); disagree = 0
    for cid, cn, x, out, remaining, to in exclusions(rows, cands):
        xc = cands.get(x)
        if not xc:
            continue
        fp = xc['party']
        cl = orders.get((cid, x))
        if not cl:
            no_card[fp] += 1
            continue
        picks = Counter()
        for reg, order in cl:
            nxt = next((c for c in order if c != x and c in remaining), None)
            if nxt:
                picks[nxt] += 1
        if not picks:
            continue
        if len(picks) > 1:
            disagree += 1
        d = picks.most_common(1)[0][0]
        dc = cands[d]
        rem_parties = {mparty(cands[r]['party']) for r in remaining}
        base = luce_share(W, mparty(fp), rem_parties, mparty(dc['party']))
        conc = to.get(d, 0) / out
        recs.append({'contest': cid, 'count': cn, 'excluded': x, 'party': fp, 'votes': out, 'pick': d, 'pick_party': dc['party'],
                     'concordance': round(conc, 4), 'baseline': round(base, 4) if base is not None else None,
                     'lift': round(conc - base, 4) if base is not None else None, 'n_remaining': len(remaining),
                     'cards': len(cl), 'remaining': remaining, 'to': to})
    # ---- fixed-effects regression: share to r = a[pX, pr] + f[pX] * card_pick
    # within-transformation by (pX, pr) cell, then weighted least squares on f per from-party
    cells = defaultdict(list)
    for rec in recs:
        for r in rec['remaining']:
            pr = mparty(cands[r]['party'])
            cells[(mparty(rec['party']), pr)].append((rec['to'].get(r, 0) / rec['votes'], 1.0 if r == rec['pick'] else 0.0, rec['votes'], rec['contest']))
    f_num, f_den, f_n, f_seats = defaultdict(float), defaultdict(float), Counter(), defaultdict(set)
    for (px, pr), pts in cells.items():
        if len(pts) < 2:
            continue
        wsum = sum(p[2] for p in pts)
        ybar = sum(p[0] * p[2] for p in pts) / wsum
        xbar = sum(p[1] * p[2] for p in pts) / wsum
        if xbar in (0.0, 1.0):
            continue  # no variation in the card within this pair
        for y, xx, w, c in pts:
            f_num[px] += w * (xx - xbar) * (y - ybar)
            f_den[px] += w * (xx - xbar) ** 2
            f_n[px] += 1
            f_seats[px].add(c)
    follow = {p: {'f': round(f_num[p] / f_den[p], 3), 'obs': f_n[p], 'seats': len(f_seats[p])} for p in f_num if f_den[p] > 0}
    # ---- party summaries
    byp = defaultdict(list)
    for rec in recs:
        byp[rec['party']].append(rec)
    summary = {}
    for p, rs in sorted(byp.items(), key=lambda kv: -sum(r['votes'] for r in kv[1])):
        v = sum(r['votes'] for r in rs)
        conc = sum(r['concordance'] * r['votes'] for r in rs) / v
        lifts = [r for r in rs if r['lift'] is not None]
        lift = sum(r['lift'] * r['votes'] for r in lifts) / sum(r['votes'] for r in lifts) if lifts else None
        summary[p] = {'exclusions': len(rs), 'votes': v, 'concordance': round(conc, 3), 'lift': round(lift, 3) if lift is not None else None,
                      'follow': follow.get(mparty(p)), 'no_card': no_card.get(p, 0)}
    out = {'election': eid, 'summary': summary, 'disagreeing_cards': disagree, 'exclusions_with_card': len(recs),
           'exclusions_without_card': sum(no_card.values()),
           'rows': [{k: v for k, v in r.items() if k not in ('remaining', 'to')} for r in recs]}
    os.makedirs(os.path.join(ROOT, 'raw/htv'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, f'raw/htv/follow_{eid}.json'), 'w'), indent=0)
    print(f'{len(recs)} exclusions with a card, {sum(no_card.values())} without; {disagree} where the party\'s cards disagreed')
    print(f'{"party":6} {"excl":>5} {"votes":>8} {"conc":>6} {"lift":>6} {"follow":>7} {"obs":>5} seats')
    for p, s in summary.items():
        f = s['follow']
        print(f'{p:6} {s["exclusions"]:5} {s["votes"]:8,} {s["concordance"]:6.1%} {(s["lift"] if s["lift"] is not None else float("nan")):+6.1%} '
              f'{(f["f"] if f else float("nan")):7.2f} {(f["obs"] if f else 0):5} {(f["seats"] if f else 0)}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'vic2022')
