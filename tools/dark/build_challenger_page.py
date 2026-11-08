"""Build the private EBA Dark page for the returning-challenger analysis (data/analysis/returning_challengers.json).
Usage: python3 tools/dark/build_challenger_page.py data/analysis/returning_challengers.json analysis/dark/second_chances.html"""
import json, sys, os
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>')] + '''
th { white-space: normal; vertical-align: bottom; } #tbl-vote td:first-child { white-space: normal; min-width: 180px; }
</style>'''
data = json.dumps({k: R[k] for k in ('vote', 'vote_by_closeness', 'former_members', 'winning', 'win_rates', 'member_side', 'independents', 'independent_rows', 'returning_2026')}, separators=(',', ':'))

body = r'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 1 · part 5</span></div>
  <h1>Second chances</h1>
  <p>Some candidates lose and come back: for a second go, a third, or to win back a seat they used to hold. Do they build a following the way sitting members do? How do they move the vote, and does it matter whether the member is still there?</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">No, they don't. A Labor or Coalition candidate on their second try does about as well as a fresh face (<b class="num" id="t-sec"></b>, within noise). Third tries are too rare among the major parties to judge (3 cases), and the Greens' are no better either. Returning challengers do win more often, but only because they come back to seats where they came close. Once the margin and the swing are allowed for, coming back is worth nothing. The hard part is the opponent: a member who took the seat from them last time gets the sophomore surge. Incumbency belongs to the office, not to name recognition.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>The vote</h2>
  <p>The challenging party's first-preference change in the seat, compared with the same party's other challenges at the same election. Notional figures where boundaries changed; whether the member is a first-termer is controlled for.</p>
  <div class="tablewrap"><table id="tbl-vote"><thead><tr><th></th><th class="n">Labor + Coalition</th><th class="n">of which state</th><th class="n">of which federal</th><th class="n">Greens</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Points of first preferences, 90% bootstrap intervals. Second go, third go: the same person who lost last time (and the time before). Open seat: the member did not stand again.</p>
</section>

<section>
  <h2>Winning</h2>
  <p>Within 6 points of the member, second-try challengers won <b class="num" id="t-raw2"></b> of the time and fresh candidates <b class="num" id="t-raw1"></b>. That looks like a big edge, but those who come back are mostly those who nearly won. In a model of winning on the two-party margin faced and the statewide swing, returning multiplies the odds by <b class="num" id="t-or"></b>: no edge. An open seat helps (odds ×<span class="num" id="t-open"></span>), as the open-seat penalty would predict.</p>
  <div class="tablewrap" style="max-width:520px"><table id="tbl-win"><thead><tr><th>Challenger</th><th>Opponent</th><th class="n">Within 6 pts</th><th class="n">Won</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>Former members trying to win it back</h2>
  <p>Nine Labor or Coalition members who lost their seat stood again next time. Four won it back. Their vote fell against fresh challengers, but that is the member who beat them enjoying the sophomore surge: allowing for it, a former member does about as well as anyone (<span class="num" id="t-fm"></span>).</p>
  <div class="tablewrap"><table id="tbl-fm"><thead><tr><th>Election</th><th>Seat</th><th>Former member</th><th class="n">Party vote change</th><th>Result</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>The member's side</h2>
  <p>When the same challenger comes back, the sitting member's party does <b class="num" id="t-mem"></b> better than where the opponent is new (interval just touching zero). A rematch is, if anything, slightly easier for the incumbent.</p>
</section>

<section>
  <h2>Independents who try again</h2>
  <p id="t-ind"></p>
  <div class="tablewrap"><table id="tbl-ind"><thead><tr><th>Election</th><th>Seat</th><th>Independent</th><th class="n">Try</th><th class="n">Last time</th><th class="n">This time</th><th>Result</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Independents with 8% or more last time.</p>
</section>

<section>
  <h2>2026: who is coming back</h2>
  <p>Declared candidates (as of the 31 October register) who stood for the same seat before. The ballot draw will confirm the list.</p>
  <div class="tablewrap"><table id="tbl-26"><thead><tr><th>Seat</th><th>Candidate</th><th class="n">Tries before</th><th class="n">Last vote</th><th>Facing</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>For the seat models</h2>
  <ul class="plain">
    <li>Treat a returning major-party challenger like a new one: no bonus.</li>
    <li>Where the member took the seat from that challenger, the sophomore surge in the member model already covers the extra difficulty.</li>
    <li>An independent's previous vote is a fair starting point for their next try (on average it slips a little), but the spread is wide: some campaigns build (Mildura 2018, Wannon, Benambra), many fade.</li>
  </ul>
</section>

<section><h3>Next</h3><p class="note">Code: <code>src/returning_challengers.py</code>; results in <code>data/analysis/returning_challengers.json</code>. Re-run with <code>python3 tools/rerun_analyses.py --id returning_challengers</code> (triggers: nominations, results).</p></section>

</div></main>

<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const pts = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
const ci = (x) => `${pts(x.pts)}<div class="note">${pts(x.lo)} to ${pts(x.hi)}</div>`;
const V = D.vote, A = V['ALP+COAL'], W = D.winning, FM = D.former_members;
$('t-sec').textContent = pts(A.second_v_member.pts) + ' pts';
const wr = (t, o) => D.win_rates.find(r => r.type === t && r.opp === o);
const r2 = wr('second', 'member'), r1 = wr('new', 'member');
$('findings').innerHTML = [
  [pts(A.second_v_member.pts), 'Second go, vote', 'Points against a fresh candidate; interval ' + pts(A.second_v_member.lo) + ' to ' + pts(A.second_v_member.hi) + '.', ''],
  ['×' + W.returning_odds_ratio.toFixed(2), 'Odds of winning, returning', 'Given the margin and the swing. Interval ' + W.returning_ci[0] + '–' + W.returning_ci[1] + '.', ''],
  [pts(A.v_first_term_member_who_won_it.pts), 'Facing the member who beat them', 'The sophomore surge, seen from the other side.', 'down'],
  [pts(D.member_side.returning_challenger.pts), 'Member’s party in a rematch', 'Against a new opponent; borderline.', '']
].map(([n, l, s, c]) => `<div class="finding"><div class="big ${c}">${n}</div><div class="lab">${l}</div><div class="sub">${s}</div></div>`).join('');
const rows = [['Second go, v member', 'second_v_member'], ['Third or later go, v member', 'third_plus_v_member'], ['Open seat (any challenger)', 'open_seat'], ['Returning, in an open seat (extra)', 'returning_in_open_seat'], ['Member is a first-termer who won it', 'v_first_term_member_who_won_it'], ['Member is another first-termer', 'v_other_first_term_member']];
document.querySelector('#tbl-vote tbody').innerHTML = rows.map(([l, k]) => `<tr><td>${l}</td>` + ['ALP+COAL', 'ALP+COAL state', 'ALP+COAL federal', 'GRN'].map(g => `<td class="n num">${ci(V[g][k])}</td>`).join('') + '</tr>').join('') +
  `<tr><td class="note">Cases (second / third+ / open)</td>` + ['ALP+COAL', 'ALP+COAL state', 'ALP+COAL federal', 'GRN'].map(g => `<td class="n num note">${V[g].n_second} / ${V[g].n_third_plus} / ${V[g].n_open}</td>`).join('') + '</tr>';
$('t-raw2').textContent = r2.won + ' of ' + r2.n; $('t-raw1').textContent = r1.won + ' of ' + r1.n; $('t-or').textContent = '×' + W.returning_odds_ratio.toFixed(2) + ' (interval ' + W.returning_ci[0] + '–' + W.returning_ci[1] + ')'; $('t-open').textContent = W.open_odds_ratio.toFixed(1);
const TL = { new: 'Fresh', second: 'Second go', third_plus: 'Third+ go' };
document.querySelector('#tbl-win tbody').innerHTML = D.win_rates.filter(r => r.n).map(r => `<tr><td>${TL[r.type]}</td><td>${r.opp === 'member' ? 'Member' : 'Open seat'}</td><td class="n num">${r.n}</td><td class="n num">${r.won} (${Math.round(100 * r.won / r.n)}%)</td></tr>`).join('');
$('t-fm').textContent = pts(FM.former_member_back.pts) + ' pts, interval ' + pts(FM.former_member_back.lo) + ' to ' + pts(FM.former_member_back.hi);
const E = (e) => (e.startsWith('fed') ? 'Federal ' : 'State ') + e.slice(-4);
const cap = (s) => s.replace(/\b([A-Z])([A-Z]+)\b/g, (m, a, b) => a + b.toLowerCase());
const dot = (p) => `<span class="dot" style="background:${p === 'ALP' ? 'var(--alp)' : ['COAL', 'LIB', 'NAT'].includes(p) ? 'var(--coal)' : p === 'GRN' ? 'var(--grn)' : 'var(--ind)'}"></span>`;
document.querySelector('#tbl-fm tbody').innerHTML = FM.cases.map(c => `<tr><td>${E(c.to)}</td><td>${c.seat}</td><td>${dot(c.party)}${cap(c.candidate)}</td><td class="n num">${pts(c.change_pts)}</td><td>${c.won ? 'Won it back' : 'Lost again'}</td></tr>`).join('');
$('t-mem').textContent = pts(D.member_side.returning_challenger.pts) + ' pts';
const I2 = D.independents.find(x => x.try === '2nd'), I3 = D.independents.find(x => x.try === '3rd+');
$('t-ind').innerHTML = `${I2.n} independents stood again in the same seat after losing. On their second try their vote moved ${pts(I2.mean_change_pts)} pts on average (median ${pts(I2.median_change_pts)}); ${Math.round(100 * I2.share_up)}% went up. Those who had 10% or more last time slipped ${pts(I2.strong_10plus.mean_change_pts)} pts on average and ${I2.won} won. On a third or later try (${I3.n} cases) the average was ${pts(I3.mean_change_pts)}. The averages hide a split: a few campaigns gather momentum, most fade.`;
document.querySelector('#tbl-ind tbody').innerHTML = D.independent_rows.slice(0, 14).map(r => `<tr><td>${E(r.to)}</td><td>${r.seat}</td><td>${cap(r.name)}</td><td class="n num">${r.try}</td><td class="n num">${(100 * r.share0).toFixed(1)}%</td><td class="n num">${(100 * r.share1).toFixed(1)}%</td><td>${r.won ? 'Won' : ''}</td></tr>`).join('');
const R26 = D.returning_2026.filter(o => o.tries_in_seat > 0);
document.querySelector('#tbl-26 tbody').innerHTML = R26.map(o => { const was = o.history && o.history[0] && o.history[0].party !== o.party ? ` <span class="note">(was ${o.history[0].party})</span>` : ''; const fm = o.history && o.history.some(h => h.won) ? ' <span class="note">former member</span>' : '';
  return `<tr><td>${o.seat}</td><td>${dot(o.party)}${o.candidate}${was}${fm}</td><td class="n num">${o.tries_in_seat}</td><td class="n num">${o.last_share != null ? (100 * o.last_share).toFixed(1) + '%' : ''}</td><td>${o.opponent || ''}</td></tr>`; }).join('');
</script>
'''
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT, 'w').write('<title>Second Chances</title>\n' + head + body.replace('__DATA__', data))
print(OUT)
