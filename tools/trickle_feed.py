"""Election-night rehearsal with the count trickling in: a synthetic 2026 count (the 2022 results with a swing, see
tools/synth_feed.py) written again every --every seconds with more booths reported each time, so a local copy of the
site can be watched filling up the way it will on the night. Invented numbers: never point it at the published site.

    python3 tools/trickle_feed.py /tmp/eba-rehearsal/data/live --minutes 20 --every 60

Then serve the copy (cd /tmp/eba-rehearsal && python3 -m http.server 8000) and open http://localhost:8000/?rehearse
Election-day booths come in first; early votes join at 35% of booths, postal votes at 75%, as the real count does.
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('outdir'); ap.add_argument('--minutes', type=float, default=20); ap.add_argument('--every', type=float, default=60)
ap.add_argument('--swing-coal', default='3'); ap.add_argument('--swing-grn', default='1'); ap.add_argument('--seed', default='7')
a = ap.parse_args()
if os.path.abspath(a.outdir).startswith(os.path.abspath(os.path.join(HERE, '..', 'site'))):
    sys.exit('trickle_feed: write to a copy of the site (e.g. /tmp/eba-rehearsal/data/live), never into the project\'s site/ folder')
os.makedirs(a.outdir, exist_ok=True)
out = os.path.join(a.outdir, 'latest.json')
if os.path.exists(out): os.remove(out)
steps = max(2, int(a.minutes * 60 / a.every))
print(f'no count yet: the page should show "No count yet" everywhere; first booths in {a.every:.0f} s')
time.sleep(a.every)
for k in range(1, steps + 1):
    f = min(1.0, (k / steps) ** 0.8)
    pools = 'early,postal' if f >= 0.75 else 'early' if f >= 0.35 else ''
    tmp = out + '.tmp'
    subprocess.run([sys.executable, os.path.join(HERE, 'synth_feed.py'), tmp, '--stable', '--now', '--reported', f'{f:.3f}', '--pools', pools,
                    '--swing-coal', a.swing_coal, '--swing-grn', a.swing_grn, '--seed', a.seed], check=True, capture_output=True)
    os.replace(tmp, out)
    print(f'{time.strftime("%H:%M:%S")}  step {k}/{steps}: {100 * f:.0f}% of election-day booths in' + (f', counted pools: {pools}' if pools else ''), flush=True)
    if k < steps: time.sleep(a.every)
print('count complete. Ctrl-C to stop the web server; delete /tmp/eba-rehearsal when done.')
