"""Export the compact gzip-JSON data files the static site loads (no parquet library needed in the browser).

Usage: python3 -m src.export_site <db_path> <site_data_dir>
Every table is {"cols": [...], "rows": [[...], ...]} and gzipped; GeoJSON layers are gzipped as-is.
"""
import sys, os, json, gzip, glob, sqlite3, shutil
import pandas as pd


def write(out, name, df):
    df = df.astype(object).where(pd.notna(df), None)
    payload = {'cols': list(df.columns), 'rows': df.values.tolist()}
    with gzip.open(f'{out}/{name}.json.gz', 'wt', compresslevel=9) as f:
        json.dump(payload, f, separators=(',', ':'))
    return os.path.getsize(f'{out}/{name}.json.gz')


def main(db, out):
    con = sqlite3.connect(db)
    os.makedirs(out, exist_ok=True)
    sizes = {}
    q = lambda s: pd.read_sql(s, con)
    sizes['elections'] = write(out, 'elections', q('SELECT * FROM elections ORDER BY date'))
    sizes['contests'] = write(out, 'contests', q("""SELECT election_id, contest_id, contest_name, house, enrolment, formal, informal, total_votes FROM contests"""))
    sizes['candidates'] = write(out, 'candidates', q("""SELECT election_id, contest_id, candidate_id, surname, given_name, party, party_name, ballot_position, elected FROM candidates"""))
    sizes['booths'] = write(out, 'booths', q("""
        SELECT b.election_id, b.contest_id, b.booth_id, b.booth_name, b.booth_type, g.venue_id,
               ROUND(g.lat, 5) AS lat, ROUND(g.lon, 5) AS lon, g.geo_source
        FROM booths b LEFT JOIN booth_geo g ON g.election_id = b.election_id AND g.booth_id = b.booth_id"""))
    sizes['shares'] = write(out, 'shares', q("""
        SELECT election_id, booth_id, party, votes, ROUND(share, 4) AS share FROM booth_party_share"""))
    sizes['fp'] = write(out, 'fp', q("""SELECT election_id, booth_id, candidate_id, votes FROM fp_votes"""))
    sizes['tcp'] = write(out, 'tcp', q("""SELECT election_id, booth_id, candidate_id, votes FROM tcp_votes"""))
    sizes['venues'] = write(out, 'venues', q("""SELECT venue_id, premises, address, suburb, postcode, ROUND(lat,5) lat, ROUND(lon,5) lon FROM venues"""))
    # electorate-wide results: every vote type, from the same tables the booth map uses
    sizes['contest_party'] = write(out, 'contest_party', q("""
        SELECT f.election_id, b.contest_id, COALESCE(c.party, 'INFORMAL') AS party, SUM(f.votes) AS votes
        FROM fp_votes f JOIN booths b ON b.election_id = f.election_id AND b.booth_id = f.booth_id
        LEFT JOIN candidates c ON c.election_id = f.election_id AND c.candidate_id = f.candidate_id
        GROUP BY 1, 2, 3"""))
    sizes['contest_cand'] = write(out, 'contest_cand', q("""
        SELECT f.election_id, b.contest_id, f.candidate_id, SUM(f.votes) AS votes
        FROM fp_votes f JOIN booths b ON b.election_id = f.election_id AND b.booth_id = f.booth_id
        WHERE f.candidate_id <> 'INFORMAL' GROUP BY 1, 2, 3"""))
    # final two-candidate count per contest: the last count of the official distribution, else the
    # indicative distribution, else the two-candidate-preferred count summed over every vote type
    last_official = q("""SELECT d.election_id, d.contest_id, d.candidate_id, d.progressive_total AS votes, 'distribution' AS source
        FROM dop d JOIN (SELECT election_id, contest_id, MAX(count_no) mc FROM dop GROUP BY 1,2) m
          ON m.election_id = d.election_id AND m.contest_id = d.contest_id AND m.mc = d.count_no
        WHERE d.progressive_total > 0""")
    two = last_official.groupby(['election_id', 'contest_id']).candidate_id.transform('size') == 2
    final = last_official[two]
    # the district page's own "votes after distribution of preferences" table outranks everything when it names exactly two
    try:
        fp2 = q("SELECT election_id, contest_id, candidate_id, votes, 'official result' AS source FROM final_pair")
        fp2 = fp2[fp2.groupby(['election_id', 'contest_id']).candidate_id.transform('size') == 2]
        have2 = set(zip(fp2.election_id, fp2.contest_id))
        final = pd.concat([fp2, final[[ (a, b) not in have2 for a, b in zip(final.election_id, final.contest_id)]]])
    except Exception as ex:
        print('no final_pair table:', ex)
    try:
        ind = q("""SELECT d.election_id, d.contest_id, d.candidate_id, d.progressive_total AS votes, 'indicative distribution' AS source
            FROM dop_indicative d JOIN (SELECT election_id, contest_id, MAX(count_no) mc FROM dop_indicative GROUP BY 1,2) m
              ON m.election_id = d.election_id AND m.contest_id = d.contest_id AND m.mc = d.count_no
            WHERE d.progressive_total > 0""")
        ind = ind[ind.groupby(['election_id', 'contest_id']).candidate_id.transform('size') == 2]
        have = set(zip(final.election_id, final.contest_id))
        final = pd.concat([final, ind[[ (a, b) not in have for a, b in zip(ind.election_id, ind.contest_id)]]])
    except Exception:
        pass
    tcp_sum = q("""SELECT t.election_id, b.contest_id, t.candidate_id, SUM(t.votes) AS votes, 'two-candidate count' AS source
        FROM tcp_votes t JOIN booths b ON b.election_id = t.election_id AND b.booth_id = t.booth_id GROUP BY 1,2,3""")
    have = set(zip(final.election_id, final.contest_id))
    final = pd.concat([final, tcp_sum[[ (a, b) not in have for a, b in zip(tcp_sum.election_id, tcp_sum.contest_id)]]], ignore_index=True)
    sizes['contest_tcp'] = write(out, 'contest_tcp', final)
    sizes['dop'] = write(out, 'dop', q("""SELECT election_id, contest_id, count_no, candidate_id, transfer, progressive_total, excluded FROM dop"""))
    sizes['lc_contests'] = write(out, 'lc_contests', q('SELECT * FROM lc_contests'))
    sizes['lc_candidates'] = write(out, 'lc_candidates', q('SELECT election_id, contest_id, candidate_id, "group", party, party_name, name, is_atl FROM lc_candidates'))
    for eid in [r[0] for r in con.execute('SELECT DISTINCT election_id FROM lc_votes')]:
        sizes['lc_votes_' + eid] = write(out, 'lc_votes_' + eid, q(f"SELECT election_id, contest_id, booth_id, booth_type, candidate_id, votes FROM lc_votes WHERE election_id = '{eid}'"))
    # 2026 pre-election register (declared candidates etc.), straight from data/vic2026
    for name in ['contests', 'candidates', 'retiring', 'withdrawals']:
        p = f'data/vic2026/{name}.csv'
        if os.path.exists(p):
            sizes['c2026_' + name] = write(out, 'c2026_' + name, pd.read_csv(p))
    if os.path.exists('data/vic2026/meta.json'):
        shutil.copy('data/vic2026/meta.json', f'{out}/c2026_meta.json'); sizes['c2026_meta'] = os.path.getsize(f'{out}/c2026_meta.json')
    for f in glob.glob('data/boundaries/*.geojson') + glob.glob('data/catchments/*.geojson'):
        name = ('boundary_' if 'boundaries' in f else 'catchment_') + os.path.basename(f)[:-8]
        with open(f, 'rb') as src, gzip.open(f'{out}/{name}.geojson.gz', 'wb', compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        sizes[name] = os.path.getsize(f'{out}/{name}.geojson.gz')
    json.dump({'ext': '.json.gz', 'files': sizes}, open(f'{out}/manifest.json', 'w'), indent=1)
    # a plain (uncompressed) copy for hosts that cannot serve .gz files
    plain = out.rstrip('/') + '_plain'
    os.makedirs(plain, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.json') and f != 'manifest.json':
            shutil.copy(f'{out}/{f}', f'{plain}/{f}')
        if f.endswith('.gz'):
            with gzip.open(f'{out}/{f}', 'rb') as src, open(f'{plain}/{f[:-3]}', 'wb') as dst:
                shutil.copyfileobj(src, dst)
    json.dump({'ext': '.json', 'files': sizes}, open(f'{plain}/manifest.json', 'w'), indent=1)
    print('\n'.join(f'{k:32s} {v/1024:8.0f} KB' for k, v in sizes.items()))
    print(f'total {sum(sizes.values())/1e6:.1f} MB')


if __name__ == '__main__':
    main(*sys.argv[1:3])
