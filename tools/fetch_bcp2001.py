"""Download the ABS 2001 Census Basic Community Profiles for Victoria's 88 State Electoral Divisions.

The 2001 Census SEDs are the Legislative Assembly districts drawn in 1991 (used at the 1992, 1996 and 1999 elections),
so these give the 1999 election a census of its own time. Standard library only; re-running skips files already there.

    python3 tools/fetch_bcp2001.py raw/abs/bcp2001
"""
import sys, os, time, urllib.request

SED = ['SED20115', 'SED20214', 'SED20301', 'SED20401', 'SED20518', 'SED20607', 'SED20702', 'SED20816', 'SED20917', 'SED21017', 'SED21121',
       'SED21209', 'SED21306', 'SED21405', 'SED21509', 'SED21613', 'SED21720', 'SED21810', 'SED21905', 'SED22003', 'SED22115', 'SED22221',
       'SED22312', 'SED22419', 'SED22506', 'SED22606', 'SED22720', 'SED22819', 'SED22920', 'SED23012', 'SED23102', 'SED23214', 'SED23311',
       'SED23403', 'SED23503', 'SED23607', 'SED23707', 'SED23808', 'SED23908', 'SED24019', 'SED24101', 'SED24221', 'SED24305', 'SED24420',
       'SED24504', 'SED24605', 'SED24711', 'SED24815', 'SED24912', 'SED25004', 'SED25117', 'SED25210', 'SED25311', 'SED25418', 'SED25518',
       'SED25609', 'SED25719', 'SED25808', 'SED25916', 'SED26008', 'SED26104', 'SED26210', 'SED26321', 'SED26406', 'SED26513', 'SED26622',
       'SED26722', 'SED26815', 'SED26910', 'SED27012', 'SED27101', 'SED27216', 'SED27309', 'SED27402', 'SED27516', 'SED27607', 'SED27703',
       'SED27804', 'SED27917', 'SED28013', 'SED28113', 'SED28211', 'SED28318', 'SED28422', 'SED28514', 'SED28614', 'SED28722', 'SED28802']
EXTRA = ['2']   # Victoria as a whole, for the state column
BASE = 'https://www.abs.gov.au/census/find-census-data/community-profiles/2001/{c}/download/BCP_{c}.xlsx'


def main(out):
    os.makedirs(out, exist_ok=True)
    for i, c in enumerate(SED + EXTRA, 1):
        path = os.path.join(out, f'BCP_{c}.xlsx')
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            continue
        for attempt in range(5):
            try:
                req = urllib.request.Request(BASE.format(c=c), headers={'User-Agent': 'ElectionBoothAtlas/1.0'})
                data = urllib.request.urlopen(req, timeout=60).read()
                open(path, 'wb').write(data)
                print(f'[{i}/{len(SED) + len(EXTRA)}] {c} {len(data) // 1024} KB', flush=True)
                break
            except Exception as e:  # noqa: BLE001
                print(f'   {c}: {e} - retrying', flush=True); time.sleep(5 * (attempt + 1))
        time.sleep(0.5)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'raw/abs/bcp2001')
