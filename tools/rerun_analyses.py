"""Re-run the Atlas's analyses from the question registry (analysis/questions.json).

  python3 tools/rerun_analyses.py                      list every question, its status and when it last ran
  python3 tools/rerun_analyses.py --due                list the questions whose inputs changed since they last ran
  python3 tools/rerun_analyses.py --trigger results_2026   re-run everything a new data event touches
  python3 tools/rerun_analyses.py --id seat_loss       re-run one question (and, with --deps, what it depends on)
  python3 tools/rerun_analyses.py --all                re-run every done question
  add --dry-run to print the commands without running them, --pages to rebuild the EBA Dark pages afterwards

Commands run from the project root in dependency order, each once even when several questions share it. Each run is
logged in analysis/runs.json (time, commands, exit codes), so the registry itself only changes when we edit it, and the
key numbers of each question that ran are added to analysis/vitals_history.json (see tools/findings_report.py).
"""
import os, sys, json, subprocess, datetime as dt, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'analysis/questions.json')
LOG = os.path.join(ROOT, 'analysis/runs.json')


def load():
    reg = json.load(open(REG))
    runs = json.load(open(LOG)) if os.path.exists(LOG) else {}
    return reg, runs


def order(qs, ids):
    """ids plus nothing else, sorted so that dependencies come first"""
    by = {q['id']: q for q in qs}; out, seen = [], set()

    def visit(i):
        if i in seen or i not in by:
            return
        seen.add(i)
        for d in by[i].get('depends_on', []):
            if d in ids:
                visit(d)
        out.append(i)
    for i in ids:
        visit(i)
    return out


def with_deps(qs, ids):
    by = {q['id']: q for q in qs}; todo, got = list(ids), set()
    while todo:
        i = todo.pop()
        if i in got or i not in by:
            continue
        got.add(i); todo += by[i].get('depends_on', [])
    return got


def mtime(p):
    p = os.path.join(ROOT, p)
    return os.path.getmtime(p) if os.path.exists(p) else None


def due(q, runs):
    last = runs.get(q['id'], {}).get('at')
    if not q.get('run'):
        return False
    if not last:
        return True
    t = dt.datetime.fromisoformat(last).timestamp()
    return any((mtime(p) or 0) > t for p in q.get('inputs', []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--trigger'); ap.add_argument('--id', action='append'); ap.add_argument('--all', action='store_true')
    ap.add_argument('--due', action='store_true'); ap.add_argument('--deps', action='store_true')
    ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--pages', action='store_true')
    a = ap.parse_args()
    reg, runs = load(); qs = reg['questions']; by = {q['id']: q for q in qs}
    if a.trigger and a.trigger not in reg['triggers']:
        sys.exit(f"unknown trigger {a.trigger!r}; known: {', '.join(reg['triggers'])}")
    if a.trigger:
        ids = {q['id'] for q in qs if a.trigger in q.get('triggers', []) and q.get('run')}
        ids |= {q['id'] for q in qs if q.get('run') and set(q.get('depends_on', [])) & ids}      # and what depends on those
    elif a.id:
        bad = [i for i in a.id if i not in by]
        if bad:
            sys.exit(f"unknown id(s): {', '.join(bad)}")
        ids = with_deps(qs, a.id) if a.deps else set(a.id)
    elif a.all:
        ids = {q['id'] for q in qs if q.get('run') and q['status'] == 'done'}
    else:
        show = [q for q in qs if due(q, runs)] if a.due else qs
        w = max(len(q['id']) for q in qs)
        for q in show:
            r = runs.get(q['id'], {})
            print(f"{q['id']:<{w}}  {q['status']:<8} {('ran ' + r['at'][:16]) if r.get('at') else 'never run':<20} {' '.join(q.get('triggers', []))}")
        if not a.due:
            print('\ntriggers:\n' + '\n'.join(f"  {k:<20} {v['label']} ({v['when']})" for k, v in reg['triggers'].items()))
        return
    seq = order(qs, ids)
    cmds = []
    for i in seq:
        for cmd in by[i].get('run', []):
            if cmd not in cmds:
                cmds.append(cmd)
    print('questions: ' + ', '.join(seq)); print('commands:\n  ' + '\n  '.join(cmds))
    if a.dry_run:
        return
    codes = {}
    for cmd in cmds:
        print(f'\n$ {cmd}', flush=True)
        codes[cmd] = subprocess.call(cmd, shell=True, cwd=ROOT)
        if codes[cmd]:
            print(f'!! exit {codes[cmd]}: stopping'); break
    now = dt.datetime.now().isoformat(timespec='seconds')
    for i in by:                                     # every question whose commands all just ran cleanly, not only those asked for
        mine = by[i].get('run', [])
        if mine and all(codes.get(c) == 0 for c in mine):
            runs[i] = {'at': now, 'commands': mine, 'trigger': a.trigger}
    json.dump(runs, open(LOG, 'w'), indent=1)
    # record the key numbers of what just ran, so tools/findings_report.py can say what held and what faded
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import findings_report
        ok = [i for i in seq if by[i].get('run') and all(codes.get(c) == 0 for c in by[i]['run'])]
        v = findings_report.snapshot(a.trigger or 'rerun: ' + ', '.join(ok), ok)
        if v: print(f"vitals recorded for {len(v)} question(s); report: python3 tools/findings_report.py")
    except Exception as e:
        print(f'(vitals not recorded: {e})')
    if a.pages:
        build_pages(qs, seq)


def build_pages(qs, seq=None):
    os.makedirs(os.path.join(ROOT, 'analysis/dark'), exist_ok=True)
    for q in qs:
        p = q.get('page')
        if p and p.get('builder') and (seq is None or q['id'] in seq) and os.path.exists(os.path.join(ROOT, p['builder'])):
            subprocess.call(['python3', p['builder'], p['data'], p['html']], cwd=ROOT)
    subprocess.call(['python3', 'tools/dark/build_index_page.py'], cwd=ROOT)
    print('EBA Dark pages in analysis/dark/ (private: not committed). Republish them as artifacts from a Claude session.')


if __name__ == '__main__':
    main()
