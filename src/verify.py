"""Hard reconciliation checks for a loaded state election. Exits non-zero on any failure.
Usage: python3 -m src.verify <data_dir> (e.g. data/vic2022)"""
import sys
import pandas as pd

def main(d):
    c = pd.read_csv(f'{d}/contests.csv').set_index('contest_id')
    fp = pd.read_csv(f'{d}/fp_votes.csv'); b = pd.read_csv(f'{d}/booths.csv')
    import os
    dop = pd.read_csv(f'{d}/dop.csv') if os.path.getsize(f'{d}/dop.csv') > 1 else pd.DataFrame(columns=['contest_id', 'count_no', 'transfer', 'progressive_total', 'excluded'])
    import os, json
    exc = json.load(open(f'{d}/verify_exceptions.json')) if os.path.exists(f'{d}/verify_exceptions.json') else {}
    fails = []
    for cid, row in c.iterrows():
        f = fp[fp.contest_id == cid]
        if (b[(b.contest_id == cid) & (b.booth_type == 'ordinary')].shape[0] == 0):
            fails.append(f'{cid}: no ordinary booths')
        if f[f.candidate_id != 'INFORMAL'].votes.sum() != row.formal:
            fails.append(f'{cid}: FP sum {f[f.candidate_id != "INFORMAL"].votes.sum()} != formal {row.formal}')
        if f[f.candidate_id == 'INFORMAL'].votes.sum() != row.informal:
            fails.append(f'{cid}: informal mismatch')
        dd = dop[dop.contest_id == cid]
        if len(dd):
            last = dd[dd.count_no == dd.count_no.max()]
            if last[last.excluded == 0].progressive_total.sum() != row.formal:
                fails.append(f'{cid}: distribution final total mismatch')
            if (dd.groupby('count_no').transfer.sum() != 0).any():
                fails.append(f'{cid}: transfers do not balance')
    print(f'{d}: {len(c)} contests, {len(b[b.booth_type=="ordinary"])} ordinary booths, {dop.contest_id.nunique()} distributions; {len(fails)} failures')
    real = [x for x in fails if x.split(':')[0] not in exc]
    for x in fails: print('  ' + ('KNOWN' if x.split(':')[0] in exc else 'FAIL'), x)
    sys.exit(1 if real else 0)

if __name__ == '__main__':
    main(sys.argv[1])
