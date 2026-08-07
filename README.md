# vrating

The rating you would have if every virtual round you have sat had counted. Codeforces and
AtCoder.

Type a handle. Every virtual participation is found automatically, replayed against the field
that actually sat that contest, and chained — each round scored against the rating the
previous one left you on. The result is a parallel career, drawn against your real one.

Enter several handles, comma separated, and the careers merge: alt accounts are one person.
A round sat on two accounts counts once, at its earliest sitting.

Every round lists the problems you left unsolved, linked, so the upsolving queue is right
there. Ones you attempted and failed are marked apart from ones you never opened.

"What should I upsolve?" goes further: across every round you have ever sat, it finds the
problems that most people *at your level* solved and you did not. See below for the method.

```bash
make dev                 # sets up on first run, starts the server, opens the page
make dev H=your_handle   # and warms that handle's contests in the background
```

That is the whole thing. Python 3.10+ is the only prerequisite; the first run builds a
virtualenv and installs numpy, and everything after starts in a second. `./run.sh` does the
same if you would rather not use make.

| | |
|---|---|
| `make dev` | start it |
| `make test` | the offline tests |
| `make test-all` | including the network-bound ones |
| `make warm H=handle` | warm a handle's contests without starting the server |
| `make clean` | drop the cache — it all re-fetches |

Warming is optional: the cache fills itself as you use the app. Passing a handle just moves
the waiting off your first page load.

Needs Python 3.10+. It runs without the prewarm, just slowly — that step is install, not
tuning. `GET /healthz` tells you where it stands:

```json
{"ok": true, "standings_cached": 1743, "prior_index": 1780, "warm": true}
```

## Why the numbers can be trusted

Every layer was validated against Codeforces' own published results before it was used.

| Layer | Check | Result |
|---|---|---|
| Rating formula | vs official deltas, Div. 1 fields 2023–2026 | **98–99% within ±1** |
| Score reconstruction | vs official standings, 90 real contestants, 4 contests | **100% exact** on points and penalty |
| Scoring rule fit | per-problem points, 7 rounds of 120/150/180 min | **100% exact** |
| Whole pipeline (CF) | replay a real career as if virtual, vs their actual curve | final drift **+4, −2, +3** on 3 accounts (9, 14 and 57 rounds) |
| Whole pipeline (AtCoder) | same replay, 4 users, 125 contests | **every rating exact**, every performance exact |

Run them with `pytest` (`-m "not gate"` to skip the network-bound ones). `tests/test_accuracy.py`
holds the error budgets as assertions, so a regression fails the build.

## Accuracy, honestly

Median absolute per-round error, measured against established accounts:

| Your rating | with archive | calibration only |
|---|---|---|
| 2000+ | **0** | 1 |
| 1600–2000 | **1** (p90 3) | 2 |
| 1200–1600 | **1** (p90 4) | 4 |
| below 1200 | **1** (p90 6) | 10–14 |

Errors chain forward, so the shape of the curve is firmer than any single number. Each row in
the log carries its own confidence, and a contest whose field can't be fully reconstructed is
marked `approximate` rather than quietly reported.

Two independent corrections get it there:

1. **Internal ratings.** A new Codeforces account *displays* rating 0 but is calculated at an
   internal 1400, closing the gap over six rounds via promotions of 500/350/250/150/100/50
   ([blog 77890](https://codeforces.com/blog/entry/77890)). The API reports the displayed
   value, so in a Div. 2 field a large slice of the seed input is wrong. The archive recovers
   the real one. Codeforces introduced this scheme at round 1360 (2020-05-24, dated from the
   archive itself); before it accounts simply started at 1500. Both eras are handled.
2. **Calibration.** Codeforces publishes every participant's real delta, so the residual
   against ours is observable. Fitting it per contest absorbs whatever the first correction
   missed.

## Layout

```
vrating/
  rating/     pure math, no I/O — cf.py, ac.py, scoring.py
  sources/    Codeforces API client, columnar cache, rating archive
  career/     contest preparation, calibration, the chaining engine
  web/        stdlib server + single page
```

`rating/` does no I/O, which is what makes the golden tests cheap to run.

## Speed

- Seed computation is an FFT convolution; the binary search is vectorized across the whole
  field. Full-field deltas for a 21k-participant contest: **1400× faster** than the
  straightforward loop (8.0 s → 5.7 ms).
- A single contestant inserted into a prepared contest: **0.08 ms**.
- A cached 17-round career: **2.6 s**, of which 0.9 s is the one unavoidable `user.status` call.
- **The two per-user calls happen in the browser, not on the server.** Codeforces serves
  `user.status` and `user.rating` with `Access-Control-Allow-Origin: *`, so the page fetches
  them itself — in parallel, and against the visitor's own rate-limit budget instead of this
  server's shared one. Those two calls were 3.5 s of a 3.7 s warm replay; server time is now
  **0.27 s**. The page POSTs the filtered result (~250 KB) and streams the reply back.
- Cold cache is network-bound at the API's ~1 req/s. Results stream as they land instead of
  blocking.
- **Contest preparation runs in parallel, the chain stays sequential.** Round *n* needs the
  rating round *n-1* left you on, so the chaining cannot be parallelised — but preparing each
  round's field is independent, and numpy releases the GIL for the FFT and the vectorized
  search. Measured 2.6x on four threads, 3.9x end to end. Results still stream in order: the
  pool outlives the loop, because exiting a `with ThreadPoolExecutor(...)` waits for every
  future and would turn the stream back into a batch. There is a test for that.
- The prior-contest index is precomputed per contest, so preparation stays ~30 ms.
- **Failed standings fetches are tombstoned.** Gym rounds have no rated field and the API
  refuses their standings; without remembering that, every upsolve scan re-attempted ~22
  doomed requests at one per second. That alone was 22 s of a 30 s scan.
- The upsolve scan reuses the data the replay already pulled, so opening it costs no network
  at all: **30 s → 2.2 s**, zero API calls.
- Rating-change data is cached columnar, not as the API's row JSON, which repeats the contest
  name on every row: **1.5 GB → 123 MB**.

## AtCoder

AtCoder publishes every finished round's full rank-to-performance curve, so a rank converts to
a performance essentially exactly (leave-one-out error: 0.3 rating points). The rating is then
AtCoder's own formula over your virtual performance history.

The one thing it cannot do is read your placing: `standings/json` redirects to a login. So the
app finds the rounds you have solved problems from *after* they finished — that is what a
virtual sitting looks like from outside — and you type the rank. Everything else is automatic.

Two details that break naive implementations of AtCoder's rating, both settled from data:
APerf is a weighted average in `2^(perf/800)` space rather than linear, and the rating uses
the *capped* `Performance` field, not `InnerPerformance`.

## What should I upsolve?

For each problem, the field is a labelled sample: every rated participant's rating, and
whether they solved it. Bin by rating, take the solve fraction per bin, force the curve
non-decreasing (isotonic regression — a higher rating cannot make you *less* likely to solve
something), and read it off. That gives a calibrated, quotable number: *86% of people at your
level solved this; you did not.*

**Not a rank neighbourhood.** Comparing against people who placed within ±300 of you is the
intuitive version, but rank mixes skill with that day's form — a bad round seats you among
weaker people, lowering the bar exactly when you want it held. It also discards the field:
±300 of a 20,000-person contest estimates the same quantity from 3% of the data. Measured
peer samples here run 600–2,500.

**Read at the rating you held then, not today's.** The curve comes from one contest's field,
so its rating axis is that contest's, at that date. Codeforces ratings drift — measurably
150–190 points between 2023 and 2026 alone — so reading a 2018 curve at your 2026 rating
compares across a moving axis. Everything stays contemporaneous. Whether a problem is worth
your time *now* is a separate question on a separate axis, answered by Codeforces' own global
problem difficulty, reported alongside rather than folded into one score.

**Ranked by how surprising the miss was.** Failing a problem with solve probability p carries
surprisal −log(1−p), which is monotone in p — so ordering by p *is* ordering by surprise.

**Problems you have since upsolved are excluded.** On a real account that removed 878 of them;
without it the list is unusable.

Tags are aggregated too, because a tag you keep missing says more than any single problem.

## Reading shelf

The third tab is a library of ~130 competitive-programming blogs, pulled from
[TAOGenna/competitive-programming](https://github.com/TAOGenna/competitive-programming/tree/master/Interesting_blogs).

That list is titles and links only, so rather than invent descriptions the cards use
Codeforces' own `blogEntry.view`: the author's real title, their handle coloured by rank, the
tags, the year, and an excerpt taken from the post itself. 117 of the 132 links live on
Codeforces; the rest keep the list's own text and name their host.

Cards sort by **community score**, which is the only measurable reading of "most interesting"
— the top of the shelf is the most-upvoted post in the list, not an opinion. Filter by topic,
search titles and authors and tags, and mark things read (kept in your browser, mirroring the
checkboxes in the source list).

First open fetches the metadata at ~1 req/s and then caches it — about two minutes once, 476 KB.

## Configuration

| variable | |
|---|---|
| `VRATING_PORT` | default 8770; the launcher takes the next free port if it is busy |
| `VRATING_DATA` | where the cache lives, default `./data` |
| `VRATING_WORKERS` | threads for contest preparation, default 4 — 1 works, just slower |
| `VRATING_CACHED_CONTESTS` | in-memory prepared contests, default 256 (~200 MB) |

Warming the whole archive is possible (`make warm` with no handle) but only worth it if you
are serving other people: ~1780 contests, ~35 min, ~16 GB down, ~600 MB kept. For yourself,
`make warm H=your_handle` fetches the couple of hundred rounds you have actually sat.

## Known gaps

- AtCoder ranks are entered by hand; there is no public standings source to derive them from.
- Contests before ~2015 used a different rating system and are not modelled.
- Participants disqualified mid-contest (every submission `SKIPPED`) are not modelled. This
  cannot affect a virtual participant and never changes points or penalty.
- Team participations are excluded from fields.
