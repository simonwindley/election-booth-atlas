"""Assemble the normalised CSVs into a single SQLite database with analysis views.

Usage: python3 -m src.build_db <db_path> <data_dir>
Expects <data_dir>/<election_id>/{contests,candidates,booths,fp_votes,tcp_votes,dop}.csv
and <data_dir>/venues/{venues,vec_booth_venue,geocoded}.csv
"""
import sys, os, glob, sqlite3
import pandas as pd

ELECTIONS = {
    # election_id: (level, date, name)
    'vic2010': ('state', '2010-11-27', 'Victorian state election 2010'),
    'vic2014': ('state', '2014-11-29', 'Victorian state election 2014'),
    'vic2018': ('state', '2018-11-24', 'Victorian state election 2018'),
    'vic2022': ('state', '2022-11-26', 'Victorian state election 2022'),
    'vic2023n': ('state', '2023-01-28', 'Narracan supplementary election 2023'),
    'fed2010': ('federal', '2010-08-21', 'Federal election 2010'),
    'fed2013': ('federal', '2013-09-07', 'Federal election 2013'),
    'fed2016': ('federal', '2016-07-02', 'Federal election 2016'),
    'fed2019': ('federal', '2019-05-18', 'Federal election 2019'),
    'fed2022': ('federal', '2022-05-21', 'Federal election 2022'),
    'fed2025': ('federal', '2025-05-03', 'Federal election 2025'),
    'vicby-warrandyte-2023': ('state-by', '2023-08-26', 'Warrandyte by-election 2023'),
    'vicby-mulgrave-2023': ('state-by', '2023-11-18', 'Mulgrave by-election 2023'),
    'vicby-prahran-2025': ('state-by', '2025-02-08', 'Prahran by-election 2025'),
    'vicby-werribee-2025': ('state-by', '2025-02-08', 'Werribee by-election 2025'),
    'vicby-nepean-2026': ('state-by', '2026-05-02', 'Nepean by-election 2026'),
}


def main(db_path, data_dir):
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    tables = {}
    for d in sorted(glob.glob(f'{data_dir}/*/')):
        eid = os.path.basename(d.rstrip('/'))
        if eid in ('venues', 'vic2026', 'bundle', 'boundaries', 'catchments', 'analysis', 'senate'):
            continue
        for f in glob.glob(f'{d}/*.csv'):
            t = os.path.basename(f)[:-4]
            if os.path.getsize(f) < 2:
                continue
            tables.setdefault(t, []).append(pd.read_csv(f))
    for t, dfs in tables.items():
        pd.concat(dfs, ignore_index=True).to_sql(t, con, index=False)
    pd.DataFrame([{'election_id': k, 'level': v[0], 'date': v[1], 'name': v[2]} for k, v in ELECTIONS.items()]).to_sql('elections', con, index=False)
    venues = pd.read_csv(f'{data_dir}/venues/venues.csv')
    venues.to_sql('venues', con, index=False)
    bv = pd.read_csv(f'{data_dir}/venues/vec_booth_venue.csv')
    bv.to_sql('vec_booth_venue', con, index=False)
    # AEC booth -> venue, per election (a booth that moved premises maps to a different venue)
    from .match_venues import norm
    ab = pd.concat(tables['booths'], ignore_index=True)
    ab = ab[ab.election_id.str.startswith('fed') & ab.lat.notna()].copy()
    ab['vkey'] = ab.premises.fillna('').map(norm) + '|' + ab.lat.round(2).astype(str) + '|' + ab.lon.round(2).astype(str)
    ab = ab.merge(venues[['vkey', 'venue_id']], on='vkey', how='left')
    ab[['election_id', 'booth_id', 'venue_id']].to_sql('aec_booth_venue', con, index=False)
    pd.read_csv(f'{data_dir}/venues/geocoded.csv').to_sql('geocoded', con, index=False)
    if os.path.exists(f'{data_dir}/senate/senators_elected.csv'):
        pd.read_csv(f'{data_dir}/senate/senators_elected.csv').to_sql('senators_elected', con, index=False)
    # booth -> venue, lat, lon for every election: AEC booths via their own venue ids, VEC via the match table
    con.executescript('''
    CREATE TABLE booth_geo AS
    SELECT b.election_id, b.contest_id, b.booth_id, b.booth_type,
           COALESCE(CASE WHEN b.election_id LIKE 'fed%' THEN v.venue_id ELSE m.venue_id END,
                    CASE WHEN g.lat IS NOT NULL THEN 'g-' || b.booth_id END) AS venue_id,
           COALESCE(b.lat, v2.lat, g.lat) AS lat, COALESCE(b.lon, v2.lon, g.lon) AS lon,
           CASE WHEN b.lat IS NOT NULL THEN 'aec'
                WHEN m.method IN ('exact_unique','exact_cluster','exact_nearest') THEN 'aec_name_match'
                WHEN m.method = 'fuzzy' THEN 'aec_fuzzy_review'
                WHEN g.lat IS NOT NULL THEN 'geocoded_approx' ELSE NULL END AS geo_source
    FROM booths b
    LEFT JOIN vec_booth_venue m ON m.booth_id = b.booth_id AND m.method <> 'unmatched' AND m.method <> 'fuzzy'
    LEFT JOIN venues v2 ON v2.venue_id = m.venue_id
    LEFT JOIN aec_booth_venue v ON v.election_id = b.election_id AND v.booth_id = b.booth_id
    LEFT JOIN geocoded g ON g.booth_id = b.booth_id;
    CREATE INDEX ix_fp ON fp_votes(election_id, contest_id, booth_id);
    CREATE INDEX ix_cand ON candidates(election_id, candidate_id);
    CREATE INDEX ix_bg ON booth_geo(booth_id);

    -- first preferences by canonical party per booth (informal kept as party 'INFORMAL')
    CREATE VIEW booth_party_fp AS
    SELECT f.election_id, f.contest_id, f.booth_id, COALESCE(c.party, 'INFORMAL') AS party, SUM(f.votes) AS votes
    FROM fp_votes f LEFT JOIN candidates c ON c.election_id = f.election_id AND c.candidate_id = f.candidate_id
    GROUP BY 1,2,3,4;

    -- party share of the formal vote per booth
    CREATE VIEW booth_party_share AS
    SELECT p.election_id, p.contest_id, p.booth_id, p.party, p.votes,
           1.0 * p.votes / t.formal AS share
    FROM booth_party_fp p
    JOIN (SELECT election_id, booth_id, SUM(votes) AS formal FROM booth_party_fp WHERE party <> 'INFORMAL' GROUP BY 1,2) t
      ON t.election_id = p.election_id AND t.booth_id = p.booth_id
    WHERE p.party <> 'INFORMAL';

    -- the venue time series: party share at each physical venue, each election (ordinary + early booths only)
    CREATE VIEW venue_party_share AS
    SELECT g.venue_id, g.lat, g.lon, s.election_id, e.level, e.date, s.contest_id, s.booth_id, g.booth_type, s.party, s.votes, s.share
    FROM booth_party_share s
    JOIN booth_geo g ON g.booth_id = s.booth_id AND g.election_id = s.election_id
    JOIN elections e ON e.election_id = s.election_id
    WHERE g.lat IS NOT NULL;
    ''')
    con.commit()
    for t in ['elections', 'contests', 'candidates', 'booths', 'fp_votes', 'tcp_votes', 'dop', 'venues', 'booth_geo']:
        print(t, con.execute(f'select count(*) from {t}').fetchone()[0])
    con.close()


if __name__ == '__main__':
    main(*sys.argv[1:3])
