"""First-cut state vs federal comparison at matched venues.

Usage: python3 -m src.compare <db_path>
Prints a summary and writes data/analysis/venue_state_federal.csv
"""
import sys, os, sqlite3
import pandas as pd


def main(db):
    con = sqlite3.connect(db)
    q = '''
    SELECT venue_id, election_id, level, lat, lon, contest_id, booth_id, booth_type, party, votes, share
    FROM venue_party_share
    WHERE booth_type IN ('ordinary') AND party IN ('ALP','LIB','NAT','GRN','IND')
    '''
    df = pd.read_sql(q, con)
    # Coalition = LIB + NAT
    df['party'] = df.party.replace({'NAT': 'COAL', 'LIB': 'COAL'})
    agg = df.groupby(['venue_id', 'election_id', 'party']).agg(votes=('votes', 'sum')).reset_index()
    tot = pd.read_sql('''SELECT g.venue_id, s.election_id, SUM(s.votes) AS formal FROM booth_party_share s
                         JOIN booth_geo g ON g.booth_id = s.booth_id AND g.election_id = s.election_id
                         WHERE g.booth_type = 'ordinary' AND g.venue_id IS NOT NULL GROUP BY 1,2''', con)
    agg = agg.merge(tot, on=['venue_id', 'election_id'])
    agg['share'] = agg.votes / agg.formal
    wide = agg.pivot_table(index='venue_id', columns=['party', 'election_id'], values='share')
    wide.columns = [f'{p}_{e}' for p, e in wide.columns]
    wide = wide.reset_index()
    v = pd.read_sql('SELECT venue_id, premises, suburb, lat, lon FROM venues', con)
    wide = v.merge(wide, on='venue_id')
    both = wide.dropna(subset=['ALP_vic2022', 'ALP_fed2022'])
    print(f'venues with both a 2022 state and 2022 federal ordinary booth: {len(both)}')
    for p in ['ALP', 'COAL', 'GRN']:
        if f'{p}_vic2022' in both and f'{p}_fed2022' in both:
            d = (both[f'{p}_vic2022'] - both[f'{p}_fed2022'])
            print(f'  {p}: state 2022 minus federal 2022 primary, mean {d.mean()*100:+.1f} pts, median {d.median()*100:+.1f}, IQR {d.quantile(.25)*100:+.1f}..{d.quantile(.75)*100:+.1f}')
    both25 = wide.dropna(subset=['ALP_vic2022', 'ALP_fed2025'])
    print(f'venues with both a 2022 state and 2025 federal ordinary booth: {len(both25)}')
    os.makedirs('data/analysis', exist_ok=True)
    wide.to_csv('data/analysis/venue_state_federal.csv', index=False)
    # biggest state-vs-federal ALP gaps
    both = both.assign(alp_gap=both.ALP_vic2022 - both.ALP_fed2022)
    print('\nLargest ALP state-over-federal gaps (2022 vs 2022):')
    print(both.nlargest(8, 'alp_gap')[['premises', 'suburb', 'ALP_vic2022', 'ALP_fed2022', 'alp_gap']].round(3).to_string(index=False))
    print('\nLargest ALP federal-over-state gaps:')
    print(both.nsmallest(8, 'alp_gap')[['premises', 'suburb', 'ALP_vic2022', 'ALP_fed2022', 'alp_gap']].round(3).to_string(index=False))


if __name__ == '__main__':
    main(sys.argv[1])
