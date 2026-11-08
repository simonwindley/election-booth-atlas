"""Build the private EBA Dark page for the member-effects analysis from data/analysis/member_effects.json."""
import json, sys
R = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
keep = {k: R[k] for k in ('all', 'state', 'federal', 'party_ALP', 'party_COAL', 'leave_one_out')}
keep['booth'] = {k: v for k, v in R['booth'].items() if k != 'seats_detail'}
keep['outlook'] = R['outlook_2026']
keep['tenure'] = R['tenure']
data = json.dumps(keep, separators=(',', ':'))

html = r'''<title>The Personal Vote</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:ital,wght@0,500;0,600;1,400&display=swap">
<style>
/* Layout: a single reading column in the Atlas's paper-and-ink style, with wide figures and one sortable table */
:root {
  --bg: #f4f3ee; --surface: #fbfaf7; --surface-2: #ece9e1; --line: #d6d2c6;
  --fg: #1f2126; --fg-2: #5a5d66; --fg-3: #8b8e97; --accent: #1f5f66; --dark: #23262c; --dark-fg: #e8e6df;
  --alp: #e0463f; --coal: #2a62c9; --grn: #1f7a1f; --ind: #7a7f8a; --up: #1f6a4a; --down: #9a3d2e;
  --font-ui: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
  --font-display: "IBM Plex Serif", Georgia, serif;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #15171b; --surface: #1d2025; --surface-2: #272b32; --line: #363b44; --fg: #e8e6df; --fg-2: #b4b2aa; --fg-3: #7d8089;
  --accent: #6ac2cc; --dark: #0e1013; --dark-fg: #e8e6df; --alp: #ea5a54; --coal: #5b8ae6; --grn: #3a9a3a; --ind: #9aa0ab; --up: #5fbf8f; --down: #e08870; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #15171b; --surface: #1d2025; --surface-2: #272b32; --line: #363b44; --fg: #e8e6df; --fg-2: #b4b2aa; --fg-3: #7d8089;
  --accent: #6ac2cc; --dark: #0e1013; --dark-fg: #e8e6df; --alp: #ea5a54; --coal: #5b8ae6; --grn: #3a9a3a; --ind: #9aa0ab; --up: #5fbf8f; --down: #e08870; color-scheme: dark }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font: 15px/1.6 var(--font-ui); }
.band { background: var(--dark); color: var(--dark-fg); }
.wrap { max-width: 860px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
header .wrap { padding-block: 28px 30px; display: grid; gap: 10px; }
.tag { font: 500 11px/1 var(--font-mono); letter-spacing: .14em; text-transform: uppercase; color: #9aa0ab; display: flex; gap: 14px; flex-wrap: wrap; }
.tag b { color: #6ac2cc; font-weight: 500; }
h1 { font: 600 clamp(28px, 5vw, 40px)/1.15 var(--font-display); margin: 0; text-wrap: balance; }
header p { margin: 0; max-width: 62ch; color: #c9c7c0; }
main .wrap { padding-block: 26px 60px; display: grid; gap: 34px; grid-template-columns: minmax(0, 1fr); }
main section { min-width: 0; }
h2 { font: 600 21px/1.3 var(--font-display); margin: 0 0 8px; text-wrap: balance; }
h3 { font: 500 11px/1.2 var(--font-ui); text-transform: uppercase; letter-spacing: .1em; color: var(--fg-3); margin: 0 0 8px; }
p { margin: 0 0 10px; max-width: 66ch; }
.lede { font-size: 17px; }
.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.findings { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
.finding { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 14px 12px; display: grid; gap: 4px; align-content: start; }
.finding .big { font: 500 28px/1 var(--font-mono); font-variant-numeric: tabular-nums; }
.finding .big.up { color: var(--up); } .finding .big.down { color: var(--down); }
.finding .lab { font-weight: 600; } .finding .sub { color: var(--fg-2); font-size: 13px; }
figure { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px; overflow-x: auto; }
figcaption { font-size: 13px; color: var(--fg-2); margin-top: 8px; max-width: 70ch; }
svg text { font-family: var(--font-ui); fill: var(--fg-2); font-size: 12px; }
svg .tick { fill: var(--fg-3); font-family: var(--font-mono); font-size: 11px; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; margin-bottom: 10px; flex-wrap: wrap; }
.seg button { background: var(--surface); color: var(--fg-2); border: 0; padding: 6px 11px; font: 500 13px var(--font-ui); cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--bg); }
.seg button:focus-visible, th button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font-weight: 500; color: var(--fg-3); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; background: var(--surface-2); }
th button { all: unset; cursor: pointer; } th.n, td.n { text-align: right; }
tr:last-child td { border-bottom: 0; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; vertical-align: 0; }
.pill { display: inline-block; font-size: 12px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); color: var(--fg-2); }
.pill.open { border-color: var(--down); color: var(--down); } .pill.sophomore_gain, .pill.sophomore_held { border-color: var(--up); color: var(--up); }
.note { font-size: 13px; color: var(--fg-2); }
ul.plain { margin: 0; padding-left: 18px; max-width: 66ch; } ul.plain li { margin: 4px 0; }
code { font-family: var(--font-mono); font-size: 13px; background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
</style>

<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 1 of 3</span></div>
  <h1>The personal vote</h1>
  <p>How much is a sitting member worth to their party? Every Victorian state and federal seat held under the same name at two elections in a row, 1999 to 2025, swing compared within the same election and party.</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">A member's first re-election is worth about <b class="num" id="t-gain"></b> to their party when they won the seat from someone else, and losing a sitting member costs about <b class="num" id="t-open"></b>. Victoria has <b id="t-open26"></b> districts without their sitting member in 2026.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>The estimates</h2>
  <div class="seg" role="group" aria-label="Which elections" id="seg-scope"></div>
  <figure><div id="forest"></div>
  <figcaption>Change in the member's party's first-preference share, against a long-serving member standing again (zero), after taking out the swing to that party at the same election. Bars are 90% intervals from 1,000 bootstrap resamples of seats within each election.</figcaption></figure>
</section>

<section>
  <h2>How it was measured</h2>
  <p>For each seat contested under the same name at consecutive elections, the member at dissolution is the last winner, or a by-election winner since. Their party's first-preference share is compared before and after, and the member is sorted into one of four groups: a <b>veteran</b> (already the member before the previous election, standing again), a <b>sophomore</b> (first elected last time, standing again: by gaining the seat, by holding it after a same-party retirement, or at a by-election), or an <b>open seat</b> (the member is not on the ballot; the party runs someone new). Each seat's change is compared only with seats the same party held at the same election, so a statewide landslide does not show up as a member effect.</p>
  <p class="note"><span class="num" id="t-n"></span> seat-elections in the fit. Seats renamed by a redistribution drop out, because the before-and-after comparison needs the same seat. By-elections that changed the member mid-term are taken from a hand-kept list (18 of them since 1999); those loaded in the Atlas since 2023 come from the results.</p>
</section>

<section>
  <h2>A booth-level check: voters who change members</h2>
  <p>Redistributions move booths between seats, so within one seat some voters have had the member before and some are new to them. At venues used at both elections, booths moved in from a seat held by <b>another party</b> swung <b class="num" id="t-other"></b> more towards the receiving member's party than the member's own booths did. Those voters lost their previous member, and with them that member's personal vote. Booths moved in from a <b>same-party</b> member behaved almost the same as the member's own (<span class="num" id="t-same"></span>), so at booth level the personal vote attached to one member rather than another of the same party is small.</p>
  <p class="note">Booth swings are noisy and booth catchments change, so this is a check on direction rather than a second estimate of size. The full boundary-effects analysis is next.</p>
</section>

<section>
  <h2>How sturdy is it?</h2>
  <ul class="plain" id="robust"></ul>
</section>

<section>
  <h2>Long-serving members</h2>
  <p>Counting each member's consecutive wins in the seat shows when the personal vote forms and whether it keeps growing. It forms in the first term and then stops: standing again after three, four or five terms is worth about the same as after two. There is no sign of a "tired member" fade either.</p>
  <p>What a member has built shows when they leave. A member who leaves after one term costs their party nothing (<span class="num" id="t-o1"></span>). After two terms or more, the party loses about <span class="num" id="t-o2"></span> to <span class="num" id="t-o3"></span>.</p>
  <figure><div id="tenure"></div>
  <figcaption>Member's party first-preference change by how long the member had held the seat, against a member standing again after two terms (zero). Green: the member stands again. Red: the member leaves and the party runs someone new. 90% intervals. Members already in place when the series starts (1999 state, 2004 federal) are counted from then, so their tenure is a minimum; leaving them out gives the same pattern.</figcaption></figure>
  <h3 style="margin-top:18px">Leaders' own seats</h3>
  <p>Premiers have done better in their own seats than their party did in its other seats, by <span class="num" id="t-prem"></span> on average; opposition leaders slightly worse (<span class="num" id="t-opp"></span>). There are only a dozen cases, and one of them (Napthine in South-West Coast, 2014) carries much of the premiers' figure.</p>
  <div class="tablewrap"><table id="tbl-lead"><thead><tr><th>Election</th><th>Seat</th><th>Leader</th><th>Role</th><th class="n">Against party's other seats</th></tr></thead><tbody></tbody></table></div>
</section>

<section>
  <h2>2026: who has a member effect working for or against them</h2>
  <p>Applying the estimates to the 88 districts. Open seats use the penalty for the departing member's length of service. The expected effect is relative to a veteran member standing again, before any statewide swing. This is an ingredient for the seat projections, not a forecast on its own.</p>
  <div class="seg" role="group" aria-label="Filter districts" id="seg-cat"></div>
  <div class="tablewrap"><table id="tbl"><thead><tr>
    <th><button data-k="seat">District</button></th><th><button data-k="member">Member at dissolution</button></th><th><button data-k="party">Party</button></th>
    <th><button data-k="category">Situation</button></th><th class="n"><button data-k="terms">Terms in seat</button></th><th class="n"><button data-k="expected_pts">Expected effect</button></th></tr></thead><tbody></tbody></table></div>
  <p class="note" id="t-flag"></p>
</section>

<section>
  <h2>Caveats</h2>
  <ul class="plain">
    <li>Sophomore gains are measured from a result that was already good for the party, so the surge is if anything understated: seats won on a swing tend to drift back.</li>
    <li>Members choose when to retire. Some leave seats they expect to lose, which would make the open-seat penalty look larger than the pure loss of a known face.</li>
    <li>By-election winners are a small group (16) with wide intervals; the 2026 table gives them the state estimate but marks it low confidence.</li>
    <li>First preferences only. A member effect on preferences and two-candidate results is a later step.</li>
  </ul>
</section>

<section>
  <h3>Next</h3>
  <p class="note">Analysis 2: boundary effects (notional results, transferred voters, how much of a swing is redrawn lines). Analysis 3: demographic change against swing, 2006 to 2021. Code: <code>src/member_effects.py</code>; outputs in <code>data/analysis/</code>.</p>
</section>

</div></main>

<script>
const D = __DATA__;
const LAB = { sophomore_gain: 'First defence after a gain', sophomore_held: 'First defence after a same-party handover', sophomore_byelection: 'First defence after a by-election win', open: 'Member not standing (open seat)', veteran: 'Veteran standing again' };
const SHORT = { sophomore_gain: 'Sophomore (gain)', sophomore_held: 'Sophomore (held)', sophomore_byelection: 'Sophomore (by-election)', open: 'Open seat', veteran: 'Veteran' };
const PCOL = { ALP: 'var(--alp)', COAL: 'var(--coal)', GRN: 'var(--grn)', IND: 'var(--ind)' };
const PNAME = { ALP: 'Labor', COAL: 'Coalition', GRN: 'Greens', IND: 'Independent' };
const nm = (s) => s.replace(/\b([A-Z])([A-Z'’-]+)\b/g, (m, a, b) => a + b.toLowerCase()).replace(/\bMc([a-z])/g, (m, c) => 'Mc' + c.toUpperCase());
const f = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d) + ' pts';
const $ = (id) => document.getElementById(id);
const CATS = ['sophomore_gain', 'sophomore_held', 'sophomore_byelection', 'open'];
$('t-gain').textContent = f(D.all.sophomore_gain.pts); $('t-open').textContent = f(D.all.open.pts).replace('−', '');
$('t-open26').textContent = D.outlook.filter(x => x.category === 'open').length;
$('t-n').textContent = D.all.n;
$('t-other').textContent = f(-D.booth.gap_other_party.pts).replace('+', '');
$('t-same').textContent = f(D.booth.gap_same_party.pts) + ', interval ' + f(D.booth.gap_same_party.lo) + ' to ' + f(D.booth.gap_same_party.hi);
// headline cards
$('findings').innerHTML = CATS.map(k => { const e = D.all[k]; return `<div class="finding"><div class="big ${e.pts >= 0 ? 'up' : 'down'}">${f(e.pts)}</div><div class="lab">${SHORT[k]}</div><div class="sub">${LAB[k]}. 90%: ${f(e.lo)} to ${f(e.hi)}; ${D.all.counts[k]} cases.</div></div>`; }).join('');
// forest plot
const SCOPES = [['all', 'All'], ['state', 'State'], ['federal', 'Federal'], ['party_ALP', 'Labor members'], ['party_COAL', 'Coalition members']];
let scope = 'all';
function forest() {
  const S = D[scope], W = 760, rowH = 46, top = 26, left = 250, right = 30, H = top + rowH * CATS.length + 26;
  const lo = -8, hi = 8, x = (v) => left + (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo) * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:560px" role="img" aria-label="Member effect estimates with intervals">`;
  for (let v = lo; v <= hi; v += 2) s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 8}" y2="${H - 22}" stroke="var(--line)" stroke-width="${v === 0 ? 1.5 : 1}" ${v === 0 ? '' : 'stroke-dasharray="2 3"'}/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v > 0 ? '+' : ''}${v}</text>`;
  s += `<text x="${x(0)}" y="12" text-anchor="middle" class="tick">veteran = 0</text>`;
  CATS.forEach((k, i) => { const e = S[k], y = top + i * rowH + rowH / 2, col = e.pts >= 0 ? 'var(--up)' : 'var(--down)';
    s += `<text x="0" y="${y - 3}">${SHORT[k]}</text><text x="0" y="${y + 13}" class="tick">n = ${S.counts[k]}</text>`;
    s += `<line x1="${x(e.lo)}" x2="${x(e.hi)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="3" stroke-linecap="round"/><circle cx="${x(e.pts)}" cy="${y}" r="6" fill="${col}"/>`;
    s += `<text x="${Math.min(x(e.hi) + 8, W - 4)}" y="${y + 4}" class="tick" text-anchor="${x(e.hi) + 60 > W ? 'end' : 'start'}">${f(e.pts)}</text>`; });
  $('forest').innerHTML = s + '</svg>';
  $('seg-scope').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === scope));
}
$('seg-scope').innerHTML = SCOPES.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join('');
$('seg-scope').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { scope = b.dataset.v; forest(); } });
forest();
// robustness
const L = D.leave_one_out, rng = (k) => [Math.min(...Object.values(L).map(v => v[k])), Math.max(...Object.values(L).map(v => v[k]))];
$('robust').innerHTML = [
  `Leaving out any one election at a time, the gain sophomore effect stays between ${f(rng('sophomore_gain')[0])} and ${f(rng('sophomore_gain')[1])}, and the open-seat penalty between ${f(rng('open')[0])} and ${f(rng('open')[1])}.`,
  `Labor and Coalition members show the same pattern: sophomore gain ${f(D.party_ALP.sophomore_gain.pts)} and ${f(D.party_COAL.sophomore_gain.pts)}, open seat ${f(D.party_ALP.open.pts)} and ${f(D.party_COAL.open.pts)}.`,
  `State seats show a bigger first-defence bonus after a gain (${f(D.state.sophomore_gain.pts)}) than federal ones (${f(D.federal.sophomore_gain.pts)}, only ${D.federal.counts.sophomore_gain} cases). State districts are smaller, so a member can be known personally to more of the electorate.`,
  `The open-seat penalty is similar at both levels: ${f(D.state.open.pts)} state, ${f(D.federal.open.pts)} federal.`
].map(t => `<li>${t}</li>`).join('');
// tenure chart
const T = D.tenure.all;
$('t-o1').textContent = f(T.open_1.pts); $('t-o2').textContent = f(T.open_2.pts).replace('−', ''); $('t-o3').textContent = f(T.open_3.pts).replace('−', '') + ' (three terms)';
(function () {
  const groups = [['1 term', null, 'open_1', 'sophomore'], ['2 terms', 'base', 'open_2'], ['3 terms', 'stand_3', 'open_3'], ['4 terms', 'stand_4', 'open_4plus'], ['5+ terms', 'stand_5plus', null]];
  const W = 760, H = 300, l = 54, r = 16, t = 20, b = 46, lo = -7, hi = 5;
  const y = v => t + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * (H - t - b), gw = (W - l - r) / groups.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:540px" role="img" aria-label="Member effect by tenure">`;
  for (let v = lo; v <= hi; v += 1) if (v % 2 === 1 || v === 0) s += `<line x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" stroke-width="${v === 0 ? 1.5 : 1}" ${v ? 'stroke-dasharray="2 3"' : ''}/><text class="tick" x="${l - 8}" y="${y(v) + 4}" text-anchor="end">${v > 0 ? '+' : ''}${v}</text>`;
  const mark = (cx, e, col, label) => `<line x1="${cx}" x2="${cx}" y1="${y(e.hi)}" y2="${y(e.lo)}" stroke="${col}" stroke-width="3" stroke-linecap="round"/><circle cx="${cx}" cy="${y(e.pts)}" r="6" fill="${col}"/><text class="tick" x="${cx + 9}" y="${y(e.pts) + 4}">${label}</text>`;
  groups.forEach(([lab, st, op, soph], i) => {
    const cx = l + gw * i + gw / 2;
    s += `<text x="${cx}" y="${H - 22}" text-anchor="middle">${lab}</text>`;
    if (soph) s += mark(cx - 18, T.sophomore, 'var(--up)', f(T.sophomore.pts));
    if (st === 'base') s += `<circle cx="${cx - 18}" cy="${y(0)}" r="6" fill="none" stroke="var(--up)" stroke-width="2"/><text class="tick" x="${cx - 9}" y="${y(0) - 9}">baseline</text>`;
    else if (st) s += mark(cx - 18, T[st], 'var(--up)', f(T[st].pts));
    if (op) s += mark(cx + 18, T[op], 'var(--down)', f(T[op].pts));
  });
  s += `<text x="${l}" y="${H - 4}" class="tick">Tenure = consecutive wins in the seat before this election. Green: stands again. Red: leaves.</text>`;
  $('tenure').innerHTML = s + '</svg>';
})();
const LS = D.tenure.leaders_summary; $('t-prem').textContent = f(LS.premier_mean); $('t-opp').textContent = f(LS.opposition_mean);
document.querySelector('#tbl-lead tbody').innerHTML = D.tenure.leaders.map(x => `<tr><td>${x.election.replace('vic', 'State ').replace('fed', 'Federal ')}</td><td>${x.seat}</td><td><span class="dot" style="background:${PCOL[x.party]}"></span>${nm(x.member)}</td><td>${x.role}</td><td class="n num" style="color:${x.residual_pts > 0 ? 'var(--up)' : 'var(--down)'}">${f(x.residual_pts)}</td></tr>`).join('');
// 2026 table
let cat = 'all', sortK = 'expected_pts', sortDir = 1;
const CAT_BTNS = [['all', 'All 88'], ['open', 'Open seats'], ['sophomore_gain', 'Sophomore (gain)'], ['sophomore_held', 'Sophomore (held)'], ['sophomore_byelection', 'By-election members'], ['veteran', 'Veterans']];
$('seg-cat').innerHTML = CAT_BTNS.map(([v, l]) => `<button type="button" data-v="${v}">${l}${v === 'all' ? '' : ' (' + D.outlook.filter(x => x.category === v).length + ')'}</button>`).join('');
$('seg-cat').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { cat = b.dataset.v; table(); } });
document.querySelectorAll('#tbl th button').forEach(b => b.addEventListener('click', () => { const k = b.dataset.k; sortDir = sortK === k ? -sortDir : 1; sortK = k; table(); }));
function table() {
  const rows = D.outlook.filter(x => cat === 'all' || x.category === cat).sort((a, b) => (a[sortK] > b[sortK] ? 1 : a[sortK] < b[sortK] ? -1 : a.seat.localeCompare(b.seat)) * sortDir);
  document.querySelector('#tbl tbody').innerHTML = rows.map(x => `<tr><td>${x.seat}</td><td>${nm(x.member)}${x.not_on_declared_list ? ' *' : ''}</td><td><span class="dot" style="background:${PCOL[x.party] || 'var(--ind)'}"></span>${PNAME[x.party] || x.party}</td><td><span class="pill ${x.category}">${SHORT[x.category]}</span></td><td class="n num">${x.terms}${x.terms_at_least ? '+' : ''}</td><td class="n num" style="color:${x.expected_pts > 0 ? 'var(--up)' : x.expected_pts < 0 ? 'var(--down)' : 'var(--fg-3)'}">${x.expected_pts ? f(x.expected_pts) : '0'}${x.confidence === 'low' ? ' ?' : ''}</td></tr>`).join('');
  $('seg-cat').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === cat));
}
table();
const flagged = D.outlook.filter(x => x.not_on_declared_list).map(x => `${x.seat} (${x.member})`);
$('t-flag').textContent = (flagged.length ? `* Not on the declared candidate list and not in the retirement list, so counted as not standing: ${flagged.join(', ')}. ` : '') + '? By-election members: low confidence.';
</script>
'''
open(OUT, 'w').write(html.replace('__DATA__', data))
print(OUT, len(html) + len(data))
