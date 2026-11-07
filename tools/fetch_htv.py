"""Download the registered how-to-vote cards (PDFs) listed in a VEC register capture.

    python3 tools/fetch_htv.py raw/htv/register_2022.json raw/htv/2022      # the 2022 cards
    python3 tools/fetch_htv.py site/data/live/daily.json raw/htv/2026        # the 2026 cards as captured by live/vec_daily.py

Needs internet access (run on the Mac). Skips files already downloaded, so it can be re-run as more cards
register. Writes <out>/<registration>.pdf and <out>/index.json (registration -> card details + file).
"""
import sys, os, json, time, re, urllib.request, urllib.parse

UA = 'ElectionBoothAtlas/1.0 (how-to-vote card archive; personal research)'


def main(src, out):
    j = json.load(open(src))
    cards = j['cards'] if 'cards' in j else (j.get('htv') or {}).get('cards', [])
    os.makedirs(out, exist_ok=True)
    index_path = os.path.join(out, 'index.json')
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    done = fails = 0
    for c in cards:
        if not c.get('pdf') or not c.get('registration'):
            continue
        reg = str(c['registration'])
        path = os.path.join(out, f'{reg}.pdf')
        if os.path.exists(path) and os.path.getsize(path) > 0:
            index[reg] = {**c, 'file': os.path.basename(path)}
            continue
        url = c['pdf'].replace('\\', '/')
        url = urllib.parse.quote(url, safe=':/?&=%')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if not data.startswith(b'%PDF'):
                print(f'  not a PDF: {reg} {url[:90]}'); fails += 1; continue
            open(path, 'wb').write(data)
            index[reg] = {**c, 'file': os.path.basename(path)}
            done += 1
            if done % 25 == 0:
                print(f'  {done} downloaded...')
            time.sleep(0.4)
        except Exception as e:
            print(f'  failed {reg}: {e}'); fails += 1
    json.dump(index, open(index_path, 'w'), indent=0)
    print(f'{done} downloaded this run, {fails} failed, {len(index)} in {index_path}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
