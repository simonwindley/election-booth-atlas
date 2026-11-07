#!/usr/bin/env python3
"""Refresh the Polls tab: fetch Wikipedia's "Opinion polling for the 2026 Victorian state election" page, turn its tables
into the grid capture that src/load_polls.py reads (raw/polls/wikipedia_vic2026_polls.json), rebuild
site/data/polls_vic2026.json, and optionally commit and push it. Standard library only; run from the project folder:

    python3 live/polls_update.py --publish

    --html FILE     parse a saved copy of the page instead of fetching it
    --publish       git add / commit / push the two JSON files afterwards
"""
import sys, os, re, json, argparse, datetime as dt, urllib.request
from html.parser import HTMLParser

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
PAGE = 'Opinion_polling_for_the_2026_Victorian_state_election'
URL = f'https://en.wikipedia.org/wiki/{PAGE}'
UA = 'ElectionBoothAtlas/1.0 (https://github.com/simonwindley/election-booth-atlas; polls refresh)'


class WikiTables(HTMLParser):
    """Walks the article: tracks the current h2/h3/h4 headings and expands each wikitable into a grid of cell texts,
    with '^' for a cell covered by a rowspan from above and '<' for one covered by a colspan from the left (the same
    convention as the in-browser capture)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heads = {2: None, 3: None, 4: None}
        self.tables, self.depth = [], 0
        self.in_head, self.head_text = None, ''
        self.skip = 0            # inside <style>, <script> or a reference superscript
        self.cur = None          # table being built: {'sec', 'rows': [...]}
        self.row, self.cell = None, None
        self.last_mod = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get('class', '') or ''
        if tag in ('style', 'script') or (tag == 'sup' and 'reference' in cls):
            self.skip += 1; return
        if self.skip:
            return
        if tag in ('h2', 'h3', 'h4'):
            self.in_head, self.head_text = int(tag[1]), ''
        elif tag == 'table' and 'wikitable' in cls and self.cur is None:
            self.cur = {'sec': [h for h in (self.heads[2], self.heads[3], self.heads[4]) if h], 'rows': []}
        elif self.cur is not None:
            if tag == 'tr':
                self.row = []
            elif tag in ('td', 'th') and self.row is not None:
                self.cell = {'rs': int(a.get('rowspan') or 1), 'cs': int(a.get('colspan') or 1), 'text': ''}
            elif tag == 'br' and self.cell is not None:
                self.cell['text'] += ' '
        elif tag == 'li' and a.get('id') == 'footer-info-lastmod':
            self.in_head = 'lastmod'; self.head_text = ''

    def handle_endtag(self, tag):
        if tag in ('style', 'script', 'sup') and self.skip:
            if tag != 'sup' or self.skip:
                self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ('h2', 'h3', 'h4') and self.in_head == int(tag[1]):
            lvl = self.in_head; t = re.sub(r'\[edit\]', '', self.head_text).strip()
            self.heads[lvl] = t
            for l in (3, 4):
                if l > lvl:
                    self.heads[l] = None
            self.in_head = None
        elif tag == 'li' and self.in_head == 'lastmod':
            self.last_mod = self.head_text.strip(); self.in_head = None
        elif self.cur is not None:
            if tag in ('td', 'th') and self.cell is not None:
                self.row.append(self.cell); self.cell = None
            elif tag == 'tr' and self.row is not None:
                self.cur['rows'].append(self.row); self.row = None
            elif tag == 'table':
                self.tables.append(self.cur); self.cur = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_head is not None:
            self.head_text += data
        elif self.cell is not None:
            self.cell['text'] += data


def expand(rows):
    """Row/colspan expansion into a rectangular grid."""
    g = []
    for ri, cells in enumerate(rows):
        while len(g) <= ri:
            g.append([])
        ci = 0
        for c in cells:
            while ci < len(g[ri]) and g[ri][ci] is not None:
                ci += 1
            for i in range(c['rs']):
                while len(g) <= ri + i:
                    g.append([])
                r = g[ri + i]
                for j in range(c['cs']):
                    while len(r) <= ci + j:
                        r.append(None)
                    r[ci + j] = re.sub(r'\s+', ' ', c['text']).strip() if (i == 0 and j == 0) else ('^' if j == 0 else '<')
            ci += c['cs']
    return [[c if c is not None else '' for c in r] for r in g]


def capture(html):
    p = WikiTables(); p.feed(html)
    return {'meta': {'retrieved': dt.datetime.now(dt.timezone.utc).isoformat(), 'last_edited': p.last_mod, 'url': URL},
            'tables': [{'sec': t['sec'], 'grid': expand(t['rows'])} for t in p.tables]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', help='parse this saved page instead of fetching')
    ap.add_argument('--publish', action='store_true')
    args = ap.parse_args()
    if args.html:
        html = open(args.html, encoding='utf-8').read()
    else:
        req = urllib.request.Request(URL, headers={'User-Agent': UA})
        html = urllib.request.urlopen(req, timeout=60).read().decode('utf-8')
    cap = capture(html)
    raw = os.path.join(ROOT, 'raw', 'polls', 'wikipedia_vic2026_polls.json')
    os.makedirs(os.path.dirname(raw), exist_ok=True)
    json.dump(cap, open(raw, 'w'), indent=0)
    print(f'{len(cap["tables"])} tables captured; page {cap["meta"]["last_edited"] or "(last-edited unknown)"}')
    from src import load_polls
    fw = os.path.join(ROOT, 'raw', 'polls', 'freshwater')
    if os.path.isdir(fw):   # issue questions: drop each new Herald Sun / Freshwater data-table .xlsx into raw/polls/freshwater/
        try:
            from src import load_issue_polls   # needs openpyxl; without it the existing raw/polls/issues_vic2026.json is reused
            load_issue_polls.main(fw, os.path.join(ROOT, 'raw', 'polls', 'issues_vic2026.json'))
        except ImportError as e:
            print(f'issue tables not re-read ({e}); using the existing raw/polls/issues_vic2026.json. To refresh: pip3 install openpyxl')
    out = os.path.join(ROOT, 'site', 'data', 'polls_vic2026.json')
    load_polls.main(raw, out)
    if os.path.exists(os.path.join(ROOT, 'raw', 'abs', 'sa1_census_2021.json')):   # re-model each seat's and booth's likely priorities from the new waves
        from src import model_issues
        model_issues.main()
        if os.path.exists(os.path.join(ROOT, 'raw', 'mood', 'mckinnon_2026.json')):
            try:
                from src import model_mood   # needs numpy; the mood columns already in the files are kept if it is missing
                model_mood.main()
            except ImportError as e:
                print(f'democratic mood not re-modelled ({e}); existing figures kept. To refresh: pip3 install numpy')
    if args.publish:
        import subprocess
        cmd = ('git add raw/polls/wikipedia_vic2026_polls.json raw/polls/issues_vic2026.json raw/polls/freshwater site/data/polls_vic2026.json site/data/demog_vic_la_2022.json.gz site/data/demog_booth_vic2022.json.gz && '
               '(git diff --cached --quiet || (git commit -q -m "polls update %s" && git push -q))' % dt.date.today().isoformat())
        r = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=180)
        print('published' if r.returncode == 0 else f'publish failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}')


if __name__ == '__main__':
    main()
