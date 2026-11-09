#!/usr/bin/env python3
"""Fetch the economic and local data for the economy questions in analysis/questions.json.

Run from the project folder in your own Terminal:
    python3 tools/fetch_econ.py            # everything (a few minutes; the ABS labour force file is ~45 MB)
    python3 tools/fetch_econ.py rents lxrp # just some sources (names below)
Files land in raw/econ/<source>/ ; re-running refreshes them (they are small, except abs).

  rba      RBA statistical tables (CSV): F1.1 cash rate; F5 indicator lending rates; F6 housing lending rates;
           E13 housing loan payments; G1 consumer price inflation; H5 labour force
  abs      ABS Data API (CSV with labels): CPI by capital city and expenditure group (quarterly, 1998-);
           Wage Price Index; Labour Force (states, 1998-); regional data by SA2 and LGA, 2011-2025: median house
           and unit prices and sales, median employee, investment, superannuation and total income, building approvals, population
  rents    DFFH Rental Report: moving annual median rent by suburb and town; quarterly median rents by LGA
           (the latest editions, which carry the full history back to 1999/2000)
  sales    Valuer-General Victoria: median house / unit / vacant-land prices by suburb (time-series workbooks),
           and the Guide to Property Values statistics workbook (older years)
  salm     Jobs and Skills / DEWR Small Area Labour Markets: smoothed unemployment by SA2 and LGA, quarterly 2010-
  budget   Victorian State Capital Program (Budget Paper No. 4), every budget from 2013-14: projects, locations, costs
  lxrp     Level Crossing Removal Project: the Wikipedia list (line, road, nearest station, solution, completion
           month) and the coordinates of every station named in it (Wikipedia API)
"""
import os, re, sys, json, time, urllib.request, urllib.parse, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'raw', 'econ')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15 (Election Booth Atlas research)',
      'Accept': '*/*'}


def get(url, headers=None, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read(), r.geturl()
        except Exception as e:
            if k == tries - 1:
                raise
            time.sleep(4 * (k + 1))


def save(sub, name, blob):
    d = os.path.join(OUT, sub); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name); open(p, 'wb').write(blob)
    print(f'  {sub}/{name}  {len(blob) / 1024:,.0f} KB', flush=True)
    return p


def links(page, pattern):
    blob, base = get(page)
    t = blob.decode('utf-8', 'replace')
    out = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        full = urllib.parse.urljoin(base, html.unescape(href))
        txt = re.sub(r'<[^>]+>|\s+', ' ', text).strip()
        if re.search(pattern, full + ' ' + txt, re.I):
            out.append((full, txt))
    return out


def rba():
    for t in ('f1.1', 'f5', 'f6', 'e13', 'g1', 'h5'):
        save('rba', f'{t}-data.csv', get(f'https://www.rba.gov.au/statistics/tables/csv/{t}-data.csv')[0])


def abs_api():
    base = 'https://data.api.abs.gov.au/rest/data/ABS,{flow}/{key}?{q}format=csvfilewithlabels'
    for flow, key, q, name in (('CPI_Q,1.0.0', 'all', 'startPeriod=1998&', 'cpi_q.csv'),
                               ('WPI,1.2.0', 'all', 'startPeriod=1998&', 'wpi.csv'),
                               ('LF,1.0.0', 'all', 'startPeriod=1998&', 'labour_force.csv')):
        save('abs', name, get(base.format(flow=flow, key=key, q=q))[0])
    for m in ('HOUSES_2', 'HOUSES_3', 'HOUSES_4', 'HOUSES_5', 'INCOME_2', 'INCOME_8', 'INCOME_11', 'INCOME_17', 'INCOME_36', 'EQUIV_2', 'BUILDING_4', 'ERP_P_20'):
        for rt in ('SA2', 'LGA'):
            if os.path.exists(os.path.join(OUT, 'abs', f'regional_{m}_{rt}.csv')):
                continue
            # the LGA region-type code follows the LGA edition in the release (LGA2021 ... LGA2024): try each
            for code in ((rt,) if rt == 'SA2' else ('LGA2024', 'LGA2023', 'LGA2022', 'LGA2021')):
                try:
                    save('abs', f'regional_{m}_{rt}.csv', get(base.format(flow='ABS_REGIONAL_ASGS2021,1.6.0', key=f'{m}.{code}..A', q=''), tries=1)[0])
                    break
                except Exception as e:
                    err = e
            else:
                print(f'  regional {m} {rt}: failed ({err})')
            time.sleep(1)


def rents():
    page = 'https://www.dffh.vic.gov.au/publications/rental-report'
    found = links(page, r'moving-annual-median-rent-suburb|quarterly-median-rents-local-government-area|tables-rental-report')
    if not found:
        print('  no rental report links found on', page); return
    for url, txt in found:
        blob, final = get(url)
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(final).path)) or re.sub(r'\W+', '_', txt) + '.xlsx'
        save('rents', name, blob)


def sales():
    urls = ['https://www.land.vic.gov.au/__data/assets/excel_doc/0033/775617/houses-by-suburb-2015-2025.xlsx',
            'https://www.land.vic.gov.au/__data/assets/excel_doc/0034/775618/units-by-suburb-2015-2025.xlsx',
            'https://www.land.vic.gov.au/__data/assets/excel_doc/0035/775619/land-by-suburb-2015-2025.xlsx',
            'https://www.land.vic.gov.au/__data/assets/excel_doc/0029/709751/Houses-by-suburb-2013-2023.xlsx',
            'https://www.land.vic.gov.au/__data/assets/excel_doc/0031/709753/Units-by-suburb-2013-2023.xlsx',
            'https://www.propertyandlandtitles.vic.gov.au/__data/assets/excel_doc/0018/427032/All-statistics.xls']
    try:   # newer editions, if published since
        urls += [u for u, _ in links('https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics', r'by-suburb.*\.xlsx|median-(house|unit)-.*\.xls') if u not in urls]
    except Exception as e:
        print('  property sales page:', e)
    for u in urls:
        try:
            save('sales', os.path.basename(urllib.parse.urlparse(u).path), get(u)[0])
        except Exception as e:
            print(f'  {u}: failed ({e})')


def salm():
    for page in ('https://www.dewr.gov.au/employment-research/resources/salm-smoothed-sa2-datafiles-asgs-2021',
                 'https://www.dewr.gov.au/employment-research/resources/salm-smoothed-lga-datafiles-asgs-2025'):
        found = [u for u, t in links(page, r'/download/') if u.rstrip('/').endswith('xlsx')]
        if not found:
            print('  no download link on', page); continue
        save('salm', page.rstrip('/').split('/')[-1] + '.xlsx', get(found[0])[0])


def lxrp():
    raw, _ = get('https://en.wikipedia.org/w/index.php?title=Level_Crossing_Removal_Project&action=raw')
    save('lxrp', 'level_crossing_removal_project.wikitext', raw)
    t = raw.decode('utf-8')
    stations = sorted(set(re.findall(r'\[\[([^\]|]+? railway station)(?:\|[^\]]*)?\]\]', t)))
    coords = {}
    for i in range(0, len(stations), 50):
        q = urllib.parse.urlencode({'action': 'query', 'prop': 'coordinates', 'titles': '|'.join(stations[i:i + 50]), 'format': 'json', 'redirects': 1})
        j = json.loads(get('https://en.wikipedia.org/w/api.php?' + q)[0])
        redir = {r['from']: r['to'] for r in j['query'].get('redirects', [])}
        norm = {r['from']: r['to'] for r in j['query'].get('normalized', [])}
        bytitle = {p['title']: p.get('coordinates', [{}])[0] for p in j['query']['pages'].values()}
        for s in stations[i:i + 50]:
            tt = redir.get(norm.get(s, s), norm.get(s, s))
            c = bytitle.get(tt) or {}
            if c.get('lat'):
                coords[s] = [c['lat'], c['lon']]
        time.sleep(1)
    save('lxrp', 'station_coordinates.json', json.dumps(coords, indent=1).encode())
    print(f'  {len(coords)} of {len(stations)} stations located')


def budget():
    """Victorian State Capital Program (Budget Paper No. 4): every capital project with its location and total
    estimated investment, one workbook per budget (2013-14 onwards), found through the DataVic catalogue"""
    api = 'https://discover.data.vic.gov.au/api/3/action/package_search?' + urllib.parse.urlencode({'q': 'State Capital Program', 'rows': 100})
    j = json.loads(get(api)[0])
    n = 0
    for p in j['result']['results']:
        if not re.search(r'capital program', p['title'], re.I):
            continue
        for r in p.get('resources', []):
            u = r.get('url') or ''
            if not re.search(r'\.xlsx?$', u, re.I):
                continue
            name = re.sub(r'[^A-Za-z0-9._-]+', '_', p['name'])[:80] + '__' + os.path.basename(urllib.parse.urlparse(u).path)
            try:
                save('budget', urllib.parse.unquote(name), get(u)[0]); n += 1
            except Exception as e:
                print(f'  {u}: failed ({e})')
            time.sleep(0.5)
    print(f'  {n} capital program workbooks')


SOURCES = {'rba': rba, 'abs': abs_api, 'rents': rents, 'sales': sales, 'salm': salm, 'lxrp': lxrp, 'budget': budget}


def main():
    want = [a for a in sys.argv[1:] if a in SOURCES] or list(SOURCES)
    for k in want:
        print(k, flush=True)
        try:
            SOURCES[k]()
        except Exception as e:
            print(f'  {k} failed: {e}')
    print('done ->', OUT)


if __name__ == '__main__':
    main()
