"""Build the private EBA Dark page for the primary-swing analysis (data/analysis/primary_swings.json).
Usage: python3 tools/dark/build_primary_page.py data/analysis/primary_swings.json analysis/dark/first_preferences.html"""
import json, sys, os
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>')] + '''
.warn { border-left: 3px solid var(--down); background: var(--surface); padding: 10px 14px; border-radius: 0 6px 6px 0; font-size: 14px; max-width: 70ch; }
td.p { font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-align: right; }
#tbl-26 th { white-space: normal; vertical-align: bottom; }
:root { --onp: #e08a1f; } @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --onp: #f0a040; } } :root[data-theme="dark"] { --onp: #f0a040; }
</style>'''
data = json.dumps({k: R[k] for k in ('rules', 'onp_senate', 'backtest', 'outlook_2026')}, separators=(',', ':'))

body = r'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 3a</span></div>
  <h1>First preferences</h1>
  <p>With One Nation polling in the twenties, a two-party swing may be the wrong tool for 2026. What do primary-vote swings tell us seat by seat, and what happens when seats are projected from primaries and run through preferences instead?</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">Each party's vote moves in its own way. The Greens and the Coalition move by about the same number of points everywhere. Labor sits between uniform and proportional, losing more where it is strongest. One Nation's 2025 Senate growth was closer to proportional: it grew most where it was already strong. Projecting seats from primaries and counting preferences called <b class="num" id="t-bt"></b> of past results correctly, against <b class="num" id="t-bt2"></b> for a uniform two-party swing, with the gain in seats where the final two was not Labor v Coalition.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>Uniform or proportional?</h2>
  <p>For every pair of consecutive elections since 1999 (notional figures where boundaries changed), each seat's change was compared with two rules, given the true statewide result. Uniform: every seat moves by the statewide change. Proportional: every seat moves by the same ratio. λ blends them (0 uniform, 1 proportional), fitted per party; the error is the typical miss on a seat's primary vote, predicting each election from the others.</p>
  <div class="tablewrap"><table id="tbl-rules"><thead><tr><th>Party</th><th class="n">Seat-elections</th><th class="n">λ</th><th class="n">Error, uniform</th><th class="n">Error, proportional</th><th class="n">Error, fitted</th><th>Reading</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Minor = everyone except Labor, the Coalition, the Greens and a seat's strongest independent. One Nation from its Senate vote at <span id="t-ven"></span> polling places, 2022 to 2025.</p>
</section>

<section>
  <h2>Backtest: primaries against the pendulum</h2>
  <p>Both methods were given perfect polls: the true statewide primaries for one, the true statewide two-party swing for the other. Independents' votes were carried forward only if the same independent stood again, which is known once nominations close.</p>
  <div class="tablewrap"><table id="tbl-bt"><thead><tr><th>Election</th><th class="n">Seats</th><th class="n">Primaries + preferences</th><th class="n">Uniform two-party</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Adding member effects (sophomore surge, open-seat penalty) barely changes either count. The remaining misses are mostly new independents (Kooyong and Goldstein 2022) and very close seats.</p>
</section>

<section>
  <h2>2026 from the primaries</h2>
  <div class="warn" id="warn"></div>
  <p style="margin-top:12px">Each seat's 2022 primaries were moved by each party's rule to the latest poll average. One Nation starts from its 2022 upper-house vote in the district, because it stood in few lower-house seats in 2022. Members' personal votes are applied, then a preference count is run in every seat. The simulation adds statewide poll error (2.5 pts per party) and seat-level scatter of the size measured above, 2,000 times.</p>
  <figure><div id="sim"></div><figcaption>Seats won in 2,000 simulations: median (dot), 80% range (bar). 45 seats for a majority. The two-party pendulum at the polls' two-party figure gives <span id="t-pp"></span>.</figcaption></figure>
  <h3 style="margin-top:18px">Final twos</h3>
  <p id="finals"></p>
  <div class="seg" role="group" aria-label="Show seats" id="seg"><button aria-pressed="true" data-f="close">Close</button><button aria-pressed="false" data-f="onp">One Nation in the final two</button><button aria-pressed="false" data-f="diff">Differs from the pendulum</button><button aria-pressed="false" data-f="all">All</button></div>
  <div class="tablewrap"><table id="tbl-26"><thead><tr><th>Seat</th><th class="n">Labor</th><th class="n">Coalition</th><th class="n">Greens</th><th class="n">One Nation</th><th>Final two</th><th>Chance of winning</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Projected primaries (%). Chance of winning from the simulation. † the pendulum picks a different winner.</p>
</section>

<section>
  <h2>The big unknown: Coalition preferences to One Nation</h2>
  <p>The flow model is fitted on Victorian counts where Liberal and National voters were rarely excluded with One Nation still in the race, so how they rank One Nation against Labor is not in the data. Labor's own voters put One Nation last (strength about 0.3). The central run uses a neutral 1. Seats won, depending on that number:</p>
  <div class="tablewrap" style="max-width:520px"><table id="tbl-sens"><thead><tr><th>Coalition-to-One Nation strength</th><th class="n">Labor</th><th class="n">Coalition</th><th class="n">One Nation</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">Strength is relative to the other candidates still in the count; Liberal voters give Labor about 0.5. The 2025 federal counts in Queensland and New South Wales seats where One Nation made the final two would pin this down, but they are outside the Atlas.</p>
</section>

<section>
  <h2>Caveats</h2>
  <ul class="plain">
    <li>One Nation polling in the twenties is outside anything in the data. Its starting map (the 2022 upper-house vote) and its growth rule (2025 Senate) both come from a party polling 3–5%.</li>
    <li>It is assumed One Nation stands in every seat; the ballot draw will settle that, and the re-run is triggered by nominations.</li>
    <li>New independents cannot be projected until nominations close; strong ones (as in Kooyong and Goldstein in 2022) are exactly what this misses.</li>
    <li>Poll error is set at 2.5 pts per party. With a new party this large it may be bigger.</li>
  </ul>
</section>

<section><h3>Next</h3><p class="note">Code: <code>src/primary_swings.py</code>; results in <code>data/analysis/primary_swings.json</code>. Re-run with <code>python3 tools/rerun_analyses.py --id primary_swings</code> or <code>--trigger polls_2026</code> / <code>nominations_2026</code>.</p></section>

</div></main>

<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const pts = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
const R = D.rules, B = D.backtest.total, O = D.outlook_2026, ON = D.onp_senate['fed2022->fed2025'];
const PN = { ALP: 'Labor', COAL: 'Coalition', LIB: 'Liberal', NAT: 'National', GRN: 'Greens', ONP: 'One Nation', IND: 'Independent', OTH: 'Other', MINOR: 'Minor parties', OTHERS: 'Everyone else' };
const COL = { ALP: 'var(--alp)', COAL: 'var(--coal)', LIB: 'var(--coal)', NAT: 'var(--coal)', GRN: 'var(--grn)', ONP: 'var(--onp)', IND: 'var(--ind)', OTH: 'var(--ind)' };
$('t-bt').textContent = B.primaries + ' of ' + B.seats; $('t-bt2').textContent = B.two_party;
$('findings').innerHTML = [
  [R.GRN.lambda.toFixed(2), 'λ, Greens', 'Uniform: the same points everywhere. Proportional would miss by ' + R.GRN.rmse_proportional.toFixed(1) + ' pts a seat.', ''],
  [R.ALP.lambda.toFixed(2), 'λ, Labor', 'Between: Labor loses more where it is strongest.', ''],
  [ON.lambda.toFixed(2), 'λ, One Nation', 'Senate 2022 to 2025: grew most where already strong.', ''],
  [B.primaries + '/' + B.seats, 'Seats called, primaries + preferences', 'Uniform two-party ' + B.two_party + '/' + B.seats + ', four elections.', 'up']
].map(([n, l, s, c]) => `<div class="finding"><div class="big ${c}">${n}</div><div class="lab">${l}</div><div class="sub">${s}</div></div>`).join('');
const read = (g) => g.lambda < 0.25 ? 'uniform' : g.lambda > 0.75 ? 'proportional' : 'in between';
document.querySelector('#tbl-rules tbody').innerHTML = ['ALP', 'COAL', 'GRN', 'MINOR'].map(k => [PN[k], R[k]]).concat([['One Nation (Senate)', { n: ON.venues, lambda: ON.lambda, rmse_uniform: ON.rmse_uniform, rmse_proportional: ON.rmse_proportional, rmse_lambda_out_of_sample: null }]])
  .map(([n, g]) => `<tr><td>${n}</td><td class="n num">${g.n}</td><td class="n num">${g.lambda.toFixed(2)}</td><td class="n num">${g.rmse_uniform.toFixed(1)}</td><td class="n num">${g.rmse_proportional.toFixed(1)}</td><td class="n num">${g.rmse_lambda_out_of_sample == null ? '–' : g.rmse_lambda_out_of_sample.toFixed(1)}</td><td>${read(g)}</td></tr>`).join('');
$('t-ven').textContent = ON.venues.toLocaleString();
const E = (e) => (e.startsWith('fed') ? 'Federal ' : 'State ') + e.slice(-4);
document.querySelector('#tbl-bt tbody').innerHTML = Object.entries(D.backtest).filter(([k]) => k !== 'total').map(([k, v]) => `<tr><td>${E(k.split('->')[1])} (from ${k.slice(3, 7)})</td><td class="n num">${v.seats}</td><td class="n num">${v.primaries}</td><td class="n num">${v.two_party}</td></tr>`).join('') + `<tr><td><b>Total</b></td><td class="n num">${B.seats}</td><td class="n num"><b>${B.primaries}</b></td><td class="n num"><b>${B.two_party}</b></td></tr>`;
$('warn').innerHTML = `<b>An exploration, not a forecast.</b> Poll average (${O.polls_n} polls to ${O.polls_to}): Labor ${O.polls.ALP}, Coalition ${O.polls.COAL}, Greens ${O.polls.GRN}, One Nation ${O.polls.ONP}. Labor's primary is down about ${Math.round(37 - O.polls.ALP)} points from 2022 and One Nation is polling at a level never seen in Victoria, so everything below extrapolates beyond the history it was fitted on.`;
// simulation chart
(function () {
  const S = O.simulated_seats, ks = ['COAL', 'ALP', 'ONP', 'GRN', 'IND'], W = 640, rowH = 34, left = 110, right = 30, top = 16, H = top + ks.length * rowH + 24, mx = 60;
  const x = v => left + v / mx * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:420px" role="img" aria-label="Simulated seats by party">`;
  for (let v = 0; v <= mx; v += 10) s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 20}" stroke="var(--line)" stroke-dasharray="2 3"/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v}</text>`;
  s += `<line x1="${x(45)}" x2="${x(45)}" y1="${top - 10}" y2="${H - 20}" stroke="var(--fg-2)" stroke-width="1.5"/><text class="tick" x="${x(45) + 4}" y="${top - 2}">45</text>`;
  ks.forEach((k, i) => { const t = S[k], y = top + i * rowH + rowH / 2; s += `<text x="0" y="${y + 4}">${PN[k]}</text><line x1="${x(t.lo)}" x2="${x(t.hi)}" y1="${y}" y2="${y}" stroke="${COL[k]}" stroke-width="8" stroke-linecap="round" opacity=".35"/><circle cx="${x(t.median)}" cy="${y}" r="6" fill="${COL[k]}"/><text class="tick" x="${x(t.hi) + 10}" y="${y + 4}">${t.median} (${t.lo}–${t.hi})</text>`; });
  $('sim').innerHTML = s + '</svg>';
})();
$('t-pp').textContent = Object.entries(O.two_party_seats).map(([k, v]) => PN[k] + ' ' + v).join(', ') + ' of the Labor v Coalition seats (two-party swing ' + pts(O.two_party_swing_from_polls_pts) + ')';
$('finals').textContent = Object.entries(O.final_twos).sort((a, b) => b[1] - a[1]).map(([k, v]) => k.split(' v ').map(p => PN[p]).join(' v ').replace('Coalition v Coalition', 'Liberal v National') + ': ' + v).join(' · ');
const S = O.seats.map(x => { const w = Object.entries(x.p_win)[0]; return Object.assign(x, { top: w[0], ptop: w[1] }); });
const g = (x, k) => k === 'COAL' ? (x.primaries.LIB || 0) + (x.primaries.NAT || 0) : (x.primaries[k] || 0);
function draw(f) {
  let rows = S.slice();
  if (f === 'close') rows = rows.filter(x => x.ptop < 0.75);
  if (f === 'onp') rows = rows.filter(x => x.final_two.includes('ONP'));
  if (f === 'diff') rows = rows.filter(x => x.two_party_winner && x.two_party_winner !== (['LIB', 'NAT'].includes(x.winner) ? 'COAL' : x.winner));
  rows.sort((a, b) => f === 'all' ? a.seat.localeCompare(b.seat) : a.ptop - b.ptop);
  document.querySelector('#tbl-26 tbody').innerHTML = rows.map(x => {
    const diff = x.two_party_winner && x.two_party_winner !== (['LIB', 'NAT'].includes(x.winner) ? 'COAL' : x.winner);
    return `<tr><td>${x.seat}${diff ? ' †' : ''}${x.member ? `<div class="note">${x.member}</div>` : ''}</td>` + ['ALP', 'COAL', 'GRN', 'ONP'].map(k => `<td class="p">${(100 * g(x, k)).toFixed(0)}</td>`).join('') +
      `<td>${x.final_two.map(p => `<span class="dot" style="background:${COL[p]}"></span>${PN[p]}`).join(' v ')}</td><td>${Object.entries(x.p_win).slice(0, 2).map(([p, v]) => `${PN[p]} ${Math.round(100 * v)}%`).join(', ')}</td></tr>`;
  }).join('') || '<tr><td colspan="7" class="note">None.</td></tr>';
}
draw('close');
document.querySelectorAll('#seg button').forEach(b => b.addEventListener('click', () => { document.querySelectorAll('#seg button').forEach(x => x.setAttribute('aria-pressed', x === b)); draw(b.dataset.f); }));
document.querySelector('#tbl-sens tbody').innerHTML = Object.entries(O.sensitivity_coalition_to_onp).map(([k, v]) => `<tr><td>${k}${k === '1.0' ? ' (central)' : ''}</td><td class="n num">${v.ALP || 0}</td><td class="n num">${v.COAL || 0}</td><td class="n num">${v.ONP || 0}</td></tr>`).join('');
</script>
'''
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT, 'w').write('<title>First Preferences</title>\n' + head + body.replace('__DATA__', data))
print(OUT)
