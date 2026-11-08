"""Build the private EBA Dark page for the cross-level analysis (data/analysis/cross_level.json), reusing the member page's styles."""
import json, sys, re, os
R = json.load(open(sys.argv[1])); OUT = sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>') + len('</style>')]
head = head.replace('main section { min-width: 0; }', 'main section { min-width: 0; }\n.split { display: grid; grid-template-columns: minmax(0,1fr); gap: 12px; } .split figure { max-width: 520px; }')
data = json.dumps({k: R[k] for k in ('split_tickets', 'federal_member_changes', 'statewide')}, separators=(',', ':'))

body = r'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>Analysis 1 · part 3</span></div>
  <h1>Two levels</h1>
  <p>Victorians vote for two parliaments, often at the same school hall. How much does the local member at each level move the vote, does a change of federal member reach state voting, and how do state elections treat the party running Canberra? 2002 to 2022.</p>
</div></header>

<main><div class="wrap">

<section>
  <p class="lede">Local members pull their own level's vote towards their party by about <b class="num" id="t-mem"></b> in each direction, so the same polling place splits its ticket around them. A change of federal member does not carry into state voting. And at five of the last six state elections the party governing federally lost ground, by <b class="num" id="t-fed"></b> on average.</p>
  <div class="findings" id="findings"></div>
</section>

<section>
  <h2>Split tickets at the same polling place</h2>
  <p>Each state election is paired with the federal election nearest in time, and the same venues are compared: a party's state share minus its federal share. Where the sitting state member standing again is from that party, the gap moves towards the state vote; where the sitting federal member is from that party, it moves towards the federal vote. Comparing venues in the same state district that sit in different federal divisions isolates the federal member, and venues in the same division split across state districts isolate the state member. Both give the same answer.</p>
  <figure><div id="coef"></div>
  <figcaption>Effect on the state-minus-federal gap of the local member at each level being from the party (+) rather than its main rival (−), per side. 90% intervals from a bootstrap over districts. Pooled: all venue pairs with election-pair effects. Within: compared only with venues in the same state district (federal member) or the same federal division (state member).</figcaption></figure>
  <h3 style="margin-top:18px">Federal independents stay federal</h3>
  <p>Where a federal independent holds the seat (Indi from 2013, Kooyong and Goldstein from 2022), Labor and the Coalition both run <b class="num" id="t-ind"></b> above their federal shares at state elections (wide intervals: only a few seats). The independent vote does not carry over to the state ballot, where no comparable independent is usually standing, and returns to the major parties.</p>
</section>

<section>
  <h2>The mood of the pairing</h2>
  <p>The average gap between a party's state and federal vote at the same venues swings by election, which is the statewide mood of each contest more than anything local.</p>
  <div class="split">
    <figure><div id="gaps"></div><figcaption>Average state share minus federal share at shared venues, per pairing (state election shown). Red Labor, blue Coalition.</figcaption></figure>
    <div class="tablewrap"><table id="tbl-state"><thead><tr><th>State election</th><th>Governing federally</th><th class="n">Months since federal election</th><th class="n">Swing to that party</th></tr></thead><tbody></tbody></table></div>
  </div>
</section>

<section>
  <h2>A new federal member does not move the state vote</h2>
  <p>Between consecutive state elections, about <span class="num" id="t-flipn"></span> of the venues found their federal member had changed party. Within the same state district and election, their state swing differs from neighbours whose federal member stayed by only <span class="num" id="t-flip"></span> per side, and the interval includes zero. State swings do follow federal swings a little at the same venue (a slope of about <span class="num" id="t-slope"></span>), but the federal member's party adds nothing beyond that.</p>
</section>

<section>
  <h2>Reading it for 2026</h2>
  <ul class="plain">
    <li>Labor governs in Canberra (re-elected May 2025, about 19 months before polling day) and in Spring Street. In the history above, the federally governing party lost ground at five of six state elections, including both times Labor held both (2010 and 2022). With only six elections, and federal and state incumbency tangled together in half of them, treat it as a headwind to watch rather than a number to plug in.</li>
    <li>Seats where a federal independent holds the overlapping division (Kooyong and Goldstein against Kew, Hawthorn, Brighton, Sandringham, Caulfield) should not be expected to deliver a teal-sized independent vote at state level unless a strong state independent stands.</li>
    <li>The state member's own personal vote (analysis 1) is the one that matters for state seats; the federal member's is not inherited.</li>
  </ul>
</section>

<section>
  <h2>Caveats</h2>
  <ul class="plain">
    <li>Paired elections are up to 12 months apart (2006 with 2007), so part of each gap is change over time; the election-pair effects absorb the average of it.</li>
    <li>Venues move and catchments shift between elections, adding noise but not obvious bias.</li>
    <li>The federal side of the question (do Victorians punish the state government at federal elections?) needs the national swing as a yardstick, which is not in the Atlas yet.</li>
  </ul>
</section>

<section><h3>Next</h3><p class="note">Code: <code>src/cross_level.py</code>; results in <code>data/analysis/cross_level.json</code>. Uses the member history from <code>src/member_effects.py</code>.</p></section>

</div></main>

<script>
const D = __DATA__;
const f = (v, d = 1) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d) + ' pts';
const $ = (id) => document.getElementById(id);
const ST = D.split_tickets, FM = D.federal_member_changes, SW = D.statewide;
const all = [ST.ALP.pooled.xs.pts, ST.COAL.pooled.xs.pts, -ST.ALP.pooled.xf.pts, -ST.COAL.pooled.xf.pts];
$('t-mem').textContent = Math.min(...all).toFixed(1) + '–' + Math.max(...all).toFixed(1) + ' pts';
$('t-fed').textContent = f(SW.mean_swing_to_federal_government_party).replace('−', '');
$('t-ind').textContent = 'about ' + Math.round(ST.ALP.pooled.ind_fed.pts) + '–' + Math.round(ST.COAL.pooled.ind_fed.pts) + ' pts';
$('findings').innerHTML = [
  [f(ST.ALP.within_federal_division.xs.pts), 'State member, state vote', 'Labor; Coalition ' + f(ST.COAL.within_federal_division.xs.pts) + '. Same federal division, different state districts.', 'up'],
  [f(ST.ALP.within_state_district.xf.pts), 'Federal member, state-minus-federal gap', 'The federal member pulls the federal vote their way. Labor; Coalition ' + f(ST.COAL.within_state_district.xf.pts) + '.', 'down'],
  [f(FM.ALP.member_only.dmem.pts), 'New federal member, state swing', 'Interval ' + f(FM.ALP.member_only.dmem.lo) + ' to ' + f(FM.ALP.member_only.dmem.hi) + ': no detectable spillover.', ''],
  [f(SW.mean_swing_to_federal_government_party), 'Party governing federally, at state elections', 'Average swing, six elections; it gained only in 2006.', 'down']
].map(([n, l, s, c]) => `<div class="finding"><div class="big ${c}">${n}</div><div class="lab">${l}</div><div class="sub">${s}</div></div>`).join('');
// coefficient plot
(function () {
  const rows = [['State member', 'Labor', ST.ALP.pooled.xs, ST.ALP.within_federal_division.xs], ['State member', 'Coalition', ST.COAL.pooled.xs, ST.COAL.within_federal_division.xs],
                ['Federal member', 'Labor', ST.ALP.pooled.xf, ST.ALP.within_state_district.xf], ['Federal member', 'Coalition', ST.COAL.pooled.xf, ST.COAL.within_state_district.xf]];
  const W = 760, rowH = 50, top = 26, left = 150, right = 150, H = top + rowH * rows.length + 26, lo = -4, hi = 4;
  const x = v => left + (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo) * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" style="min-width:540px" role="img" aria-label="Member effects on split tickets">`;
  for (let v = lo; v <= hi; v++) s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 22}" stroke="var(--line)" stroke-width="${v ? 1 : 1.5}" ${v ? 'stroke-dasharray="2 3"' : ''}/><text class="tick" x="${x(v)}" y="${H - 6}" text-anchor="middle">${v > 0 ? '+' : ''}${v}</text>`;
  s += `<text class="tick" x="${x(-3.9)}" y="12">← towards the federal vote</text><text class="tick" x="${x(3.9)}" y="12" text-anchor="end">towards the state vote →</text>`;
  rows.forEach(([who, p, a, b], i) => {
    const y = top + i * rowH + rowH / 2, col = p === 'Labor' ? 'var(--alp)' : 'var(--coal)';
    s += `<text x="0" y="${y - 2}">${who}</text><text x="0" y="${y + 14}" class="tick">${p}</text>`;
    s += `<line x1="${x(a.lo)}" x2="${x(a.hi)}" y1="${y - 7}" y2="${y - 7}" stroke="${col}" stroke-width="3" stroke-linecap="round"/><circle cx="${x(a.pts)}" cy="${y - 7}" r="5.5" fill="${col}"/>`;
    s += `<line x1="${x(b.lo)}" x2="${x(b.hi)}" y1="${y + 8}" y2="${y + 8}" stroke="${col}" stroke-width="3" stroke-linecap="round" opacity=".55"/><circle cx="${x(b.pts)}" cy="${y + 8}" r="5.5" fill="var(--surface)" stroke="${col}" stroke-width="2"/>`;
    s += `<text class="tick" x="${x(Math.max(a.hi, b.hi)) + 8}" y="${y + 4}">${f(a.pts)} · ${f(b.pts)}</text>`;
  });
  s += `<circle cx="${left}" cy="${H - 34 + 26}" r="0"/>`;
  $('coef').innerHTML = s + '</svg><p class="note" style="margin:6px 0 0">Filled: pooled. Hollow: within the same district or division.</p>';
})();
// gap bars
(function () {
  const pairs = Object.keys(ST.ALP.mean_gap_by_pair), W = 360, H = 230, l = 40, r = 10, t = 14, b = 34, lo = -8, hi = 8;
  const y = v => t + (hi - v) / (hi - lo) * (H - t - b), bw = (W - l - r) / pairs.length;
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Average state minus federal gap by pairing">`;
  for (let v = lo; v <= hi; v += 4) s += `<line x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)" ${v ? 'stroke-dasharray="2 3"' : 'stroke-width="1.5"'}/><text class="tick" x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${v > 0 ? '+' : ''}${v}</text>`;
  pairs.forEach((p, i) => { const cx = l + bw * i + bw / 2;
    [['ALP', 'var(--alp)', -8], ['COAL', 'var(--coal)', 2]].forEach(([k, col, dx]) => { const v = ST[k].mean_gap_by_pair[p]; s += `<rect x="${cx + dx}" y="${Math.min(y(v), y(0))}" width="7" height="${Math.abs(y(v) - y(0))}" fill="${col}"/>`; });
    s += `<text class="tick" x="${cx}" y="${H - 12}" text-anchor="middle">${p.slice(3)}</text>`; });
  $('gaps').innerHTML = s + '</svg>';
})();
document.querySelector('#tbl-state tbody').innerHTML = SW.rows.map(r => `<tr><td>${r.election.slice(3)}</td><td><span class="dot" style="background:${r.federal_government === 'ALP' ? 'var(--alp)' : 'var(--coal)'}"></span>${r.federal_government === 'ALP' ? 'Labor' : 'Coalition'}${r.federal_government === r.state_government_going_in ? ' (also state)' : ''}</td><td class="n num">${Math.round(r.months_since_federal_election)}</td><td class="n num" style="color:${r.swing_to_federal_government_party > 0 ? 'var(--up)' : 'var(--down)'}">${f(r.swing_to_federal_government_party)}</td></tr>`).join('');
$('t-flipn').textContent = Math.round(100 * FM.ALP.flipped / FM.ALP.venues) + '%';
$('t-flip').textContent = f(FM.ALP.member_only.dmem.pts) + ' (Labor) and ' + f(FM.COAL.member_only.dmem.pts) + ' (Coalition)';
$('t-slope').textContent = FM.ALP.member_and_federal_swing.fswing.slope.toFixed(2) + '–' + FM.COAL.member_and_federal_swing.fswing.slope.toFixed(2);
</script>
'''
open(OUT, 'w').write('<title>Two Levels</title>\n' + head + body.replace('__DATA__', data))
print(OUT)
