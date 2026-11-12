"""Do voters punish their state government at federal elections? (The mirror of federal_government_headwind.)

For each state and territory at each federal election, the swing in Labor's two-party-preferred vote there minus the
national swing (AEC House TPP by division, summed by state; raw/national/aec). The predictor is the party governing the
state on polling day: +1 Labor, -1 Liberal/National/CLP. If voters take it out on the state government, the coefficient is
negative: a Labor state government costs federal Labor in that state.

Two readings:
  pooled   all state-elections together (does the state government's party line up with the deviation?)
  within   with a fixed effect for each state (does a state's federal swing move when its own government changes party?)
           identified only by the changes of government between federal elections: WA 2017, SA 2018 and 2022, NT 2016 and
           2024, NSW 2023, QLD 2024.
Victoria itself cannot answer the question alone: Labor has governed the state at every federal election since 2016
(and 1999-2010); its federal deviations are reported for the record.
Federal elections 2016-2025 (swings 2019, 2022, 2025) are what is loaded so far; 2004-2013 extend it when their AEC files
arrive (tools/fetch_national.sh).

usage: python3 -m src.state_government_at_federal   -> data/analysis/state_government_at_federal.json
"""
import os, csv, io, json, glob, math
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EVENTS = {'2016': '20499', '2019': '24310', '2022': '27966', '2025': '31496'}
# party governing each state/territory on federal polling day
STATE_GOV = {
    '2016': {'NSW': 'COAL', 'VIC': 'ALP', 'QLD': 'ALP', 'WA': 'COAL', 'SA': 'ALP', 'TAS': 'COAL', 'ACT': 'ALP', 'NT': 'COAL'},
    '2019': {'NSW': 'COAL', 'VIC': 'ALP', 'QLD': 'ALP', 'WA': 'ALP', 'SA': 'COAL', 'TAS': 'COAL', 'ACT': 'ALP', 'NT': 'ALP'},
    '2022': {'NSW': 'COAL', 'VIC': 'ALP', 'QLD': 'ALP', 'WA': 'ALP', 'SA': 'ALP', 'TAS': 'COAL', 'ACT': 'ALP', 'NT': 'ALP'},
    '2025': {'NSW': 'ALP', 'VIC': 'ALP', 'QLD': 'COAL', 'WA': 'ALP', 'SA': 'ALP', 'TAS': 'COAL', 'ACT': 'ALP', 'NT': 'COAL'}}
FED_GOV = {'2019': 'COAL', '2022': 'COAL', '2025': 'ALP'}   # federal government going into each election


def tpp_by_state(ev):
    f = glob.glob(os.path.join(ROOT, f'raw/national/aec/{ev}/HouseTppByDivisionDownload-{ev}.csv'))[0]
    lines = open(f, encoding='utf-8-sig').read().splitlines()[1:]
    alp, tot = {}, {}
    for r in csv.DictReader(io.StringIO('\n'.join(lines))):
        s = r['StateAb']; alp[s] = alp.get(s, 0) + int(r['Australian Labor Party Votes']); tot[s] = tot.get(s, 0) + int(r['TotalVotes'])
    nat = sum(alp.values()) / sum(tot.values())
    return {s: alp[s] / tot[s] for s in alp}, nat


def ols(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def main():
    T = {y: tpp_by_state(ev) for y, ev in EVENTS.items()}
    years = sorted(T); rows = []
    for a, b in zip(years, years[1:]):
        (s0, n0), (s1, n1) = T[a], T[b]
        for s in s1:
            rows.append(dict(year=b, state=s, swing=100 * (s1[s] - s0[s]), national=100 * (n1 - n0), dev=100 * ((s1[s] - s0[s]) - (n1 - n0)),
                             gov=1 if STATE_GOV[b][s] == 'ALP' else -1, changed=int(STATE_GOV[b][s] != STATE_GOV[a][s]),
                             same_as_federal=int(STATE_GOV[b][s] == FED_GOV[b])))
    y = np.array([r['dev'] for r in rows]); g = np.array([r['gov'] for r in rows], float)
    # pooled
    bp = ols(np.column_stack([np.ones(len(y)), g]), y)
    # within: state fixed effects
    states = sorted({r['state'] for r in rows})
    Xw = np.column_stack([g] + [np.array([r['state'] == s for r in rows], float) for s in states])
    bw = ols(Xw, y)
    # permutation test for the within estimate: shuffle the government series within each state
    rng = np.random.default_rng(5); perm = []
    for _ in range(4000):
        gg = g.copy()
        for s in states:
            ix = [i for i, r in enumerate(rows) if r['state'] == s]; gg[ix] = rng.permutation(g[ix])
        perm.append(ols(np.column_stack([gg] + list(Xw[:, 1:].T)), y)[0])
    p_within = float(np.mean(np.abs(perm) >= abs(bw[0])))
    permp = []
    for _ in range(4000):
        permp.append(ols(np.column_stack([np.ones(len(y)), rng.permutation(g)]), y)[1])
    p_pooled = float(np.mean(np.abs(permp) >= abs(bp[1])))
    res = dict(method=__doc__.split('\n\n')[1].strip(), elections=years,
               national_swing_to_alp={b: round(100 * (T[b][1] - T[a][1]), 2) for a, b in zip(years, years[1:])},
               pooled=dict(per_labor_state_gov_pts=round(float(bp[1]), 2), note='deviation per +1 (Labor state government) vs -1 (Coalition); the gap between the two is twice this', p_perm=round(p_pooled, 3), n=len(rows)),
               within=dict(per_labor_state_gov_pts=round(float(bw[0]), 2), p_perm=round(p_within, 3), changes_of_government=sum(r['changed'] for r in rows)),
               victoria=[dict(year=r['year'], deviation_pts=round(r['dev'], 2), state_gov=STATE_GOV[r['year']]['VIC']) for r in rows if r['state'] == 'VIC'],
               rows=[{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in rows])
    # same party at both levels: is a state government of the federal government's own party a drag on the federal swing to that party?
    sp = np.array([(1 if FED_GOV[r['year']] == 'ALP' else -1) * r['same_as_federal'] for r in rows], float)   # +1: both Labor, -1: both Coalition
    bs = ols(np.column_stack([np.ones(len(y)), sp]), y)
    res['same_party_both_levels'] = dict(per_unit_pts=round(float(bs[1]), 2), note='+1 when Labor governs both state and federation, -1 when the Coalition does')
    gap = 2 * bp[1]
    res['findings'] = [
        f"Pooled across every state and territory (federal elections 2019, 2022, 2025): where Labor governed the state, federal Labor's swing there was {gap:+.1f} points relative to the national swing compared with states under the Coalition (permutation p = {p_pooled:.2f}): no sign that voters punish their state government at federal elections, and if anything the opposite.",
        f"Within each state (when the state government changed party between federal elections): {2 * bw[0]:+.1f} points (p = {p_within:.2f}), from {res['within']['changes_of_government']} changes of government.",
        "Victoria: Labor governed the state at all three, so Victoria cannot answer this on its own; its deviations from the national swing were " + ', '.join(f"{v['year']} {v['deviation_pts']:+.1f}" for v in res['victoria']) + " points.",
        f"Same party at both levels: {res['same_party_both_levels']['per_unit_pts']:+.2f} points per unit (positive would mean a state government of the federal government's party helps it federally).",
        "Small sample (8 jurisdictions x 3 elections); adding 2004-2013 from the AEC files would more than double it."]
    json.dump(res, open(os.path.join(ROOT, 'data/analysis/state_government_at_federal.json'), 'w'), indent=1)
    print(json.dumps({k: res[k] for k in ('national_swing_to_alp', 'pooled', 'within', 'victoria')}, indent=1)); print('\n'.join(res['findings']))
    for r in rows: print(r['year'], r['state'], f"dev {r['dev']:+.2f}", 'ALP gov' if r['gov'] > 0 else 'COAL gov', 'changed' if r['changed'] else '')


if __name__ == '__main__':
    main()
