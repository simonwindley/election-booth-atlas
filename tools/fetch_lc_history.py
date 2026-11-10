"""Fetch the VEC's Legislative Council spreadsheets for 2006, 2010 and 2014 through the Internet Archive.

The old VEC site kept, per region: the STV count ("Distributions"), and the votes by voting centre
("VotesReceived" in 2014, "VotesDetails" and "FPVbyVC" in 2010, "FPVbyVC" in 2006). Each file is looked up
in the Wayback Machine's index and the newest good (HTTP 200) capture is downloaded unchanged.

Usage: python3 tools/fetch_lc_history.py [2014 2010 2006]
Writes raw/vec/<year>/legislative_council/<file>.xls (skips files already there).
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error

UA = 'ElectionBoothAtlas/1.0 (+https://github.com/simonwindley/election-booth-atlas)'
WB = 'https://web.archive.org'
REGIONS = ['EasternMetropolitan', 'EasternVictoria', 'NorthernMetropolitan', 'NorthernVictoria',
           'SouthEasternMetropolitan', 'SouthernMetropolitan', 'WesternMetropolitan', 'WesternVictoria']
FILES = {
    '2014': [('files/State2014/{r}RegionDistributions.xls', 'files/State2014/{r}RegionVotesReceived.xls')],
    '2010': [('files/state2010{r}RegionDistributions.xls', 'files/state2010{r}RegionVotesDetails.xls', 'files/state2010{r}RegionFPVbyVC.xls')],
    '2006': [('files/state2006{r}RegionDistributions.xls', 'files/state2006{r}RegionFPVbyVC.xls')],
}


def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            wait = 5 * (2 ** i)
            print(f'    HTTP {e.code} - waiting {wait}s', flush=True); time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            wait = 5 * (2 ** i)
            print(f'    {type(e).__name__} - waiting {wait}s', flush=True); time.sleep(wait)
    return None


def best_capture(path):
    """Newest HTTP-200 capture of www.vec.vic.gov.au/<path> (http or https), as (timestamp, original)."""
    q = urllib.parse.urlencode({'url': 'vec.vic.gov.au/' + path, 'fl': 'timestamp,original,statuscode', 'filter': 'statuscode:200', 'output': 'json'})
    data = get(f'{WB}/cdx/search/cdx?{q}')
    if not data:
        return None
    rows = json.loads(data.decode() or '[]')[1:]
    return (rows[-1][0], rows[-1][1]) if rows else None


def main(years):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for year in years:
        out = os.path.join(root, 'raw', 'vec', year, 'legislative_council'); os.makedirs(out, exist_ok=True)
        for r in REGIONS:
            for pattern in FILES[year][0]:
                path = pattern.format(r=r)
                fn = os.path.join(out, os.path.basename(path))
                if os.path.exists(fn) and os.path.getsize(fn) > 2000:
                    continue
                cap = best_capture(path)
                if not cap and 'SouthEastern' in path:   # 2014 spells it South-Eastern
                    cap = best_capture(path.replace('SouthEastern', 'South-Eastern'))
                if not cap:
                    print(f'  -- no capture of {path}', flush=True); continue
                ts, orig = cap
                data = get(f'{WB}/web/{ts}id_/{orig}')
                if not data or data[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':   # an .xls (OLE2) file
                    print(f'  !! {path}: not a spreadsheet ({len(data or b"")} bytes)', flush=True); continue
                with open(fn, 'wb') as f:
                    f.write(data)
                print(f'  {year} {os.path.basename(path)}  {len(data):,} bytes  (capture {ts})', flush=True)
                time.sleep(1.5)


if __name__ == '__main__':
    main(sys.argv[1:] or ['2014', '2010', '2006'])
