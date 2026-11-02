"""Issue-priority polling for Victoria 2026, from the Herald Sun / Freshwater Strategy monthly data tables
(raw/polls/freshwater/*.xlsx, published at freshwaterstrategy.com). Each workbook has one sheet of tables, each
introduced by a "Back to TOC" row, then a title row, a header row ("Column %" / "Row %" / "Average" followed by the
crossbreak names), data rows, and "Unweighted n" / "Weighted n" rows.

Kept, for every wave:
  priority   "Which of the following would you like the Victorian State Government to prioritise? Pick up to three"
  most       "...and which is MOST important?"
  manage     "who is best to manage the following issues" (Labor / neither-unsure / Coalition, row %)
  manage_net the Labor-minus-Coalition net for each issue, by crossbreak
  vote_issue, vote_most  (Sept 2026 on) "which issues are most likely to influence who you will vote for" + MOST

Writes raw/polls/issues_vic2026.json; src.load_polls merges it into site/data/polls_vic2026.json as `issues`.
Usage: python3 -m src.load_issue_polls [dir] [out]
"""
import sys, os, re, glob, json
import openpyxl

MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'])}
DROP = {'Other', 'Unsure', 'Nothing', 'None of these', 'None', 'Neither / Unsure'}


def fieldwork(wb):
    for ws in wb.worksheets:
        if ws.title.strip() != 'Methodology':
            continue
        for r in ws.iter_rows(values_only=True):
            t = ' '.join(str(x) for x in r if x is not None)
            m = re.search(r'Fieldwork dates:\s*(.+)', t)
            if m:
                s = m.group(1).strip()
                yr = re.search(r'(20\d\d)', s).group(1)
                days = re.findall(r'(\d{1,2})\s*([A-Za-z]+)?', s.replace(yr, ''))
                # "31 July - 3 August 2026", "5-8 June 2026", "24 - 28 September 2026"
                mons = [d[1].lower() for d in days if d[1]]
                end_mon = MONTHS[mons[-1]]
                start_mon = MONTHS[mons[0]] if len(mons) > 1 else end_mon
                d0, d1 = int(days[0][0]), int(days[-1][0])
                n = None
                return s, f'{yr}-{start_mon:02d}-{d0:02d}', f'{yr}-{end_mon:02d}-{d1:02d}'
    return None, None, None


def sample(wb):
    for ws in wb.worksheets:
        if ws.title.strip() == 'Methodology':
            for r in ws.iter_rows(values_only=True):
                t = ' '.join(str(x) for x in r if x is not None)
                m = re.search(r'Sample:\s*([\d,]+)', t)
                if m:
                    return int(m.group(1).replace(',', ''))


def tables(ws):
    rows = list(ws.iter_rows(values_only=True))
    out, i = [], 0
    while i < len(rows):
        if rows[i] and rows[i][0] == 'Back to TOC' and i + 2 < len(rows) and isinstance(rows[i + 1][0], str):
            title = re.sub(r'\s+', ' ', rows[i + 1][0]).strip()
            hdr = rows[i + 2]
            if hdr and hdr[0] in ('Column %', 'Row %', 'Average'):
                cols = [str(c).strip() if c is not None else None for c in hdr[1:]]
                ncol = max(k for k, c in enumerate(cols) if c) + 1
                cols = cols[:ncol]
                data, n = [], None
                j = i + 3
                while j < len(rows) and rows[j] and rows[j][0] is not None and not str(rows[j][0]).startswith('Weight'):
                    lab = str(rows[j][0]).strip()
                    vals = list(rows[j][1:1 + ncol])
                    if lab == 'Unweighted n':
                        n = vals
                    elif lab != 'Weighted n':
                        data.append((lab, vals))
                    j += 1
                out.append({'title': title, 'kind': hdr[0], 'cols': cols, 'rows': data, 'n': n})
                i = j
                continue
        i += 1
    return out


def num(v, scale):
    return None if v is None or isinstance(v, str) else round(v * scale, 1)


def main(d='raw/polls/freshwater', out='raw/polls/issues_vic2026.json'):
    waves, crossbreaks = [], None
    for f in sorted(glob.glob(os.path.join(d, '*.xlsx'))):
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = max(wb.worksheets, key=lambda w: w.max_row or 0)
        text, start, end = fieldwork(wb)
        w = {'firm': 'Freshwater Strategy', 'client': 'Herald Sun', 'fieldwork': text, 'start': start, 'date': end, 'n': sample(wb),
             'file': os.path.basename(f), 'url': 'https://freshwaterstrategy.com/'}
        prev = None
        for t in tables(ws):
            low = t['title'].lower()
            key = None
            if 'like the victorian state government to prioritise' in low:
                key = 'priority'
            elif low.startswith('…and which is most important') or low.startswith('...and which is most important'):
                key = {'priority': 'most', 'vote_issue': 'vote_most'}.get(prev)
            elif low.startswith('in your view, who is best to manage'):
                key = 'manage'
            elif low.startswith('net: in your view, who is best to manage'):
                key = 'manage_net'
            elif 'most likely to influence who you will' in low:
                key = 'vote_issue'
            if key in ('priority', 'vote_issue'):
                prev = key
            elif key is None:
                prev = None if not low.startswith('…and') else prev
            if not key or key in w:
                continue
            if key == 'manage':
                # row % with columns Labor-best / Neither / Coalition-best
                ci = {c: k for k, c in enumerate(t['cols']) if c}
                lab = next(k for c, k in ci.items() if 'Labor' in c); coa = next(k for c, k in ci.items() if 'Liberal' in c)
                nei = next(k for c, k in ci.items() if 'Neither' in c)
                w['manage'] = {'labor_label': t['cols'][lab], 'coalition_label': t['cols'][coa],
                               'rows': [{'issue': r, 'labor': num(v[lab], 100), 'neither': num(v[nei], 100), 'coalition': num(v[coa], 100)} for r, v in t['rows']]}
                continue
            crossbreaks = crossbreaks or t['cols']
            scale = 1 if key == 'manage_net' else 100
            w[key] = {'title': t['title'], 'cols': t['cols'], 'n': [x if isinstance(x, (int, float)) else None for x in (t['n'] or [])],
                      'rows': [{'issue': r, 'v': [num(x, scale) for x in v]} for r, v in t['rows'] if r not in DROP or key != 'manage_net']}
        waves.append(w)
        print(w['date'], w['n'], [k for k in ('priority', 'most', 'manage', 'manage_net', 'vote_issue', 'vote_most') if k in w])
    waves.sort(key=lambda w: w['date'] or '')
    obj = {'source': 'Herald Sun / Freshwater Strategy monthly Victorian poll, published data tables (online panel, ~1,000 Victorian voters a wave, weighted to age, sex, education, 2022 state and 2025 federal vote, location)',
           'groups': [{'label': 'Gender', 'cols': ['Female', 'Male']}, {'label': 'Age', 'cols': ['18-34', '35-54', '55+']},
                      {'label': 'Household income', 'cols': ['HHI less than $75k', 'HHI $75k-$150k', 'HHI over $150k']},
                      {'label': 'Education', 'cols': ['Degree educated', 'No degree']},
                      {'label': 'Housing', 'cols': ['Homeowner (with mortgage)', 'Homeowner (without mortgage)', 'Renting', 'Living with parents']},
                      {'label': 'Children', 'cols': ['Children at home', 'No children at home']},
                      {'label': 'State vote', 'cols': ['Labor Party', 'Liberals & Nationals', 'One Nation', 'The Greens', 'Other']}],
           'waves': waves}
    json.dump(obj, open(out, 'w'), indent=1)
    print(len(waves), 'waves ->', out)
    return obj


if __name__ == '__main__':
    main(*sys.argv[1:3])
