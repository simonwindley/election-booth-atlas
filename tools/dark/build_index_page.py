"""Build the EBA Dark index, "The Question Book", from analysis/questions.json and analysis/runs.json.
Usage: python3 tools/dark/build_index_page.py [out.html]   (default analysis/dark/index.html)"""
import json, sys, os, html
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'analysis/dark/index.html')
reg = json.load(open(os.path.join(ROOT, 'analysis/questions.json')))
runs_p = os.path.join(ROOT, 'analysis/runs.json')
runs = json.load(open(runs_p)) if os.path.exists(runs_p) else {}
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_member_page.py')).read()
head = src[src.index('<meta name="claude:viewport-fit-sides"'):src.index('</style>')]
head += '''.q { border-top: 1px solid var(--line); padding: 14px 0; display: grid; gap: 6px; }
.q:first-of-type { border-top: 0; }
.q h4 { font: 600 16px/1.4 var(--font-ui); margin: 0; max-width: 66ch; }
.q .meta { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; font-size: 12px; color: var(--fg-3); }
.q .hl { color: var(--fg-2); margin: 0; }
.pill.done { border-color: var(--up); color: var(--up); } .pill.next { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
.pill.planned { border-style: dashed; } .pill.idea { border-style: dotted; color: var(--fg-3); }
.trig { font: 11px var(--font-mono); background: var(--surface-2); padding: 1px 6px; border-radius: 4px; color: var(--fg-2); }
a { color: var(--accent); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
.card b { display: block; font-size: 14px; } .card .when { font-size: 12px; color: var(--fg-3); margin-bottom: 6px; }
.card ul { margin: 0; padding-left: 16px; font-size: 13px; color: var(--fg-2); }
</style>'''
E = html.escape
T = reg['triggers']; Q = reg['questions']
groups = []
for q in Q:
    if q['group'] not in groups:
        groups.append(q['group'])
counts = {s: sum(q['status'] == s for q in Q) for s in ('done', 'next', 'planned', 'idea')}


def qhtml(q):
    r = runs.get(q['id'], {})
    page = q.get('page') or {}
    link = f' · <a href="{E(page["artifact"])}">{E(page["title"])}</a>' if page.get('artifact') else (f' · page: {E(page["title"])}' if page.get('title') else '')
    ran = f'ran {E(r["at"][:10])}' if r.get('at') else ('never run' if q.get('run') else 'not built')
    extra = ''.join(f'<p class="hl note"><b>{k.capitalize()}:</b> {E(q[k])}</p>' for k in ('needs', 'next') if q.get(k))
    return (f'<div class="q" id="{E(q["id"])}"><div class="meta"><span class="pill {q["status"]}">{q["status"]}</span><code>{E(q["id"])}</code><span>{ran}{link}</span></div>'
            f'<h4>{E(q["question"])}</h4>' + (f'<p class="hl">{E(q["headline"])}</p>' if q.get('headline') else '') + extra +
            '<div class="meta">' + ''.join(f'<span class="trig" title="{E(T[t]["label"])}">{E(t)}</span>' for t in q.get('triggers', [])) + '</div></div>')


trig_cards = ''.join(
    f'<div class="card"><b>{E(v["label"])}</b><div class="when">{E(v["when"])} · <code>--trigger {E(k)}</code></div><ul>' +
    ''.join(f'<li><a href="#{E(q["id"])}">{E(q["id"])}</a>{"" if q.get("run") else " (to build)"}</li>' for q in Q if k in q.get('triggers', [])) + '</ul></div>'
    for k, v in T.items() if any(k in q.get('triggers', []) for q in Q))

body = f'''
<header class="band"><div class="wrap">
  <div class="tag"><b>EBA Dark</b><span>private working notes</span><span>index</span></div>
  <h1>The Question Book</h1>
  <p>Every question we have asked of the Atlas's data, what answers it, what we found, and which new data should make us ask it again.</p>
</div></header>
<main><div class="wrap">
<section>
  <div class="findings">
    <div class="finding"><div class="big up">{counts["done"]}</div><div class="lab">Answered</div><div class="sub">With code to re-run.</div></div>
    <div class="finding"><div class="big">{counts["next"]}</div><div class="lab">Next</div><div class="sub">{E(", ".join(q["id"] for q in Q if q["status"] == "next"))}</div></div>
    <div class="finding"><div class="big">{counts["planned"] + counts["idea"]}</div><div class="lab">Planned or ideas</div><div class="sub">Waiting on data or time.</div></div>
  </div>
  <p class="note" style="margin-top:12px">Re-run from the project root: <code>python3 tools/rerun_analyses.py --trigger results_2026 --pages</code>. Edit <code>analysis/questions.json</code> to add a question.</p>
</section>
<section><h2>When new data arrives</h2><div class="grid2">{trig_cards}</div></section>
''' + ''.join(f'<section><h2>{E(g)}</h2>' + ''.join(qhtml(q) for q in Q if q['group'] == g) + '</section>' for g in groups) + '</div></main>'
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
open(OUT, 'w').write('<title>The Question Book</title>\n' + head + body)
print(OUT)
