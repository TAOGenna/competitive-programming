# Virtual rating for Codeforces / AtCoder virtual contests

**Question:** if I do a virtual contest today on a contest from 2023, what rating would I have if I'd competed live at that moment — and can that be computed faithfully?

**Verdict: yes, on both platforms, from public data, with verified accuracy.** I implemented both rating systems from scratch and checked them against each platform's own published results. AtCoder is effectively exact. Codeforces is exact for established-account fields and has one known bias in newbie-heavy divisions, with a concrete fix.

All claims below were checked by running code against live APIs on 2026-08-06. Working scripts: `virtual-rating/`.

---

## 1. Codeforces

### Data availability (all verified live, no auth)

| Endpoint | Gives you | Verified |
|---|---|---|
| `contest.ratingChanges?contestId=N` | the **exact rated field**: handle, rank, oldRating, newRating | 9581 rows for contest 1900 |
| `contest.standings?contestId=N` | every contestant's points + penalty per problem | 6.6 MB, 9581 rows |
| `contest.status?contestId=N&handle=H` | **your own** submissions in that contest incl. `participantType: VIRTUAL`, `relativeTimeSeconds`, verdict | returns 6 submissions for a real participant |
| `contest.list` | 2133 finished contests | — |

Two constraints found by probing:

- `contest.standings` rejects **any** extra parameter for non-admins (`showUnofficial`, `handles`, `from`, `count`) — the API replies: *"Non-gym contest standings for non-admin users are available only via anonymous GET requests with no extra parameters."* So you cannot pull virtual rows from the standings API. You don't need to: `contest.status` with your handle gives your virtual submissions, and you reconstruct your own points/penalty from the problem point values in `contest.standings`.
- Rate limit is ~1 req/sec. A full archive crawl of `contest.ratingChanges` across all 2133 contests takes ~37 minutes, once.

`codeforces.com` HTML pages are behind Cloudflare (403 to scripted fetches). The `/api/` endpoints are not. Design around the API only.

### The algorithm

Mirzayanov published the system in [blog entry 20762](https://codeforces.com/blog/entry/20762): compute each participant's *seed* (expected rank = 1 + Σ Elo win probabilities of the rest), take `m = sqrt(rank × seed)`, binary-search the rating `R` whose seed equals `m`, set `delta = (R − r)/2`, then apply two zero-sum adjustments.

**The published version does not match production.** My faithful implementation of the 2015 blog scored 0.1% exact on contest 1900. The corrected variant is in [Carrot](https://github.com/meooow25/carrot) (`carrot/src/background/predict.js`), itself adapted from [TLE](https://github.com/cheran-senthil/TLE)'s `rating_calculator.py`, which came from a Mirzayanov submission. The differences that actually matter:

1. Tied participants are assigned the **worst** rank in the tie group, not the best (and ties are recomputed from points+penalty, not read from the API's displayed rank).
2. `trunc` toward zero, not `floor`, at every rounding step.
3. The binary search runs over `[2, 6000]` and returns `lo − 1`.
4. Ranks are recomputed **among the rated subset only**.
5. Unrated participants get an effective rating of 1400.

### Validation results

Running my port against the platform's own `newRating − oldRating`:

| Contest | Field | Exact | Within ±1 | mean abs err |
|---|---|---|---|---|
| **1889** (Div. 1) | 856 rated | **74.5%** | **99.0%** | **0.68** |
| 1900 (Div. 2) | 9581 rated | 0% | 0.06% | 51.2 |
| 2001 (Div. 2) | 21175 rated | 0.25% | 2.6% | 55.4 |
| 2 (year 2010) | 122 rated | 0% | 2.5% | 18.6 |

Div. 1 is essentially solved. The Div. 2 failure is not random — bucketing the signed error by old rating shows a clean monotone gradient:

```
oldRating     n    mean signed err (pred − actual)
        0   410              -171.5
      400   326              -140.0
      800  1739               -59.7
     1200  1546               -20.8
     1600   788                -8.6
     2000   135                -5.4
```

I sampled 70 handles from contest 1900 and pulled `user.rating` for each to count their prior rated contests. The error tracks contest count, not rating:

```
#prior rated contests    n   mean signed err
                    0   10          -179.6
                    1    4          -278.0
                    3    2          -130.0
                    5    3           -35.0
                   8+   44           -21.2
```

**Cause — confirmed empirically, see §7.** Per [CF blog 77890](https://codeforces.com/blog/entry/77890) (2020), a new account **displays** rating 0 but Codeforces uses **1400 internally** when computing rating changes. The gap is closed by promotions of +500, +350, +250, +150, +100, +50 over the first six rated contests (summing to exactly 1400); after six contests displayed = internal. So:

```
internal_rating = displayed_rating + (1400 − sum of promotions already granted)
k=0: +1400   k=1: +900   k=2: +550   k=3: +300   k=4: +150   k=5: +50   k≥6: 0
```

The API's `oldRating` is the *displayed* value. In a Div. 2/3/4 field a large fraction of the seed input is therefore wrong, which biases **everyone's** delta, established accounts included.

**Fix:** crawl `contest.ratingChanges` for all 2133 contests once (~37 min at the rate limit). That archive gives every handle's exact prior-rated-contest count at any point in history, so you can reconstruct internal ratings for the whole field. See §7 for verification of the k=0 case.

**Why this matters less than it looks for your use case:** you are one established account inserted into a historical field. The distribution bias is a shared offset you correct once per contest. You are not affected by the promotions themselves.

### Getting your own virtual rank

Codeforces' native virtual participation already applies live scoring (point decay, −50 per rejected attempt, system tests). Pipeline:

1. `contest.status?contestId=N&handle=you` → your VIRTUAL submissions with `relativeTimeSeconds`.
2. `contest.standings?contestId=N` → problem point values, and every original contestant's `(points, penalty)`.
3. Recompute your points/penalty, insert yourself into the rated field, re-rank by `(-points, penalty)`.
4. Run the rating calculator with your *virtual* rating as your old rating.

---

## 2. AtCoder

This one is cleaner than Codeforces.

### Data availability (verified live, no auth)

| Endpoint | Gives you |
|---|---|
| `atcoder.jp/contests/{id}/results/json` | **every participant**: Place, IsRated, OldRating, NewRating, Performance, Competitions. 8155 rows for abc300 |
| `atcoder.jp/users/{user}/history/json` | your full per-contest history incl. `Performance` **and** `InnerPerformance` |
| `data.ac-predictor.com/results/{id}.json` | mirror of the above |
| `data.ac-predictor.com/aperfs/{id}.json` | every participant's APerf (5623 entries for abc300) — what [ac-predictor](https://github.com/key-moon/ac-predictor) uses for live prediction |

**One gap:** `atcoder.jp/contests/{id}/standings/json` 302-redirects to `/login`. Scores and submission times are auth-gated; final placements and performances are not. You'll need your own session cookie to read standings, or you take your rank from the virtual-participation UI, or you use [AtCoder Problems](https://kenkoooo.com/atcoder)' public submission API (verified 200) to rebuild standings yourself.

### The algorithm — and the two things that break naive implementations

Rating from a performance history is:

```
APerf   = 800 · log2( Σ 2^(perf_i/800) · 0.9^i  /  Σ 0.9^i )     # i = 1 is most recent
f(n)    = 1200 · ( F(n) − F(∞) ) / ( F(1) − F(∞) ),  F(k) = √(Σ 0.81^i) / (Σ 0.9^i)
Rating  = APerf − f(n)
if Rating ≤ 0:  Rating = 400 / exp((400 − Rating)/400)           # positivize
```

Two traps, both of which I hit and had to diagnose from the data:

1. **APerf is a weighted average in `2^(perf/800)` space, not linear space.** Using a linear weighted mean gets `n = 1` exactly right and then drifts — 4.5% exact overall, errors up to 300. Switching to log space took it to 96.4%.
2. **The rating uses the *capped* `Performance`, not `InnerPerformance`.** ABC300 is rated for <2000 and every performance is capped at 2400; `InnerPerformance` for those rows runs to 3415. The rating calculation uses 2400. Using InnerPerformance produced systematic errors of 300–500 on strong ABC performers.

### Validation results

17 users sampled across the whole rating spectrum (0–2400) plus tourist and chokudai, replaying every rated contest in their history and predicting each `NewRating`:

```
OVERALL 421 predictions | exact 96.4% | within ±1 96.9% | max abs err 123
```

tourist (71 contests), chokudai (37), purslane_ma (7), urnayuw (10), 0x4c (30) — **100% exact, every contest**. The residual ~4% is concentrated in a few users and is most likely historical rated-range changes (the ABC rated ceiling has moved over the years, changing the performance cap) rather than a formula error. Not chased down.

### Rank → performance is essentially free

You don't need to re-run the Elo integral. `results/json` gives you the full (Place, Performance) curve for that contest. Leave-one-out interpolation across abc300:

```
n=176 | mean abs err 0.3 | median 0.0 | p95 0.7 | max 2.6   (rating points)
```

So: get your virtual rank → interpolate → that is your performance, already correctly capped, because the cap is a property of the contest. Append it to your virtual performance history, rerun the rating formula. Done.

Use `aperfs/{id}.json` only if you need performance *above* the cap or for a contest with sparse results.

---

## 3. Prior art

Worth knowing before building, none of it a complete answer:

- **[Codeforces Anytime](https://codeforces-anytime.firebaseapp.com/)** ([source](https://github.com/sono8stream/codeforces-anytime)) — the closest existing thing: plots a rating curve built purely from CF virtual contests. Firebase app, 156 commits, README documents setup only, no stated algorithm or caveats.
- **[cfviz virtual rating change calculator](https://cfviz.netlify.app/virtual-rating-change)** — single-shot: you type contest id + points + penalty, it returns expected rank and delta. No history, no chained rating.
- **[Carrot](https://github.com/meooow25/carrot)** — the reference-quality CF delta implementation. Live and finished contests only; README does not mention virtual support.
- **[CF Rating Predictor](https://codeforces.com/blog/entry/149938)** — scans your submission history for virtual participations and projects a rating trajectory. Could not read the post (Cloudflare); overlaps heavily with the CF half of this idea.
- **[EverydayAtCoder](https://github.com/KATO-Hiro/EverydayAtCoder)** — explicitly "Codeforces Anytime for AtCoder". 1 star, backend and demo both "Coming soon". **The AtCoder side is effectively unbuilt.**
- **[ac-predictor](https://github.com/key-moon/ac-predictor)** — live AtCoder performance prediction, not virtual.

The gap: nothing does both platforms, and nothing maintains a persistent *virtual rating* that chains contest to contest with the newbie-effective-rating correction.

---

## 4. Design sketch

The core loop is the same on both platforms:

```
virtual_rating ← your real rating (or 1400 / 0) at the moment you start
for each virtual contest, in the order YOU did them:
    rank    ← insert your result into that contest's historical field
    delta   ← platform rating function(virtual_rating, rank, historical field)
    virtual_rating += delta          # AtCoder: recompute from perf history instead
```

The one real design decision: **your virtual rating, not your real rating, is the input.** That's what makes it a genuine parallel career rather than a series of independent "what-if" deltas — and it's what neither cfviz nor Carrot does.

Notes:

- Codeforces needs a local mirror of `contest.ratingChanges` for all contests anyway (rate limits, and the effective-rating fix). Build it once, refresh incrementally.
- AtCoder needs no crawl for the rating math — `results/json` per contest is enough. It needs auth only for standings.
- Replicate eligibility rules or the number is fiction: AtCoder ABC is rated only below 2000, ARC below 2800; Codeforces Div. 2 is rated only below 2100. If your virtual rating leaves the band, the contest should be unrated for you.

## 5. Silent failure modes

Things that would produce a plausible-looking wrong number:

- **Old contests.** Contest 2 (2010) matched 0% — the current CF formula did not exist then. Pick a cutoff; anything before roughly 2015 is a different system. AtCoder's system also changed around 2016.
- **The Div. 2 seed bias.** Uncorrected, this silently costs a 2100-rated user ~40 points per contest, always in the same direction, so a virtual career compounds the error instead of averaging it out.
- **Div. 1 + Div. 2 combined rounds** are rated per division. Feeding a combined field into one calculation is wrong and will look fine.
- **AtCoder performance cap drift.** Rated ranges have changed over the years; a hardcoded 2400 cap applied to an older ABC gives wrong performances that still look reasonable.
- **Rank inflation from unrated participants.** On both platforms unrated entrants occupy ranks. CF computes among the rated subset only; if you rank yourself against the full standings your rank is too high.
- **Contest 2003 dropped 5382 of 19890 rated participants** when joining standings to ratingChanges by handle. I did not diagnose this. Any join like that needs a hard assertion, not a silent inner join.

## 6. Is there a newer Codeforces formula? (checked 2026-08-06)

**No. The core delta formula has not changed in at least three years.** I ran the Carrot/TLE algorithm against Div. 1 fields (where the new-account distortion is negligible) spanning 2023-07 → 2026-07:

| Contest | Date | rated | exact | within ±1 | mean abs err |
|---|---|---|---|---|---|
| 2249 Round 1112 (Div. 1) | 2026-07-26 | 676 | 72.2% | **98.7%** | 0.66 |
| 2239 Round 1105 (Div. 1) | 2026-06-27 | 708 | 14.0% | 90.3% | 1.23 |
| 2201 Round 1082 (Div. 1) | 2026-02-23 | 813 | 62.1% | **98.8%** | 1.49 |
| 2196 Round 1079 (Div. 1) | 2026-02-11 | 821 | 87.2% | **99.3%** | 0.41 |
| 2174 Round 1069 (Div. 1) | 2025-12-06 | 711 | 68.1% | 98.0% | 1.08 |
| 2159 Round 1058 (Div. 1) | 2025-10-12 | 872 | 65.6% | 98.5% | 1.05 |
| 1889 Round 906 (Div. 1) | 2023-10-28 | 856 | 74.5% | **98.9%** | 0.68 |
| 1852 Round 887 (Div. 1) | 2023-07-23 | 746 | 75.3% | **99.1%** | 0.66 |

Flat across the whole span. A formula change would show as a break; there isn't one.

I also checked whether the *new-account display convention* changed — it hasn't. Across one Div. 2 contest per quarter from 2024-03 to 2026-08, the minimum displayed `oldRating` is 0 in every contest and 600–2300 participants per round have displayed rating exactly 0.

### The new-account mechanism, verified

First-time participants are identifiable: displayed `oldRating == 0` means exactly k=0, so internal = 1400. Testing that:

```
                              first-timers   their mean signed err
contest 1900 (2023)  n=405    internal delta as-is:   -521.3
                              internal delta + 500:    -21.3
contest 2001 (2024)  n=1304   internal delta as-is:   -519.0
                              internal delta + 500:    -19.0
contest 2040 (2024)  n=760    internal delta as-is:   -524.6
                              internal delta + 500:    -24.6
```

The +500 first-contest promotion is confirmed exactly, consistently across three contests and two years. Applying just this partial fix (eff=1400 where displayed==0) halves the bias for established users:

```
                        veterans (rating ≥1600), mean signed error
contest 2040:   raw -15.8   →   with fix  -7.7
contest 2001:   raw  -5.4   →   with fix  -3.3   (within±1: 19.7% → 28.7%)
```

The residual −3 to −8 is the k=1..5 cohort, which is *not* identifiable from the rating value alone and needs the full archive crawl.

### What the community is actually discussing in 2026

This is probably what prompted the "new formula" suspicion, but none of it is a formula change:

- **[Inconsistencies in Codeforces rating system](https://codeforces.com/blog/entry/154911)** (2026-07-03) — someone implemented the published formula, compared against actual changes, and found "a very significant bias," which they link to the percentage of new accounts in a contest. **That is precisely the effect measured above**, from the same root cause. Independent confirmation that the published formula is still the live one, and that the missing piece is the new-account correction — not a new formula.
- **[Codeforces rating deflation](https://codeforces.com/blog/entry/154620)** — community analysis claiming ~150–190 points of deflation for legitimate participants comparing Jan 2025–Jun 2026 against Jan 2023–Jun 2024. An emergent effect (field composition in the AI era), not an algorithm change.
- **[About Recent Rating Change](https://codeforces.com/blog/entry/147457)** — a temporary rollback of rating changes, later restored. Operational, not a formula change.

### Deflation is partly structural — relevant to a long virtual career

The published algorithm has a built-in downward drift, and my implementation reproduces it: the first adjustment is `inc = trunc(−Σδ/n) − 1` (the `−1` removes a point per participant per contest), and the second is clamped to `[−10, 0]` so it can only ever subtract. Measuring actual mean delta across 237 crawled contests:

- Div. 1 / small fields behave as designed: mean delta ≈ 0 (contest 1965: +0.03, 2196: +0.38, 2129: −2.16).
- Large Div. 2/3/4 fields show mean delta **+40 to +100**. That is *not* rating being created among established users — it is the +500-style promotions to first-timers inflating the sum of displayed deltas.

For a virtual career this matters: the drift is small per contest but one-directional, so it compounds over dozens of virtual contests rather than averaging out.

### Additional prior art found

**[How to get the Virtual Rating Changes](https://codeforces.com/blog/entry/145127)** — a CF blog post on exactly this problem. Not readable through Cloudflare; worth opening in a browser before building.

## 7. What is verified vs. not

Verified by running code:
- Both APIs, all endpoints and constraints in the tables above.
- CF algorithm reproduces official deltas at 99% within ±1 on a Div. 1 field.
- CF error correlates with prior-contest count, not rating (n=70 sample).
- AtCoder rating formula reproduces official ratings at 96.4% exact / 100% for most users (421 predictions).
- AtCoder rank→performance interpolation accurate to <1 rating point.

- CF's core delta formula is unchanged 2023-07 → 2026-07 (8 Div. 1 contests, 98–99% within ±1 throughout).
- The +500 first-contest promotion, exactly, on 3 contests across 2 years (bias −521 → −21).
- Substituting effective rating 1400 for first-timers halves the residual bias for established users.
- Structural deflation: mean delta ≈ 0 in Div. 1, +40..+100 in large fields (237 crawled contests).

- **The full promotion schedule.** The archive crawl finished (2133 contests; 1779 rated, 354
  genuinely unrated — the fetch failures turned out to be unrated contests returning HTTP 400,
  confirmed by a retry pass that fixed zero of them). Indexing 960,493 handles chronologically
  gives every participant's prior-contest count, and applying the full schedule
  (500/350/250/150/100/50) as internal-rating offsets drops median delta error to **1.0 in
  every rating band** — from 9.5–13.9 below 1200 and 3.7–4.0 at 1200–1600. That the whole
  schedule lands this cleanly confirms all six values, not just k=0.

Not verified:
- The cause of the remaining ~4% AtCoder mismatches.
- Contest 2003's 5382 unmatched rated participants.
