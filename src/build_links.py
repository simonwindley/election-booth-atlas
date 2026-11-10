"""Build site/data/c2026_links.json from the hand-checked sweep files in raw/links/.

Each line: <contest|surname|given> <party-page slug or -> k=url ...
k: w website, f facebook, i instagram, xx X, t TikTok, l LinkedIn, y YouTube, b Bluesky, th Threads; htv = Liberal HTV path.
Only links a party publishes on the candidate's own page, or a campaign site cited for the candidate, go in.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'raw' / 'links'
OUT = ROOT / 'site' / 'data' / 'c2026_links.json'
KIND = {'w': 'website', 'f': 'facebook', 'i': 'instagram', 'xx': 'x', 't': 'tiktok', 'l': 'linkedin', 'y': 'youtube', 'b': 'bluesky', 'th': 'threads'}
PAGE = {
    'alp': 'https://www.viclabor.org.au/our-team/{}',
    'lib': 'https://vicliberal.org.au/team/{}',
    'grn': 'https://greens.org.au/vic/person/{}',
    'nat': 'https://vic.nationals.org.au/our-team/',
    'vsp': 'https://www.victoriansocialists.org.au/candidates/{}',
    'onp': 'https://vic.onenation.org.au/candidate/{}',
}


def url(v):
    v = v.strip()
    if not re.match(r'^https?://', v):
        v = 'https://' + ('www.' if re.match(r'^(facebook|instagram|x|twitter|youtube|tiktok|linkedin)\.com/', v) else '') + v
    v = re.sub(r'^http://', 'https://', v)
    if 'facebook.com/profile.php' not in v:
        v = re.sub(r'\?.*$', '', v)
    return v if v.count('/') > 2 else v + '/'


def main():
    links, htv = {}, {}
    for party, tmpl in PAGE.items():
        for line in (RAW / f'{party}.txt').read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            m = re.match(r'^(\S*\|[^|]*\|\S+)\s+(\S+)\s*(.*)$', line.strip())
            key, slug, rest = m.group(1), m.group(2), m.group(3).split()
            if not key.startswith('vic-'):
                key = 'vic-' + key
            L = links.setdefault(key, {})
            if slug != '-' or '{}' not in tmpl:
                L['party'] = tmpl.format(slug)
            for kv in rest:
                k, v = kv.split('=', 1)
                if k == 'htv':
                    htv[key] = 'https://vicliberal.org.au' + v
                elif k in KIND:
                    L[KIND[k]] = url(v)
    # AJP pages and independent campaign sites, matched by hand (see raw/links/ajp_ind.txt)
    extra = {
        'vic-benambra|fuery|mike': {'party': 'mike-fuery'}, 'vic-broadmeadows|unicomb|rachel': {'party': 'rachel-unicomb'},
        'vic-brunswick|rose|india': {'party': 'india-rose'}, 'vic-bundoora|nicolosi|chloe': {'party': 'chloe-nicolosi'},
        'vic-carrum|moore|carolyn': {'party': 'carolyn-moore'}, 'vic-eildon|bond|chloe': {'party': 'chloe-bond'},
        'vic-eureka|morrison|wendy': {'party': 'wendy-morrison'}, 'vic-euroa|kelly|karina': {'party': 'karina-kelly'},
        'vic-evelyn|heald|jan': {'party': 'jan-heald'}, 'vic-frankston|harman|julie': {'party': 'julie-harman'},
        'vic-greenvale|furina|rosanna': {'party': 'rosanna-furina'}, 'vic-hastings|coulson|chloe': {'party': 'chloe-coulson'},
        'vic-kororoit|kandpal|vasundhara': {'party': 'vasundhara-kandpal'}, 'vic-macedon|korinfsky|natalie': {'party': 'natalie-korinfsky'},
        'vic-melbourne|jones|naomi': {'party': 'naomi-jones'}, 'vic-melton|adin-james|fiona': {'party': 'fiona-adinjames'},
        'vic-mill-park|levens|eve': {'party': 'eve-levens'}, 'vic-monbulk|wormald|alyssa': {'party': 'alyssa-wormald'},
        'vic-niddrie|haselgrove|salomae': {'party': 'salomae-haselgrove'}, "vic-prahran|o'neill|g.": {'party': 'daniel-oneill'},
        'vic-tarneit|rahn|maurita': {'party': 'maurita-rahn'}, 'vic-wendouree|collins|melissa': {'party': 'Melissa-Collins'},
        'vic-yan-yean|okatan|sinan': {'party': 'sinan-okatan'}, 'vic-murray-plains|collard|peita': {'party': 'petia-collard'},
    }
    for k, v in extra.items():
        links.setdefault(k, {})['party'] = 'https://vic.animaljusticeparty.org/' + v['party']
    ind = {
        'vic-albert-park|dragwidge|georgie': 'georgie4albertpark.com.au', 'vic-ashwood|joshi|hitendra': 'joshi4ashwood.au',
        'vic-bayswater|clarke|mathew': 'mathewclarke.com.au', 'vic-box-hill|cheung|heena': 'heena4boxhill.com.au',
        'vic-bundoora|murphy-webster|melissa': 'melissamurphywebster.com.au', 'vic-frankston|abraham|chrysten': 'chrysten4fkn.com',
        'vic-malvern|zigouras|christina': 'christinazigouras.com.au', 'vic-mornington|maher|adrian': 'adrianmaher.com.au',
        'vic-richmond|meyer|david': 'meyerforrichmond.au', 'vic-ivanhoe|kennedy|michelle': 'michellekennedyforivanhoe.com.au',
        'vic-macedon|seton|michael': 'michael4macedon.com.au', 'vic-macedon|bonanno|dom': 'domformacedon.com.au',
        'vic-williamstown|briffa|tony': 'briffaindependent.com.au', 'vic-brunswick|yuan|melissa': 'melformerribek.vote',
        'vic-melbourne|tuckfield|rowan': 'rowantuckfield.vote', 'vic-footscray|marsh|jess': 'jessmarsh.com.au',
        'vic-clarinda|white|caroline': 'votecaroline.com', 'vic-bulleen|rublee|greg': 'gregrubleeforbulleen.com',
    }
    for k, v in ind.items():
        links.setdefault(k, {})['website'] = url(v)
    links.setdefault('vic-essendon|adams|ava', {})['facebook'] = url('facebook.com/AvaForEssendon')
    out = {'updated': '2026-11-10',
           'note': "Official campaign and public-figure accounts only: links a party publishes on the candidate's own page, or a campaign site cited for the candidate. Key: contest_id|surname|first given name, lower case.",
           'links': dict(sorted(links.items())), 'htv_pending': dict(sorted(htv.items()))}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')))
    n_social = sum(1 for L in links.values() if set(L) - {'party'})
    print(f'{len(links)} candidates with links ({n_social} with a site or social account), {len(htv)} Liberal HTV slots -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
