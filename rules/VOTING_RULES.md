# Voting rules: the one source

Anything the Atlas publishes that tells people how to fill in a ballot (cards, captions, replies, site text) copies its wording from `rules/voting_rules.json`. Nothing is written from memory, by people or by Claude.

## Victoria, 2026 state election (checked 22 Nov 2026 against the VEC)

Source: https://www.vec.vic.gov.au/voting/learn-to-vote/how-to-fill-out-state-ballot-papers

- **Lower house (Legislative Assembly):** number every box, in the order of your choice.
- **Upper house (Legislative Council):** number at least **5** boxes above the line, **or** at least **5** boxes below the line. Not both.
- A single 1 above the line is **informal** in 2026. That was the 2022 rule, under group voting tickets, which have been abolished.

## Adding a new system

1. Add an entry to `voting_rules.json` with the official source URL, the date checked, and `verified: true` only once someone has read the official page.
2. Give it a `say` line: the exact words cards and captions will use.
3. Build scripts load the entry with `social/posts/_build/rules.py` and call `rules.check(text)` on any card or caption text, which fails the build on outdated wording.

## History

- 22 Nov 2026: the democracy sausage card (s03) went out saying "at least 1 above the line" (the 2022 rule). Corrected card: s03b. This file exists so that doesn't happen again.

## Timeline and counting (vic2026)
Verified 22 Nov 2026 against the VEC's 2026 state election pages. See `vic2026_timeline_count.json` for dates (postal applications close 6 pm Wed 25 Nov; early voting closes 6 pm Fri 27 Nov; election day 8 am to 6 pm Sat 28 Nov; postal votes by mail admitted until 6 pm Fri 4 Dec) and the four counting stages. Use that file, not memory, for any post about deadlines or the count.
