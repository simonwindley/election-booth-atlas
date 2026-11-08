"""Build the private EBA Dark page for the boundary analysis (data/analysis/boundary_effects.json; also reads notionals.json
and seat_loss.json from the same folder). Usage: python3 tools/dark/build_boundary_page.py data/analysis/boundary_effects.json analysis/dark/new_lines.html"""
import json, sys, os
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
d = os.path.dirname(os.path.abspath(sys.argv[1]))
SL = {}
if os.path.exists(os.path.join(d, 'seat_loss.json')):
    _s = json.load(open(os.path.join(d, 'seat_loss.json')))
    SL = dict(_s.get('notional_check', {}), redistribution_or=next((p['odds_ratio'] for p in _s['predictors'] if p['key'] == 'redistribution'), None))
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>')] + '''
#tbl-red th, #tbl-flip th { white-space: normal; vertical-align: bottom; }
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
</style>'''
keep = {'check': R['check'], 'redistributions': R['redistributions'], 'flips': R['flips'], 'flips_summary': R['flips_summary'],
        'territory': {k: v for k, v in R['territory'].items()}, 'seat_loss': SL}
data = json.dumps(keep, separators=(',', ':'))

body = r'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 2</span></div>
  <h1>New lines</h1>
  <p>Seven redistributions in the Atlas: Victorian districts redrawn for 2002, 2014 and 2022, federal divisions for 2010, 2019, 2022 and 2025. We rebuilt each previous election on the new boundaries, checked it against the published notionals, and asked what new lines do to seats and members.</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">Our notional results land within half a point of Antony Green's on average. A redistribution moves the typical seat's margin by about a point. Seats handed to the other side on paper are usually wafer-thin, and they fall the way uniform swing says they should. The one systematic error in a notional is the personal vote: voters moved in from an opposing member's seat swing towards their new member, by about <b class="num" id="t-terr"></b> for a seat made entirely of them, as the old member's personal vote unwinds.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>Checking the notionals</h2>
  <p>Votes at each election-day booth follow its catchment onto the new map, weighted by where people live (census SA1s). All other votes (postal, early, absent) follow the old seat's population. Two-party figures come from the Labor v Coalition counts, or are estimated from first preferences where the final two was something else. Against the published notional margins:</p>
  <figure><div id="scatter"></div><figcaption>Labor two-party share, notional: the Atlas against Antony Green (ABC), Labor v Coalition seats only. 2022 state (circles) and 2025 federal (squares). Points on the diagonal agree.</figcaption></figure>
</section>

<section>
  <h2>What each redistribution did</h2>
  <div class="tablewrap"><table id="tbl-red"><thead><tr><th>For</th><th class="n">Seats</th><th class="n">Abolished</th><th class="n">From namesake</th><th class="n">Margin shift</th><th class="n">Paper flips</th><th class="n">Won on paper side</th></tr></thead><tbody></tbody></table></div>
  <p class="note" style="margin-top:8px">From namesake: the share of a continuing seat's people who were in the seat of the same name before. Margin shift: notional two-party margin against the seat's own last result.</p>
</section>

<section>
  <h2>Do paper flips stick?</h2>
  <p>Sixteen seats changed hands on paper. The notional party won <b class="num" id="t-won"></b>. That sounds like notionals being wrong, but most were won by less than a point on paper (median <span class="num" id="t-med"></span>), so the election's swing decides them: uniform swing expected <b class="num" id="t-exp"></b>. In 2002 Labor's 8-point swing took back all four seats the new lines had handed the Liberals.</p>
  <div class="tablewrap"><table id="tbl-flip"><thead><tr><th>For</th><th>Seat</th><th>Paper change</th><th class="n">Paper margin</th><th class="n">Swing to paper side</th><th class="n">Uniform-swing chance</th><th>Won by</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>The cost of new territory</h2>
  <p>For <span class="num" id="t-n"></span> members standing again in a redrawn seat, their swing against the notional result (relative to the statewide swing on the same basis) was compared with where the seat's voters came from. Voters from the member's own old seat and from a same-party colleague's seat behave alike. Voters who came from an opposing member's seat swing towards the receiving member: that opposing member's personal vote, which the notional still counts, goes with them.</p>
  <div class="split">
    <figure><div id="terr"></div><figcaption>Average swing to the member relative to the state, by the share of the new seat that came from an opposing member's seat. Labels: members.</figcaption></figure>
    <div class="findings" id="terr-cards" style="grid-template-columns:minmax(0,1fr)"></div>
  </div>
  <p class="note" style="margin-top:10px">The same pattern appears at booth level (The Personal Vote: booths moved from another party's member swung 3.0 pts more to the receiving party), with a different method and data.</p>
</section>

<section>
  <h2>What changes in the models</h2>
  <ul class="plain">
    <li>The seat-loss model now uses notional margins in redrawn seats. Out-of-sample log loss improves by <span class="num" id="t-ll"></span> and the AUC from <span class="num" id="t-auc"></span>. "New boundaries" still carries a slightly higher risk of losing (odds ×<span class="num" id="t-or"></span>, not significant), which fits the territory effect: members carry less personal vote into new ground.</li>
    <li>For the next redistribution (federal, and Victoria for 2030), adjust each notional by about 3–4 pts × the share of the seat coming from an opposing member's seat, towards the new member's party. A seat that takes 20% of its voters from the other side's MP is about 0.7 pts better for its member than the notional says.</li>
    <li>2026 is fought on the 2022 boundaries, so no notionals are needed this time; the 2022 results stand as the baseline.</li>
  </ul>
</section>

<section>
  <h2>Caveats</h2>
  <ul class="plain">
    <li>Population comes from the census nearest in time: 2011 SA1s for the 1999 and 2010 results, 2016 for 2016 to 2019, 2021 for 2022. Growth areas in 1999 are the weakest link.</li>
    <li>1999 two-candidate counts are incomplete, so more of the 2002 notionals are estimated from first preferences.</li>
    <li>Members who moved to a differently named seat are not followed; the territory estimate uses 258 members who stayed put, and its interval is wide (it includes zero at the bottom end).</li>
  </ul>
</section>

<section><h3>Next</h3><p class="note">Code: <code>src/notional.py</code> (notionals, <code>data/analysis/notionals.json</code>) and <code>src/boundary_effects.py</code>. Re-run with <code>python3 tools/rerun_analyses.py --trigger redistribution_fed</code>.</p></section>

</div></main>

<script>
const D = __DATA__;
const $ = (id) => document.getElementById(id);
const pts = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
const C = D.check, T = D.territory, F = D.flips_summary, SL = D.seat_loss;
$('t-terr').textContent = T.other_party_pts_per_100pct.toFixed(1) + ' pts';
$('findings').innerHTML = [
  [C.vic2022.mean_abs_diff.toFixed(2), 'Points from the published notionals', 'Mean absolute difference, 2022 state (' + C.vic2022.seats + ' seats); 2025 federal ' + C.fed2025.mean_abs_diff.toFixed(2) + '.', ''],
  [F.won_by_notional_party + ' of ' + F.n, 'Paper flips won by the notional side', 'Uniform swing expected ' + F.expected_on_uniform_swing + '.', ''],
  [pts(T.other_party_pts_per_100pct), 'Swing from opposing-member voters', 'Points to the receiving member per 100% of the seat. Interval ' + pts(T.other_ci[0]) + ' to ' + pts(T.other_ci[1]) + '.', 'up'],
  [pts(T.same_party_pts_per_100pct), 'From a same-party colleague', 'No detectable difference from the member’s own voters.', '']
].map(([n, l, s, c]) => `<div class="finding"><div class="big ${c}">${n}</div><div class="lab">${l}</div><div class="sub">${s}</div></div>`).join('');
// scatter
(function () {
  const W = 420, H = 420, m = 40, lo = 25, hi = 85, x = v => m + (v - lo) / (hi - lo) * (W - m - 12), y = v => H - m - (v - lo) / (hi - lo) * (H - m - 12);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:460px" role="img" aria-label="Atlas against published notional two-party shares">`;
  for (let v = 30; v <= 80; v += 10) s += `<line x1="${x(v)}" x2="${x(v)}" y1="${y(lo)}" y2="${y(hi)}" stroke="var(--line)" stroke-dasharray="2 3"/><line y1="${y(v)}" y2="${y(v)}" x1="${x(lo)}" x2="${x(hi)}" stroke="var(--line)" stroke-dasharray="2 3"/><text class="tick" x="${x(v)}" y="${H - m + 16}" text-anchor="middle">${v}</text><text class="tick" x="${m - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  s += `<line x1="${x(lo)}" y1="${y(lo)}" x2="${x(hi)}" y2="${y(hi)}" stroke="var(--fg-3)"/><line x1="${x(50)}" x2="${x(50)}" y1="${y(lo)}" y2="${y(hi)}" stroke="var(--fg-3)" stroke-width=".6"/><line y1="${y(50)}" y2="${y(50)}" x1="${x(lo)}" x2="${x(hi)}" stroke="var(--fg-3)" stroke-width=".6"/>`;
  s += `<text class="tick" x="${(x(lo) + x(hi)) / 2}" y="${H - 6}" text-anchor="middle">Published notional (Labor 2PP %)</text><text class="tick" transform="translate(10 ${(y(lo) + y(hi)) / 2}) rotate(-90)" text-anchor="middle">Atlas notional</text>`;
  C.vic2022.rows.forEach(r => { const col = r.green >= 50 ? 'var(--alp)' : 'var(--coal)'; s += `<circle cx="${x(r.green)}" cy="${y(r.atlas)}" r="3.6" fill="${col}" fill-opacity=".75"><title>${r.seat} (state): published ${r.green.toFixed(1)}, Atlas ${r.atlas.toFixed(1)}</title></circle>`; });
  C.fed2025.rows.forEach(r => { const col = r.green >= 50 ? 'var(--alp)' : 'var(--coal)'; s += `<rect x="${x(r.green) - 3.5}" y="${y(r.atlas) - 3.5}" width="7" height="7" fill="none" stroke="${col}" stroke-width="1.6"><title>${r.seat} (federal): published ${r.green.toFixed(1)}, Atlas ${r.atlas.toFixed(1)}</title></rect>`; });
  $('scatter').innerHTML = s + '</svg>';
})();
const E = (e) => (e.startsWith('fed') ? 'Federal ' : 'State ') + e.slice(-4);
document.querySelector('#tbl-red tbody').innerHTML = D.redistributions.map(r => `<tr><td>${E(r.for)}</td><td class="n num">${r.seats}</td><td class="n num" title="${r.abolished.join(', ')}">${r.abolished.length}</td><td class="n num">${Math.round(100 * r.median_from_namesake)}%</td><td class="n num">${r.mean_abs_shift_pts.toFixed(1)} pts</td><td class="n num">${r.notional_flips}</td><td class="n num">${r.flips_won_by_notional_party}</td></tr>`).join('');
$('t-won').textContent = F.won_by_notional_party + ' of ' + F.n; $('t-exp').textContent = F.expected_on_uniform_swing.toFixed(1); $('t-med').textContent = F.median_notional_margin_pts.toFixed(1) + ' pts';
const pn = { ALP: 'Labor', COAL: 'Coalition' };
document.querySelector('#tbl-flip tbody').innerHTML = D.flips.map(f => `<tr><td>${E(f.for)}</td><td>${f.seat}${f.new_seat ? ' (new)' : ''}</td><td>${pn[f.was]} → ${pn[f.notional]}</td><td class="n num">${f.notional_margin_pts.toFixed(1)}</td><td class="n num">${pts(f.swing_to_notional_party_pts)}</td><td class="n num">${Math.round(100 * f.p_uniform)}%</td><td><span class="dot" style="background:${f.winner === 'ALP' ? 'var(--alp)' : 'var(--coal)'}"></span>${pn[f.winner] || f.winner}${f.notional_party_won ? '' : ' (stayed)'}</td></tr>`).join('');
// territory bins
(function () {
  const bins = [['none', 0, 0.001], ['under 10%', 0.001, 0.1], ['10–30%', 0.1, 0.3], ['30%+', 0.3, 1.01]];
  const rows = bins.map(([l, a, b]) => { const s = T.rows.filter(r => r.other_party >= a && r.other_party < b); return [l, s.length, s.length ? 100 * s.reduce((t, r) => t + r.swing_rel, 0) / s.length : 0]; });
  const W = 380, H = 230, l = 40, r = 10, t = 14, b = 40, lo = -2, hi = 3, y = v => t + (hi - v) / (hi - lo) * (H - t - b), bw = (W - l - r) / rows.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Relative swing by share from opposing members">`;
  for (let v = lo; v <= hi; v++) s += `<line x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" ${v ? 'stroke-dasharray="2 3"' : 'stroke-width="1.5"'}/><text class="tick" x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${v > 0 ? '+' : ''}${v}</text>`;
  rows.forEach(([lab, n, v], i) => { const cx = l + bw * i + bw / 2; s += `<rect x="${cx - 18}" y="${Math.min(y(v), y(0))}" width="36" height="${Math.max(1, Math.abs(y(v) - y(0)))}" fill="${v >= 0 ? 'var(--up)' : 'var(--down)'}"/><text class="tick" x="${cx}" y="${(v >= 0 ? y(v) - 5 : y(v) + 13)}" text-anchor="middle">${pts(v)}</text><text class="tick" x="${cx}" y="${H - 22}" text-anchor="middle">${lab}</text><text class="tick" x="${cx}" y="${H - 8}" text-anchor="middle">n=${n}</text>`; });
  $('terr').innerHTML = s + '</svg>';
})();
$('t-n').textContent = T.n;
$('terr-cards').innerHTML = `<div class="finding"><div class="big up">${pts(T.other_party_pts_per_100pct)}</div><div class="lab">per 100% from an opposing member’s seat</div><div class="sub">Regression of relative swing on the two shares; 90% interval ${pts(T.other_ci[0])} to ${pts(T.other_ci[1])}.</div></div><div class="finding"><div class="big">${pts(T.same_party_pts_per_100pct)}</div><div class="lab">per 100% from a same-party colleague</div><div class="sub">Interval ${pts(T.same_ci[0])} to ${pts(T.same_ci[1])}.</div></div>`;
if (SL.loeo_logloss_old_margins) { $('t-ll').textContent = (SL.loeo_logloss_old_margins - SL.loeo_logloss_notional).toFixed(1) + ' nats'; $('t-auc').textContent = SL.loeo_auc_old_margins.toFixed(3) + ' to ' + SL.loeo_auc_notional.toFixed(3); $('t-or').textContent = SL.redistribution_or ? SL.redistribution_or.toFixed(2) : ''; }
</script>
'''
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT, 'w').write('<title>New Lines</title>\n' + head + body.replace('__DATA__', data))
print(OUT)
