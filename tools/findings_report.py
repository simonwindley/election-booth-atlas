"""What held, what faded: track each analysis's key numbers ("vitals") across re-runs and data expansions.

Each question in analysis/questions.json can list vitals: the handful of numbers its headline rests on, read from its output
JSON by a dotted path (list items by index), with an optional scope (state / federal / urban / regional / a jurisdiction...)
so the same effect can be compared across places:
    "vitals": [{"label": "Sophomore surge (pts)", "file": "data/analysis/seat_swing_deviation.json",
                "path": "core_state.coef.sophomore.0", "lo": "core_state.coef.sophomore.1", "hi": "core_state.coef.sophomore.2",
                "scope": "Victoria, state"}]
Snapshots go to analysis/vitals_history.json (one entry per run: when, why, values). The report compares the latest snapshot
with the previous one and with the first, and sorts every vital into:
  held          same sign, and moved less than a third of its size (or stayed inside its earlier interval)
  strengthened  same sign, at least a third bigger
  faded         same sign, at least a third smaller, or its interval now includes zero
  flipped       changed sign
  still negligible  both values below the vital's 'negligible' size (set it for effects that hover around zero)
and lists questions that have no vitals yet.

usage: python3 tools/findings_report.py --snapshot "why"   record the current values (tools/rerun_analyses.py does this after each run)
       python3 tools/findings_report.py                    print the report and write analysis/findings_report.md
"""
import os, sys, json, argparse, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'analysis/questions.json')
HIST = os.path.join(ROOT, 'analysis/vitals_history.json')
OUT = os.path.join(ROOT, 'analysis/findings_report.md')


def dig(d, path):
    for p in path.split('.'):
        if d is None: return None
        d = d[int(p)] if isinstance(d, list) else d.get(p)
    return d


def read_vitals(q):
    out = {}
    for v in q.get('vitals', []):
        f = os.path.join(ROOT, v['file'])
        if not os.path.exists(f): continue
        d = json.load(open(f))
        key = v['label'] + (f" [{v['scope']}]" if v.get('scope') else '')
        val = dig(d, v['path'])
        if isinstance(val, (int, float)):
            out[key] = {'value': val, 'lo': dig(d, v['lo']) if v.get('lo') else None, 'hi': dig(d, v['hi']) if v.get('hi') else None, 'negligible': v.get('negligible', 0)}
    return out


def snapshot(why, ids=None):
    reg = json.load(open(REG)); hist = json.load(open(HIST)) if os.path.exists(HIST) else []
    vals = {q['id']: read_vitals(q) for q in reg['questions'] if q.get('vitals') and (not ids or q['id'] in ids)}
    vals = {k: v for k, v in vals.items() if v}
    if vals:
        hist.append({'at': dt.datetime.now().isoformat(timespec='seconds'), 'why': why, 'values': vals})
        json.dump(hist, open(HIST, 'w'), indent=1)
    return vals


def classify(old, new, negligible=0):
    a, b = old['value'], new['value']
    if abs(a) < negligible and abs(b) < negligible: return 'still negligible'
    if a == 0 or b == 0: return 'held' if a == b else ('faded' if b == 0 else 'strengthened')
    if (a > 0) != (b > 0): return 'flipped'
    if new.get('lo') is not None and new.get('hi') is not None and new['lo'] <= 0 <= new['hi'] and not (old.get('lo') is not None and old['lo'] <= 0 <= old['hi']):
        return 'faded'
    r = abs(b) / abs(a)
    if r >= 4 / 3: return 'strengthened'
    if r <= 2 / 3: return 'faded'
    return 'held'


def report():
    reg = json.load(open(REG)); hist = json.load(open(HIST)) if os.path.exists(HIST) else []
    lines = ['# What held, what faded', '', f'Generated {dt.datetime.now():%Y-%m-%d %H:%M}. {len(hist)} snapshot(s) on record.', '']
    by = {q['id']: q for q in reg['questions']}
    latest = {}
    for h in hist:
        for qid, vals in h['values'].items():
            for k, v in vals.items(): latest.setdefault((qid, k), []).append((h['at'][:10], h['why'], v))
    for qid in [q['id'] for q in reg['questions'] if q.get('vitals')]:
        rows = [(k, s) for (q, k), s in latest.items() if q == qid]
        if not rows: continue
        lines += [f"## {qid}", '', by[qid]['question'], '', '| Vital | First | Previous | Latest | Since previous | Since first |', '|---|---|---|---|---|---|']
        for k, s in sorted(rows):
            f = lambda v: f"{v['value']:.3g}" + (f" [{v['lo']:.3g}, {v['hi']:.3g}]" if v.get('lo') is not None and v.get('hi') is not None else '')
            first, prev, last = s[0][2], (s[-2][2] if len(s) > 1 else None), s[-1][2]
            lines.append(f"| {k} | {f(first)} | {f(prev) if prev else '–'} | {f(last)} | {classify(prev, last, last.get('negligible', 0)) if prev else 'baseline'} | {classify(first, last, last.get('negligible', 0)) if len(s) > 1 else 'baseline'} |")
        lines.append('')
    missing = [q['id'] for q in reg['questions'] if q.get('run') and not q.get('vitals')]
    lines += ['## Not tracked yet', '', 'Questions that run but have no vitals listed: ' + (', '.join(missing) or 'none') + '.', '']
    open(OUT, 'w').write('\n'.join(lines)); print('\n'.join(lines))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--snapshot'); ap.add_argument('--id', action='append')
    a = ap.parse_args()
    if a.snapshot is not None:
        v = snapshot(a.snapshot, a.id); print(f'snapshot: {sum(len(x) for x in v.values())} vitals from {len(v)} questions')
    else:
        report()
