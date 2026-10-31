# Putting the atlas on GitHub (once) and publishing it

Repository: https://github.com/simonwindley/vic-booth-atlas (public; GitHub Pages is free for public repos).

## 1. Create the repository (on github.com, once)

New repository → name `vic-booth-atlas`, Public, **no** README/.gitignore/licence (the folder already has them) → Create.

## 2. First push (Terminal on the Mac, once)

    cd ~/Documents/"Election Analyser"
    git init -b main
    git add .
    git commit -m "Victoria Booth Atlas: data pipeline, site, election-night feed"
    git remote add origin https://github.com/simonwindley/vic-booth-atlas.git
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

    https://simonwindley.github.io/vic-booth-atlas/

Anyone with that link gets the full atlas, basemap included. Check the Actions tab if it does not appear.

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
