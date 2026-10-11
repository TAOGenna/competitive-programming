# contests

Contest folders and sample runs for Codeforces and AtCoder.

| Where | Command | What it does |
|---|---|---|
| `contests/` | `make cf2268` | Codeforces contest → `cf2268/A.cpp …` (copies of `code.cpp`) with samples in `cf2268/tests/A/1.in`, `1.out` |
| `contests/` | `make abc370` | Same for AtCoder (any AtCoder contest id) |
| vim, on a contest file | `<Space>t` | Saves, compiles, runs every sample in a split beside the code |
| vim | `<Space>q` | Closes that split |
| vim, on a contest file | `<Space>c` | Copies the whole file to the clipboard, ready to paste into the submit box |
| contest folder | `make A` | Same run from the shell |
| anywhere here | `make code.cpp` | Plain build to `./code`, no samples |

## Reading the results

Each sample gets a verdict and its time:

| Verdict | Meaning |
|---|---|
| `AC` | Output matches (whitespace is ignored, real numbers may differ by 1e-6) |
| `WA` | Wrong answer: shows the input, then expected and your output side by side |
| `RE` | Crashed: shows the signal or exit code, plus stderr |
| `TLE` | Killed after the time limit (5s by default) |
| `CE` | Does not compile: shows g++'s message |
| `??` | Ran, but the test has no `.out` to compare with |

Sample runs compile with `-DDEBUG`, so `trace()` output shows up under stderr.

## Good to know

- **Your own tests:** drop `tests/A/anything.in` next to the samples. The `.out` is optional.
- **Re-running** `make cf2268` refreshes the samples and never overwrites a `.cpp` that already exists.
- **Time limit:** `make TL=2 A` for one run, or change `TL` in the `Makefile`.
- **Flags:** `CXX`, `CXXFLAGS` and `TESTFLAGS` live in the `Makefile`. Sample runs get a 256MB stack, like Codeforces.
- **Template:** new contest files are copies of `code.cpp`, so edit that to change the template.
- **Safari fallback:** if a site refuses the direct fetch, the page is opened in Safari and read from there. This is the path for a live AtCoder contest, so be logged in to AtCoder in Safari.
- **Contest not started:** the command says how long is left. Run it again once it starts.
- **Vim keys** are defined in `cp.vim`, loaded by one line at the end of `~/.vimrc`:
  `silent! source <path to this repo>/contests/cp.vim`. They only apply to `.cpp` files under this folder.
