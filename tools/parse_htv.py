"""Read the preference order off registered how-to-vote cards (PDFs).

    python3 tools/parse_htv.py vic2022 raw/htv/register_2022.json raw/htv/2022 raw/htv/cards_vic2022.json
    python3 tools/parse_htv.py vic2026 site/data/live/daily.json raw/htv/2026 raw/htv/cards_vic2026.json

For every card the register lists, and every district the card covers, the script finds each candidate's
surname on the page and the number printed beside it. The PDF text layer is tried first; pages whose numbers
(or names) are only in the artwork are rendered and read with tesseract. A card is 'complete' when every
candidate in the district got a distinct number. Re-runs skip cards already parsed (unless --redo).

Needs: pdfplumber, pypdfium2, pytesseract (+ the tesseract binary). Runs on the Mac / its VM.
"""
import sys, os, re, json, gzip, difflib, argparse
from collections import defaultdict, Counter

import pdfplumber

NUM_RE = re.compile(r'^[^\dA-Za-z]{0,2}(\d{1,2})[\.\)]?$')   # allows a box glyph stuck to the digit, e.g. '□1'


def norm(s):
    return re.sub(r'[^A-Z]', '', (s or '').upper().replace('Ø', 'O').replace('É', 'E'))


def load_candidates(election_id, path='site/data/candidates.json.gz'):
    c = json.load(gzip.open(path, 'rt'))
    rows = [dict(zip(c['cols'], r)) for r in c['rows'] if r[0] == election_id]
    by_contest = defaultdict(list)
    for r in rows:
        by_contest[r['contest_id']].append(r)
    return by_contest


def load_register(path):
    j = json.load(open(path))
    cards = j['cards'] if 'cards' in j else (j.get('htv') or {}).get('cards', [])
    return cards


# ----------------------------------------------------------------------------- word extraction

def words_text(page):
    """Words from the PDF text layer as (text, x0, x1, top, bottom)."""
    out = []
    try:
        ws = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5, y_tolerance=2)
    except Exception:
        return out
    for w in ws:
        out.append((w['text'], w['x0'], w['x1'], w['top'], w['bottom']))
    return out


_pdfium = None


def words_ocr(pdf_path, page_index, scale=2.5, psm=11):
    """Words from tesseract on a rendered page, in PDF points. psm 11 (sparse text) first; psm 4 (columns) as a second pass
    for artwork cards where the sparse pass misses names."""
    global _pdfium
    import pypdfium2 as pdfium
    import pytesseract
    doc = pdfium.PdfDocument(pdf_path)
    page = doc[page_index]
    img = page.render(scale=scale).to_pil().convert('L')
    ws = []
    d = pytesseract.image_to_data(img, config=f'--psm {psm}', output_type=pytesseract.Output.DICT)
    for i, t in enumerate(d['text']):
        t = (t or '').strip()
        if not t or int(d['conf'][i]) < 0:
            continue
        x, y, w, h = d['left'][i], d['top'][i], d['width'][i], d['height'][i]
        ws.append((t, x / scale, (x + w) / scale, y / scale, (y + h) / scale))
    return ws


def _longest_run(seq):
    best = run = 0
    for v in seq:
        run = run + 1 if v else 0
        if run > best:
            best = run
    return best


def box_interior(img, scale, x0, top, bot, width=75):
    """The drawn number box left of a name: two vertical border lines a square-ish distance apart with horizontal borders
    between them, overlapping the name's line. Returns the interior as an image (white border added), or None."""
    from PIL import ImageOps
    h = (bot - top) * scale
    X0 = int(max(0, x0 - width) * scale); Y0 = int(max(0, top - 2.0 * (bot - top)) * scale)
    cr = img.crop((X0, Y0, int((x0 - 1) * scale), int((bot + 2.0 * (bot - top)) * scale)))
    bw = ImageOps.autocontrast(cr).point(lambda v: 255 if v > 150 else 0)
    px = bw.load(); W, H = bw.size
    if W < 8 or H < 8:
        return None
    name_c = (top - Y0 / scale + (bot - top) / 2) * scale    # the name's vertical centre within the crop
    vcols = [x for x in range(W) if _longest_run([px[x, y] == 0 for y in range(H)]) >= 1.0 * h]
    groups = []
    for x in vcols:
        if groups and x - groups[-1][-1] <= 2:
            groups[-1].append(x)
        else:
            groups.append([x])
    lines = [(g[0], g[-1]) for g in groups]
    best = None
    for i in range(len(lines) - 1, 0, -1):
        for k in range(i - 1, -1, -1):
            L, R = lines[k], lines[i]; wbox = R[0] - L[1]
            if wbox > 4 * h:
                break
            if wbox < 0.6 * h:
                continue
            xa, xb = L[1] + 2, R[0] - 2
            hrows = [y for y in range(H) if _longest_run([px[x, y] == 0 for x in range(xa, xb)]) >= 0.8 * (xb - xa)]
            hg = []
            for y in hrows:
                if hg and y - hg[-1][-1] <= 2:
                    hg[-1].append(y)
                else:
                    hg.append([y])
            hl = [(g[0], g[-1]) for g in hg]
            for j in range(len(hl) - 1):
                hh = hl[j + 1][0] - hl[j][1]
                if 0.6 * h <= hh <= 4 * h and 0.7 <= wbox / hh <= 1.6:
                    ya, yb = hl[j][1] + 2, hl[j + 1][0] - 2
                    if not (ya - 0.5 * h <= name_c <= yb + 0.5 * h):
                        continue      # a neighbouring row's box
                    cand = (xa, ya, xb, yb); area = (xb - xa) * (yb - ya)
                    if best is None or area > best[1]:
                        best = (cand, area)
    if not best:
        return None
    return ImageOps.expand(bw.crop(best[0]), border=14, fill=255)


def digits_by_crop(pdf_path, page_index, hits, n_cands, scale=4):
    """Last resort for cards whose numbers are drawn in boxes the page OCR skips. For each name, find the drawn box beside
    it and read its interior as a single character (weight 3); failing a box, read a few plain crops of the strip left of
    the name (weight 1 each). The majority of valid readings wins; the permutation check downstream catches the rest."""
    import pypdfium2 as pdfium
    import pytesseract
    from PIL import ImageOps
    doc = pdfium.PdfDocument(pdf_path)
    img = doc[page_index].render(scale=scale).to_pil().convert('L')
    out = {}

    def read(im, psms):
        vals = []
        for psm in psms:
            try:
                t = pytesseract.image_to_string(im, config=f'--psm {psm} -c tessedit_char_whitelist=0123456789').strip()
            except Exception:
                continue
            t = re.sub(r'\D', '', t)
            if t and 1 <= int(t) <= n_cands:
                vals.append(int(t))
        return vals

    for cid, boxes in hits.items():
        votes = Counter()
        for b in boxes[:2]:
            x0, x1, top, bot = b[:4]
            h = max(bot - top, 6)
            inner = box_interior(img, scale, x0, top, bot)
            if inner is not None:
                for v in read(inner, (10, 7)):
                    votes[v] += 3
            if not votes:
                for width in (22, 32, 42):
                    c = img.crop((int(max(0, x0 - width) * scale), int(max(0, top - 0.9 * h) * scale), int((x0 - 1) * scale), int((bot + 0.9 * h) * scale)))
                    c = ImageOps.expand(ImageOps.autocontrast(c), border=10, fill=255)
                    for v in read(c, (10, 7)):
                        votes[v] += 1
        if votes:
            n, v = votes.most_common(1)[0]
            if v >= 2:
                out[cid] = n
    return out


# ----------------------------------------------------------------------------- matching

def find_names(words, cands):
    """For each candidate, the boxes where the surname appears. Handles multi-word surnames and OCR noise."""
    toks = [(norm(t), x0, x1, top, bot) for (t, x0, x1, top, bot) in words]
    toks = [t for t in toks if t[0]]
    hits = defaultdict(list)
    dup = {k for k, v in Counter(norm(c['surname']) for c in cands).items() if v > 1}
    for c in cands:
        target = norm(c['surname'])
        if not target:
            continue
        given = norm((c.get('given_name') or '').split(' ')[0])[:4] if target in dup else None
        nwords = max(1, len(c['surname'].split()))
        for i in range(len(toks)):
            for span in range(1, min(3, nwords + 1) + 1):
                if i + span > len(toks):
                    break
                seq = toks[i:i + span]
                # tokens must sit on one line
                if max(t[3] for t in seq) - min(t[3] for t in seq) > 6:
                    break
                joined = ''.join(t[0] for t in seq)
                if len(joined) > len(target) + 2:
                    break
                ok = joined == target or (len(target) >= 5 and difflib.SequenceMatcher(None, joined, target).ratio() >= 0.86)
                if ok and given:   # two candidates share this surname: the given name must follow on the same line
                    nxt = [t for t in toks[i + span:i + span + 2] if abs(t[3] - seq[0][3]) <= 6]
                    ok = any(t[0].startswith(given[:3]) or t[0] == given[:1] for t in nxt)   # 'Nat' or the initial 'N'
                if ok:
                    x0 = min(t[1] for t in seq); x1 = max(t[2] for t in seq)
                    top = min(t[3] for t in seq); bot = max(t[4] for t in seq)
                    hits[c['candidate_id']].append((x0, x1, top, bot, joined == target))
                    break
    return hits


def find_numbers(words):
    out = []
    for (t, x0, x1, top, bot) in words:
        m = NUM_RE.match(t)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 30:
                out.append((n, x0, x1, top, bot))
    return out


def nearest_number(box, nums, n_cands):
    """The number printed beside a name box: prefer left of the name on the same line."""
    x0, x1, top, bot, _ = box
    h = max(bot - top, 6)
    cy = (top + bot) / 2
    best = None
    for (n, nx0, nx1, ntop, nbot) in nums:
        if n > n_cands:
            continue
        ncy = (ntop + nbot) / 2
        nh = nbot - ntop
        # vertical: the number's box must overlap the name line, allowing big digits spanning two lines
        if not (ntop - 0.6 * h <= cy <= nbot + 0.6 * h or top - 0.3 * nh <= ncy <= bot + 0.3 * nh):
            continue
        if nx1 <= x0 + 2:          # to the left
            dx = x0 - nx1
            if dx > 260:
                continue
            score = dx + abs(ncy - cy) * 2
        elif nx0 >= x1 - 2:        # to the right
            dx = nx0 - x1
            if dx > 90:
                continue
            score = dx + 120 + abs(ncy - cy) * 2
        else:
            continue
        if best is None or score < best[0]:
            best = (score, n)
    return best[1] if best else None


def cluster_hits(hits):
    """Keep, for each candidate, the name box that sits in the same column as the rest of the district's names.
    Combined cards print a dozen districts per page, so a common surname can match in another district's column."""
    all_hits = [(cid, b) for cid, bs in hits.items() for b in bs]
    if len(all_hits) < 2:
        return hits
    best = None
    for cid, b in all_hits:
        near = {c2 for c2, b2 in all_hits if abs(b2[0] - b[0]) < 30 and abs(b2[2] - b[2]) < 450}
        if best is None or len(near) > best[0]:
            best = (len(near), b)
    ax, ay = best[1][0], best[1][2]
    out = {}
    for cid, bs in hits.items():
        sel = [b for b in bs if abs(b[0] - ax) < 30 and abs(b[2] - ay) < 450]
        if not sel:   # e.g. a second column of names on the same card: take the box nearest the cluster
            sel = [min(bs, key=lambda b: (b[0] - ax) ** 2 + (b[2] - ay) ** 2)]
        out[cid] = sel
    return out


def assign(words, cands):
    hits = cluster_hits(find_names(words, cands))
    nums = find_numbers(words)
    votes = {c['candidate_id']: Counter() for c in cands}
    for cid, boxes in hits.items():
        for b in boxes:
            n = nearest_number(b, nums, len(cands))
            if n is not None:
                votes[cid][n] += 1
    numbers = {}
    for cid, cnt in votes.items():
        if cnt:
            numbers[cid] = cnt.most_common(1)[0][0]
    found = {cid for cid, b in hits.items() if b}
    return numbers, found


def complete(numbers, cands):
    if len(numbers) != len(cands):
        return False
    vals = sorted(numbers.values())
    return vals == list(range(1, len(cands) + 1))


def score(numbers, cands):
    distinct = len(set(numbers.values()))
    return (distinct, distinct - len(numbers))   # more distinct numbers first; collisions count against


def infer_missing(numbers, cands, owner=None):
    """One candidate missing and one number unused (usually the card-owner's own name set as artwork): fill it in.
    If the owner's name was found but shares its number with another candidate while 1 is unused, the owner is the 1."""
    n = len(cands)
    if owner and owner not in numbers and 1 not in numbers.values() and numbers:
        numbers = {**numbers, owner: 1}      # the card-owner's own name is set as artwork: they are the 1
    if owner and owner in numbers and 1 not in numbers.values():
        shared = [c for c, v in numbers.items() if v == numbers[owner] and c != owner]
        if shared:
            numbers = {**numbers, owner: 1}
            if len(numbers) == n and len(set(numbers.values())) == n:
                return numbers, True
    if len(numbers) == n - 1 and len(set(numbers.values())) == n - 1:
        missing_c = [c['candidate_id'] for c in cands if c['candidate_id'] not in numbers]
        missing_n = [k for k in range(1, n + 1) if k not in numbers.values()]
        if len(missing_c) == 1 and len(missing_n) == 1:
            return {**numbers, missing_c[0]: missing_n[0]}, True
    return numbers, False


# ----------------------------------------------------------------------------- per card

def parse_card(pdf_path, contests, by_contest, owners=None, ocr=True, max_pages=12):
    owners = owners or {}
    """Returns {contest_id: result} for every contest in `contests` the card appears to cover."""
    results = {}
    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as e:
        return {'_error': f'open: {e}'}
    pages = pdf.pages[:max_pages]
    page_words = [words_text(p) for p in pages]
    ocr_cache = {}

    def ocr_words(i, second=False):
        key = (i, 'b') if second else i
        if key not in ocr_cache:
            try:
                ocr_cache[key] = words_ocr(pdf_path, i, scale=3.0, psm=4) if second else words_ocr(pdf_path, i)
            except Exception as e:
                ocr_cache[key] = []
                ocr_cache.setdefault('_err', str(e))
        return ocr_cache[key]

    detected = []
    if len(contests) <= 2:
        # the register's district can be wrong (or missing): see which district's candidates the first pages name
        for i, words in enumerate(page_words[:2]):
            for k, cands in by_contest.items():
                if k in contests or k in detected:
                    continue
                nf = len({cid for cid, bs in find_names(words, cands).items() if bs})
                if nf >= max(3, int(0.6 * len(cands))):
                    detected.append(k)
    for contest_id in list(contests) + detected:
        cands = by_contest.get(contest_id)
        if not cands:
            continue
        best = None
        for i, words in enumerate(page_words):
            numbers, found = assign(words, cands)
            method = 'text'
            numbers, inferred = infer_missing(numbers, cands, owners.get(contest_id))
            if not complete(numbers, cands) and ocr:
                # only OCR pages that mention at least one candidate (or have no text at all)
                if found or len(words) < 8:
                    n2, f2 = assign(ocr_words(i), cands)
                    # also try the union: names from text, numbers from OCR
                    n3, f3 = assign(words + ocr_words(i), cands)
                    found = found | f2
                    for cand_numbers, m in ((n3, 'text+ocr'), (n2, 'ocr')):
                        cand_numbers, inf2 = infer_missing(cand_numbers, cands, owners.get(contest_id))
                        if score(cand_numbers, cands) > score(numbers, cands):
                            numbers, method, inferred = cand_numbers, m, inf2
            if not complete(numbers, cands) and ocr and found and len(found) < len(cands):
                # the sparse pass missed some names: a second OCR pass in column mode, merged in
                n4, f4 = assign(words + ocr_words(i) + ocr_words(i, True), cands)
                n4, inf4 = infer_missing(n4, cands, owners.get(contest_id))
                found = found | f4
                if score(n4, cands) > score(numbers, cands):
                    numbers, method, inferred = n4, 'text+ocr2', inf4
            if not complete(numbers, cands) and ocr and len(found) >= max(2, len(cands) // 2):
                # names are on the page but the numbers are not readable as text: read the box beside each name
                extra = ocr_words(i, True) if (i, 'b') in ocr_cache else []
                hits = cluster_hits(find_names(words + ocr_words(i) + extra, cands))
                crop_nums = digits_by_crop(pdf_path, i, hits, len(cands))
                crop_nums, inf3 = infer_missing(crop_nums, cands, owners.get(contest_id))
                if score(crop_nums, cands) > score(numbers, cands):
                    numbers, method, inferred = crop_nums, 'crop', inf3
            if not numbers:
                continue
            res = {'numbers': numbers, 'method': method + ('+inferred' if inferred else ''), 'page': i + 1,
                   'complete': complete(numbers, cands), 'found': sorted(found)}
            if best is None or score(numbers, cands) > score(best['numbers'], cands):
                best = res
            if best['complete']:
                break
        if best:
            nums = best['numbers']
            n = len(cands)
            if best['complete']:
                best['order'] = [cid for cid, n_ in sorted(nums.items(), key=lambda kv: kv[1])]
                best['status'] = 'complete'
            elif len(nums) == 1 and list(nums.values())[0] == 1 and len(best.get('found', ())) >= n - 1:
                best['status'] = 'vote1_only'      # the ballot is reproduced but only the 1 is filled in
            elif len(nums) == 1 and list(nums.values())[0] == 1:
                best['status'] = 'vote1_only?'     # only a '1' beside one name; rest of the ballot not found
            else:
                best['status'] = 'partial'
            best.pop('found', None)
            if contest_id in detected:
                best['detected'] = True
            results[contest_id] = best
    pdf.close()
    if '_err' in ocr_cache:
        results['_ocr_error'] = ocr_cache['_err']
    return results


PARTY_ALIASES = {
    'australian labor party - victorian branch': 'ALP', 'australian labor party': 'ALP', 'labor': 'ALP',
    'liberal party of australia - victorian division': 'LIB', 'liberal': 'LIB', 'liberal party': 'LIB',
    'the nationals': 'NAT', 'national party of australia - victoria': 'NAT', 'nationals': 'NAT',
    'australian greens - victoria': 'GRN', 'australian greens': 'GRN', 'the australian greens - victoria': 'GRN',
    'family first victoria': 'FFP', 'animal justice party': 'AJP', 'freedom party of victoria': 'FRP',
    'labour dlp': 'DLP', 'victorian socialists': 'VSP', 'liberal democrats': 'LDP', 'liberal democratic party': 'LDP',
    "derryn hinch's justice party": 'DHJ', 'new democrats': 'NDP', 'reason australia': 'RUA', 'reason': 'RUA',
    'shooters, fishers & farmers victoria': 'SFF', 'shooters, fishers and farmers party': 'SFF',
    "pauline hanson's one nation": 'ONP', 'one nation': 'ONP', 'angry victorians party': 'AVP',
    'legalise cannabis victoria': 'LCP', 'health australia party': 'HAP', 'transport matters party': 'TMP',
    'companions and pets party': 'CPP', 'sustainable australia party - universal basic income': 'SAP',
    'sustainable australia party': 'SAP', 'united australia party': 'UAP', 'victorian socialists ': 'VSP',
}


def owner_of(card, cands):
    """Which candidate (and party) the card belongs to."""
    reg = (card.get('registrant') or '').strip()
    if card.get('kind') == 'party':
        p = PARTY_ALIASES.get(reg.lower())
        if p is None:
            # try party_name match against the candidates
            for c in cands:
                if (c.get('party_name') or '').lower() == reg.lower():
                    p = c['party']; break
        if p:
            for c in cands:
                if c['party'] == p:
                    return c['candidate_id'], p
        return None, p
    # independent / candidate registrant: "SURNAME, Given"
    sur = norm(reg.split(',')[0])
    for c in cands:
        if norm(c['surname']) == sur:
            return c['candidate_id'], c['party']
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('election'); ap.add_argument('register'); ap.add_argument('pdf_dir'); ap.add_argument('out')
    ap.add_argument('--redo', action='store_true'); ap.add_argument('--no-ocr', action='store_true')
    ap.add_argument('--retry', action='store_true', help='re-parse cards that are not complete')
    ap.add_argument('--limit', type=int, default=0); ap.add_argument('--only', default='')
    ap.add_argument('--seconds', type=float, default=0, help='stop (and save) after this many seconds')
    ap.add_argument('--candidates', default='site/data/candidates.json.gz')
    a = ap.parse_args()
    by_contest = load_candidates(a.election, a.candidates)
    cards = load_register(a.register)
    out = json.load(open(a.out)) if os.path.exists(a.out) and not a.redo else {'election': a.election, 'cards': {}}
    done = out['cards']
    n = 0
    import time; t0 = time.time()
    only = set(a.only.split(',')) if a.only else None
    for card in cards:
        reg = str(card.get('registration') or '')
        if not reg or (only and reg not in only):
            continue
        path = os.path.join(a.pdf_dir, f'{reg}.pdf')
        if not os.path.exists(path):
            continue
        if reg in done and not a.redo and not only:
            if not (a.retry and (not done[reg]['contests'] or any(r.get('status') != 'complete' for r in done[reg]['contests'].values()))):
                continue
        contests = card.get('contest_ids') or []
        owners = {k: owner_of(card, by_contest[k])[0] for k in contests if k in by_contest}
        res = parse_card(path, contests, by_contest, owners, ocr=not a.no_ocr)
        entry = {'registrant': card.get('registrant'), 'kind': card.get('kind'), 'registered': card.get('registered'),
                 'areas': card.get('areas'), 'contests': {}}
        for cid_contest, r in res.items():
            if cid_contest.startswith('_'):
                entry[cid_contest[1:]] = r
                continue
            owner, party = owner_of(card, by_contest[cid_contest])
            r['owner'] = owner; r['party'] = party
            if owner and r.get('numbers', {}).get(owner) not in (None, 1):
                r['owner_not_first'] = True
            entry['contests'][cid_contest] = r
        done[reg] = entry
        n += 1
        st = Counter(r.get('status') for r in entry['contests'].values())
        print(f'{reg:>5} {card.get("registrant","")[:34]:34} {len(entry["contests"])} contest(s): ' + ', '.join(f'{k} {v}' for k, v in st.most_common()))
        if n % 10 == 0:
            json.dump(out, open(a.out, 'w'), indent=0)
        if a.limit and n >= a.limit:
            break
        if a.seconds and time.time() - t0 > a.seconds:
            break
    json.dump(out, open(a.out, 'w'), indent=0)
    tot = sum(len(e['contests']) for e in done.values())
    st = Counter(r.get('status') for e in done.values() for r in e['contests'].values())
    print(f'{n} cards parsed this run; {len(done)} cards, {tot} card-contests in {a.out}: ' + ', '.join(f'{k} {v}' for k, v in st.most_common()))


if __name__ == '__main__':
    main()
