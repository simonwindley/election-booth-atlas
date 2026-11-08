# Putting the atlas on GitHub (once) and publishing it

## Renaming the repository (done once, November 2026)

The project started as "Victoria Booth Atlas" (`vic-booth-atlas`). To rename on GitHub: Repository → Settings →
General → Repository name → `election-booth-atlas` → Rename. GitHub redirects the old address, but the Pages
site moves to `https://simonwindley.github.io/election-booth-atlas/`, so update the remote on the Mac:

    cd ~/Documents/"Election Analyser" && git remote set-url origin https://github.com/simonwindley/election-booth-atlas.git


Repository: https://github.com/simonwindley/election-booth-atlas (public; GitHub Pages is free for public repos).

## 1. Create the repository (on github.com, once)

New repository → name `election-booth-atlas`, Public, **no** README/.gitignore/licence (the folder already has them) → Create.

## 2. First push (Terminal on the Mac, once)

    cd ~/Documents/"Election Analyser"
    git init -b main
    git add .
    git commit -m "The Election Booth Atlas: data pipeline, site, election-night feed"
    git remote add origin https://github.com/simonwindley/election-booth-atlas.git
    git push -u origin main

`git push` asks for GitHub credentials the first time: use your username and a personal access token
(GitHub → Settings → Developer settings → Personal access tokens; "repo" scope), or run `gh auth login`
first if the GitHub CLI is installed. The `.gitignore` leaves out the 76 MB SQLite database, the parquet
bundle and the plain-JSON copy of the site data — all regenerable with the commands in README.md — so the
repository is about 170 MB.

## 3. Turn on Pages (on github.com, once)

Repository → Settings → Pages → "Build and deployment" → Source: **GitHub Actions**. The workflow in
`.github/workflows/pages.yml` then publishes the `site/` folder on every push that touches it. The first
run takes a minute or two; the address will be

    https://electionboothatlas.org/

(the old `https://simonwindley.github.io/election-booth-atlas/` address redirects there). Anyone with that link gets the
full atlas, basemap included. Check the Actions tab if it does not appear.

## The domains (Cloudflare, November 2026)

Both domains are registered at Cloudflare on the electionboothatlas@gmail.com account.

* **electionboothatlas.org** is the canonical address. DNS (all *DNS only*, grey cloud, so GitHub can issue the
  certificate): four `A` records for the apex to 185.199.108-111.153, four `AAAA` to 2606:50c0:8000-8003::153, and
  `CNAME www → simonwindley.github.io`. The `_github-pages-challenge-simonwindley` TXT record verifies the domain to the
  GitHub account (github.com → Settings → Pages → Verified domains), so no one else can point a Pages site at it.
  Repository → Settings → Pages → Custom domain is `electionboothatlas.org`, with Enforce HTTPS on. The Actions
  workflow takes the domain from that setting, so there is no CNAME file in `site/`.
* **electionboothatlas.com** redirects: placeholder proxied records (`A @ 192.0.2.1`, `CNAME www`) and a Redirect Rule
  sending every request, path and query string kept, to `https://electionboothatlas.org` with a 301.
* **Email**: Cloudflare Email Routing on both domains forwards `hello@` on both the .org and the .com to electionboothatlas@gmail.com (other addresses are dropped).
  Cloudflare only receives; to send as hello@, add it in Gmail → Settings → Accounts → "Send mail as" (smtp.gmail.com,
  port 587, a Google app password) and add `include:_spf.google.com` to the .org SPF record. `_dmarc` is `p=none`.
* Visit counts (GoatCounter) run on the github.io and electionboothatlas hosts only (see `site/build.py`).

## 4. Updating

From the Mac, after any change synced from Claude (or your own edits):

    git add -A && git commit -m "describe the change" && git push

## 5. Before the night

    python3 live/vec_daily.py --publish      # once a day from 4 November: roll, nominations, how-to-vote cards, statistics

## 6. Election night: live for everyone

Run the poller with `--publish`, which commits and pushes the feed after every cycle:

    python3 live/vec_live.py --base auto --loop 60 --publish

Pages redeploys in about a minute, so people with the link see new figures 2–8 minutes after the VEC
posts them; the page itself re-reads the feed every minute. Your own browser at http://localhost:8000/
(with `python3 -m http.server 8000` in `site/`) sees each cycle immediately.

`--publish` runs `git add site/data/live/latest.json site/data/live/status.json site/data/live/changes.json
&& git commit && git push`; pass `--publish-cmd "…"` to use something else (an rsync to another host, say).
