"""Export the front-end data bundle: Parquet tables + GeoJSON layers + manifest.

Usage: python3 -m src.export_bundle <db_path> <out_dir>
The static site loads these with DuckDB-WASM (parquet) and MapLibre (geojson).
"""
import sys, os, json, glob, sqlite3, shutil, datetime
import pandas as pd
import pyarrow as pa, pyarrow.parquet as pq

TABLES = ['elections', 'contests', 'candidates', 'booths', 'booth_geo', 'fp_votes', 'tcp_votes', 'dop', 'dop_indicative',
          'lc_contests', 'lc_candidates', 'lc_votes', 'lc_dop', 'venues', 'vec_booth_venue', 'geocoded']
VIEWS = {
    'booth_party_share': 'SELECT * FROM booth_party_share',
    'venue_party_share': 'SELECT * FROM venue_party_share',
}


def main(db, out):
    con = sqlite3.connect(db)
    os.makedirs(f'{out}/tables', exist_ok=True)
    os.makedirs(f'{out}/geo', exist_ok=True)
    manifest = {'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'tables': {}, 'geo': {}}
    for t in TABLES:
        try:
            df = pd.read_sql(f'SELECT * FROM {t}', con)
        except Exception as e:
            print('skip', t, e); continue
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), f'{out}/tables/{t}.parquet', compression='zstd')
        manifest['tables'][t] = {'rows': len(df), 'columns': list(df.columns)}
    for name, sql in VIEWS.items():
        df = pd.read_sql(sql, con)
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), f'{out}/tables/{name}.parquet', compression='zstd')
        manifest['tables'][name] = {'rows': len(df), 'columns': list(df.columns)}
    for f in glob.glob('data/boundaries/*.geojson') + glob.glob('data/catchments/*.geojson'):
        kind = 'boundary' if 'boundaries' in f else 'catchment'
        name = f'{kind}_{os.path.basename(f)}'
        shutil.copy(f, f'{out}/geo/{name}')
        n = len(json.load(open(f))['features'])
        manifest['geo'][name] = {'features': n, 'bytes': os.path.getsize(f)}
    for f in glob.glob('data/catchments/h3_*.csv'):
        df = pd.read_csv(f)
        if len(df):
            pq.write_table(pa.Table.from_pandas(df, preserve_index=False), f'{out}/tables/{os.path.basename(f)[:-4]}.parquet', compression='zstd')
            manifest['tables'][os.path.basename(f)[:-4]] = {'rows': len(df), 'columns': list(df.columns)}
    json.dump(manifest, open(f'{out}/manifest.json', 'w'), indent=1)
    total = sum(os.path.getsize(p) for p in glob.glob(f'{out}/**/*', recursive=True) if os.path.isfile(p))
    print(f'bundle: {len(manifest["tables"])} tables, {len(manifest["geo"])} geo layers, {total/1e6:.1f} MB')


if __name__ == '__main__':
    main(*sys.argv[1:3])
