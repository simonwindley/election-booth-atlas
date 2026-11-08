"""Build the private EBA Dark page for the seat-loss analysis (data/analysis/seat_loss.json), reusing the member page's styles.
Usage: python3 tools/dark/build_loss_page.py data/analysis/seat_loss.json analysis/dark/who_loses.html"""
import json, sys, os
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>')]
head += '''.warn { border-left: 3px solid var(--down); background: var(--surface); padding: 10px 14px; border-radius: 0 6px 6px 0; font-size: 14px; max-width: 70ch; }
@media (max-width: 560px) { #tbl-26 .ft { display: none; } }
td.p { font-family: var(--font-mono); font-variant-numeric: tabular-nums; text-align: right; }
</style>'''
keep = {k: R[k] for k in ('n', 'losses', 'base', 'by_margin', 'predictors', 'final', 'upsets_lost', 'upsets_held', 'calibration', 'lost_to', 'swing_by_election', 'outlook_2026')}
data = json.dumps(keep, separators=(',', ':'))

body = r'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 1 · part 4</span></div>
  <h1>Who loses</h1>
  <p>Every Labor and Coalition member who stood again for their seat, at Victorian state elections 2002–2022 and federal elections in Victoria 2007–2025: what separates the ones who lost from the ones who held on?</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">The pendulum is almost the whole story. The member's margin last time and the statewide swing sort winners from losers with an out-of-sample accuracy (AUC) of <b class="num" id="t-auc"></b>, and a point of swing is worth a point of margin. Nothing else we can measure beforehand adds to that, with one exception that points the right way: members who won their seat from the other side last time are harder to dislodge. The losses nobody saw coming mostly went to independents and Greens.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>Margin against swing</h2>
  <p>Members on less than 4% who faced a swing against them lost two times in three. With the swing behind them, they almost never lost. Above 10%, one loss in 258.</p>
  <figure><div id="bands"></div>
  <figcaption>Share of recontesting members who lost, by two-candidate margin last time, split by whether the statewide two-party swing ran against their party. Labels are losses out of members.</figcaption></figure>
</section>

<section>
  <h2>What else matters? Very little</h2>
  <p>Each predictor was added to the margin-and-swing model on its own. The odds ratio says how the odds of losing change (below 1 protects the member), and the check that matters is out-of-sample: does predicting each election from the others get better? Only being a first-term member who won the seat last time comes close, consistent with the sophomore surge found earlier.</p>
  <figure><div id="forest"></div>
  <figcaption>Odds ratio of losing, on top of margin and swing, with 90% bootstrap intervals (seats resampled within elections). Continuous predictors per standard deviation. Filled: interval excludes 1. Right: change in out-of-sample log loss (positive is better; about 1 or more would be a real gain). No major-party leader lost in the period, too few cases to estimate, so leaders are left out.</figcaption></figure>
</section>

<section>
  <h2>The surprises</h2>
  <p>Out-of-sample, the model gave these members the best chances of holding on, yet they lost. Of <span class="num" id="t-surp"></span> losses it rated below 20%, <span class="num" id="t-surp-minor"></span> went to an independent or the Greens; all <span class="num" id="t-exp"></span> losses it rated above 50% went to the major-party rival. The threat the pendulum cannot see is a strong challenger who was not in last time's final two.</p>
  <div class="tablewrap"><table id="tbl-up"><thead><tr><th>Election</th><th>Seat</th><th>Member</th><th class="n">Margin</th><th class="n">Swing to party</th><th class="n">Chance of losing</th><th>Lost to</th></tr></thead><tbody></tbody></table></div>
  <h3 style="margin-top:18px">Escapes</h3>
  <p>And the members the model most expected to lose who held on.</p>
  <div class="tablewrap"><table id="tbl-held"><thead><tr><th>Election</th><th>Seat</th><th>Member</th><th class="n">Margin</th><th class="n">Swing to party</th><th class="n">Chance of losing</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>Is it honest?</h2>
  <p>Predicted against actual losses, each election predicted from a model fitted to the others.</p>
  <div class="tablewrap" style="max-width:520px"><table id="tbl-cal"><thead><tr><th>Predicted chance</th><th class="n">Members</th><th class="n">Expected losses</th><th class="n">Actual</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>2026: the members standing again</h2>
  <div class="warn" id="warn"></div>
  <p style="margin-top:12px">Chance of losing for each Labor and Coalition member standing again, at uniform two-party swings against Labor. Where the last final two was not Labor v Coalition (marked *), a two-party swing does not apply and only the margin counts. Open seats are not included: there the party's new candidate has no personal vote to defend (see The Personal Vote).</p>
  <div class="seg" role="group" aria-label="Show" id="seg"><button aria-pressed="true" data-n="20">Most at risk</button><button aria-pressed="false" data-n="999">All</button></div>
  <div class="tablewrap"><table id="tbl-26"><thead><tr><th>Seat and member</th><th class="ft">Last final two</th><th class="n">Margin</th><th class="n">3 pts</th><th class="n">6 pts</th><th class="n" id="th-polls"></th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>For the seat models</h2>
  <ul class="plain">
    <li>Uniform swing on the two-party margin is a sound backbone: the fitted weight on swing equals the weight on margin.</li>
    <li>Seats scatter around uniform swing by about <b class="num" id="t-sd"></b> (one standard deviation), which sets the seat-level uncertainty.</li>
    <li>A recontesting member's 50:50 point is a uniform-swing margin of about <b class="num" id="t-beat"></b>, not zero: the personal vote, measured another way.</li>
    <li>The model needs a challenger term for independents and minor parties. History cannot supply it for 2026, where One Nation is polling in the 20s and could reach final twos it has never been in.</li>
  </ul>
</section>

<section>
  <h2>Caveats</h2>
  <ul class="plain">
    <li>60 losses in 579 cases: enough to see margin and swing, too few to rule out modest effects of anything else.</li>
    <li>At elections with new boundaries (state 2002, 2014, 2022; several federal), margins are on the old boundaries. Notional margins from the boundary analysis will replace them.</li>
    <li>The swing is hindsight: the actual statewide swing. Before polling day it comes from the polls, with their error on top.</li>
    <li>2002 has gaps: the 1999 two-candidate counts are incomplete, so 20 members are missing.</li>
  </ul>
</section>

<section><h3>Next</h3><p class="note">Code: <code>src/seat_loss.py</code>; results in <code>data/analysis/seat_loss.json</code>. Re-run with <code>python3 tools/rerun_analyses.py --id seat_loss --deps</code>, or by trigger (results, nominations, polls).</p></section>

</div></main>

<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const pc = (v) => Math.round(100 * v) + '%';
const pts = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
const B = D.base, LT = D.lost_to, O = D.outlook_2026;
$('t-auc').textContent = B.loeo_auc.toFixed(2);
const sg = D.predictors.find(p => p.key === 'sophomore_gain');
$('findings').innerHTML = [
  [B.loeo_auc.toFixed(2), 'Out-of-sample AUC', 'Margin and swing only; ' + D.losses + ' losses in ' + D.n + ' recontests.', ''],
  [B.swing_worth_margin.toFixed(2), 'Points of margin per point of swing', 'The pendulum, estimated rather than assumed.', ''],
  ['×' + sg.odds_ratio.toFixed(2), 'Odds of losing after winning the seat', 'First-term members who took the seat from the other side. Interval ' + sg.lo.toFixed(2) + '–' + sg.hi.toFixed(2) + '.', 'up'],
  [LT['surprise (p < 0.2)']['IND/other'] + LT['surprise (p < 0.2)'].GRN + ' of ' + LT['surprise (p < 0.2)'].n, 'Surprise losses to independents or Greens', 'Losses the model rated below 20%.', 'down']
].map(([n, l, s, c]) => `<div class="finding"><div class="big ${c}">${n}</div><div class="lab">${l}</div><div class="sub">${s}</div></div>`).join('');
// margin bands
(function () {
  const bands = [...new Set(D.by_margin.map(r => r.band))], W = 640, rowH = 46, left = 70, right = 70, top = 8, H = top + bands.length * rowH + 22;
  const x = v => left + v * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:420px" role="img" aria-label="Loss rate by margin and swing direction">`;
  [0, .25, .5, .75, 1].forEach(v => s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${H - 20}" stroke="var(--line)" ${v ? 'stroke-dasharray="2 3"' : ''}/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v * 100}%</text>`);
  bands.forEach((b, i) => {
    const y = top + i * rowH + 6;
    s += `<text x="${left - 10}" y="${y + 18}" text-anchor="end">${b.replace('-', '–')}%</text>`;
    [['against', 'var(--down)', 0], ['towards', 'var(--fg-3)', 17]].forEach(([k, col, dy]) => {
      const r = D.by_margin.find(q => q.band === b && q.swing === k), v = r.n ? r.lost / r.n : 0;
      s += `<rect x="${x(0)}" y="${y + dy}" width="${Math.max(1.5, x(v) - x(0))}" height="13" rx="2" fill="${col}"/><text class="tick" x="${x(v) + 6}" y="${y + dy + 11}">${r.lost}/${r.n}</text>`;
    });
  });
  $('bands').innerHTML = s + `</svg><p class="note" style="margin:6px 0 0"><span class="dot" style="background:var(--down)"></span>swing against the member's party &nbsp; <span class="dot" style="background:var(--fg-3)"></span>swing towards</p>`;
})();
// forest
(function () {
  const rows = D.predictors.filter(p => p.key !== 'leader').sort((a, b) => b.loeo_gain - a.loeo_gain);
  const W = 760, rowH = 30, left = 290, right = 90, top = 22, H = top + rows.length * rowH + 24, lo = Math.log(0.1), hi = Math.log(10);
  const x = v => left + (Math.log(Math.max(0.1, Math.min(10, v))) - lo) / (hi - lo) * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:600px" role="img" aria-label="Odds ratios of predictors">`;
  [0.1, 0.25, 0.5, 1, 2, 4, 10].forEach(v => s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 22}" stroke="var(--line)" ${v === 1 ? 'stroke-width="1.5"' : 'stroke-dasharray="2 3"'}/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v}</text>`);
  s += `<text class="tick" x="${x(0.11)}" y="10">← protects</text><text class="tick" x="${x(7)}" y="10" text-anchor="end">more likely to lose →</text><text class="tick" x="${W - 4}" y="10" text-anchor="end">out of sample</text>`;
  rows.forEach((p, i) => {
    const y = top + i * rowH + rowH / 2, sig = p.lo > 1 || p.hi < 1, col = sig ? 'var(--accent)' : 'var(--fg-3)';
    s += `<text x="0" y="${y + 4}">${p.label}</text>`;
    s += `<line x1="${x(p.lo)}" x2="${x(p.hi)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="2.5" stroke-linecap="round"/><circle cx="${x(p.odds_ratio)}" cy="${y}" r="5" fill="${sig ? col : 'var(--surface)'}" stroke="${col}" stroke-width="2"/>`;
    s += `<text class="tick" x="${W - 4}" y="${y + 4}" text-anchor="end" style="fill:${p.loeo_gain > 0 ? 'var(--up)' : 'var(--fg-3)'}">${pts(p.loeo_gain, 2)}</text>`;
  });
  $('forest').innerHTML = s + '</svg>';
})();
const E = (e) => (e.startsWith('fed') ? 'Federal ' : 'State ') + e.slice(-4);
const dotp = (p) => `<span class="dot" style="background:${p === 'ALP' ? 'var(--alp)' : 'var(--coal)'}"></span>`;
const cap = (s) => s ? s.replace(/\b([A-Z])([A-Z]+)\b/g, (m, a, b) => a + b.toLowerCase()) : s;
$('t-surp').textContent = LT['surprise (p < 0.2)'].n; $('t-surp-minor').textContent = LT['surprise (p < 0.2)']['IND/other'] + LT['surprise (p < 0.2)'].GRN; $('t-exp').textContent = LT['expected (p >= 0.5)'].n;
const lt = { major: 'Major-party rival', GRN: 'Greens', 'IND/other': 'Independent' };
document.querySelector('#tbl-up tbody').innerHTML = D.upsets_lost.slice(0, 10).map(r => `<tr><td>${E(r.to)}</td><td>${r.seat}</td><td>${dotp(r.party)}${cap(r.member)}</td><td class="n num">${(100 * r.margin).toFixed(1)}</td><td class="n num">${pts(100 * r.swing)}</td><td class="p">${pc(r.p_lose)}</td><td>${lt[r.lost_to] || ''}</td></tr>`).join('');
document.querySelector('#tbl-held tbody').innerHTML = D.upsets_held.slice(0, 6).map(r => `<tr><td>${E(r.to)}</td><td>${r.seat}</td><td>${dotp(r.party)}${cap(r.member)}</td><td class="n num">${(100 * r.margin).toFixed(1)}</td><td class="n num">${pts(100 * r.swing)}</td><td class="p">${pc(r.p_lose)}</td></tr>`).join('');
document.querySelector('#tbl-cal tbody').innerHTML = D.calibration.map(r => `<tr><td>${r.band}</td><td class="n num">${r.n}</td><td class="n num">${r.predicted.toFixed(1)}</td><td class="n num">${r.lost}</td></tr>`).join('');
$('t-sd').textContent = B.seat_sd_pts.toFixed(1) + ' pts'; $('t-beat').textContent = '−' + B.members_beat_uniform_by_pts.toFixed(1) + ' pts';
// 2026
$('warn').innerHTML = `<b>Beyond history.</b> The last six weeks of polls (${O.polls_n} polls to ${O.polls_to}) put Labor on ${O.polls_tpp_alp}% two-party, a swing of ${pts(O.scenarios.polls)} pts from 2022. The largest swing in the data is ${O.largest_swing_in_history_pts} pts, and One Nation's polling has no precedent here, so the polls column is an extrapolation, not a forecast.`;
$('th-polls').textContent = 'Polls (' + Math.abs(O.scenarios.polls).toFixed(1) + ')';
const heat = (p) => `background: color-mix(in srgb, var(--down) ${Math.round(70 * p)}%, transparent)`;
const vsl = { COAL: 'v Coalition', ALP: 'v Labor', GRN: 'v Greens', IND: 'v independent' };
const M = O.members.filter(m => m.p_polls !== undefined).sort((a, b) => b['p_-6'] - a['p_-6']);
function draw(n) {
  document.querySelector('#tbl-26 tbody').innerHTML = M.slice(0, n).map(m => `<tr><td>${m.seat}${m.vs !== 'ALP' && m.vs !== 'COAL' ? ' *' : ''}<div class="note">${dotp(m.party)}${m.member}</div></td><td class="ft">${vsl[m.vs] || m.vs}</td><td class="n num">${m.margin_pts.toFixed(1)}</td>` +
    ['p_-3', 'p_-6', 'p_polls'].map(k => `<td class="p" style="${heat(m[k])}">${pc(m[k])}</td>`).join('') + '</tr>').join('');
}
draw(20);
document.querySelectorAll('#seg button').forEach(b => b.addEventListener('click', () => { document.querySelectorAll('#seg button').forEach(x => x.setAttribute('aria-pressed', x === b)); draw(+b.dataset.n); }));
</script>
'''
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT, 'w').write('<title>Who Loses</title>\n' + head + body.replace('__DATA__', data))
print(OUT)
