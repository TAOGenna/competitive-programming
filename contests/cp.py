#!/usr/bin/env python3
"""cp - contest folders and sample runs. Driven by the Makefile, stdlib only.

  make cf2268      Codeforces contest 2268  -> cf2268/A.cpp ... (copies of code.cpp)
  make abc370      AtCoder contest abc370   -> abc370/A.cpp ... (any AtCoder contest id works)
                   samples land in <contest>/tests/<P>/1.in, 1.out, 2.in ...
  make A           inside a contest folder: compile A.cpp and run it on tests/A/*.in
                   (in vim: <Space>t does the same after saving, <Space>q closes the result,
                   <Space>c copies the file to the clipboard for submitting)

Your own tests: drop tests/A/<name>.in next to the samples; <name>.out is optional.
Existing .cpp files are never overwritten, so re-running `make cf2268` is safe.
"""
import datetime, glob, gzip, html, json, os, re, resource, shlex, shutil, signal, subprocess, sys, tempfile, time
import unicodedata, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "cp-helper/1.0 (personal contest scaffolding script)"
TTY = sys.stdout.isatty() and "NO_COLOR" not in os.environ
W = max(44, min(shutil.get_terminal_size((80, 24)).columns - 4, 96))
GREEN, RED, YELLOW, MAGENTA, CYAN, DIM, BOLD = "32", "31", "33", "35", "36", "2", "1"
BADGE = {"AC": "30;42", "WA": "30;41", "RE": "30;45", "TLE": "30;43", "CE": "30;41", "??": "30;46"}


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if TTY else s


def width(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def rule(label=""):
    head = f"── {label} " if label else ""
    return "  " + c(DIM, head + "─" * (W - len(head)))


def say(*lines):
    for line in lines:
        print("  " + line, flush=True)


def header(left, right=""):
    print()
    left = fit(left, W - len(right) - 2).rstrip()
    say(c(BOLD, left) + " " * (W - width(left) - len(right)) + c(DIM, right))
    print(rule(), flush=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ---------------------------------------------------------------- fetching

def get(url):
    """Plain GET that says what it is. Returns (status, text); status 0 = network error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        r = e
    except OSError as e:
        return 0, str(e)
    raw = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        raw = gzip.decompress(raw)
    return r.getcode(), raw.decode("utf-8", "replace")


SAFARI = '''
on run argv
  set {u, needle, secs} to {item 1 of argv, item 2 of argv, (item 3 of argv) as integer}
  tell application "Safari"
    try
      tell front window
        set t to make new tab with properties {URL:u}
        set current tab to t
      end tell
    on error
      make new document with properties {URL:u}
      set t to current tab of front window
    end try
    repeat with i from 1 to secs * 2
      delay 0.5
      try
        set s to source of t
        if s contains needle and s contains "</html>" then return s -- the source grows while the page loads
      end try
      if i is 16 then activate -- still nothing after 8s: maybe a check that wants a click
    end repeat
  end tell
  error "timeout"
end run
'''


def safari(url, needle, secs):
    """Open url in the user's own Safari (their session, their cookies) and return the page
    source once it contains needle. Returns (source, "") or (None, why)."""
    try:
        p = subprocess.run(["osascript", "-e", SAFARI, url, needle, str(secs)], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=secs + 150)
    except subprocess.TimeoutExpired:
        return None, "Safari never answered"
    if p.returncode == 0:
        return p.stdout, ""
    if "-1743" in p.stderr or "-1712" in p.stderr or "Not authorized" in p.stderr:
        return None, ("macOS has not allowed this terminal to control Safari. Click Allow on the prompt, or enable "
                      "it in System Settings > Privacy & Security > Automation > (your terminal) > Safari")
    if "timeout" in p.stderr:
        return None, "the page in Safari never showed the problems (a check waiting for a click? not logged in?)"
    return None, p.stderr.strip()


# ---------------------------------------------------------------- parsing

def pre_text(inner):
    """Inner HTML of a sample <pre> -> the text a contestant would copy."""
    s = re.sub(r"<br\s*/?>|</div>", "\n", inner)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return s.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"


def parse_codeforces(page):
    """/contest/<id>/problems -> [(index, name, [(input, output), ...])]"""
    parts = re.split(r'problemindex="([^"]+)"', page)
    problems = []
    for idx, body in zip(parts[1::2], parts[2::2]):
        name = re.search(r'<div class="title">\s*(.*?)\s*</div>', body, re.S)
        name = html.unescape(name.group(1)).partition(". ")[2] if name else ""
        ins = re.findall(r'<div class="input">.*?<pre[^>]*>(.*?)</pre>', body, re.S)
        outs = re.findall(r'<div class="output">.*?<pre[^>]*>(.*?)</pre>', body, re.S)
        problems.append((idx, name, [(pre_text(i), pre_text(o)) for i, o in zip(ins, outs)]))
    return problems


def parse_atcoder(page):
    """/contests/<id>/tasks_print -> [(index, name, [(input, output), ...])]"""
    parts = re.split(r'<span class="h2">\s*(.*?)\s*</span>', page, flags=re.S)
    problems = []
    for title, body in zip(parts[1::2], parts[2::2]):
        idx, _, name = html.unescape(re.sub(r"<[^>]+>", "", title)).partition(" - ")
        en = body.split('<span class="lang-en">', 1)  # statements come twice: ja then en
        body = en[1] if len(en) == 2 else body
        ins = re.findall(r"<h3>\s*(?:Sample Input|入力例)[^<]*</h3>\s*<pre[^>]*>(.*?)</pre>", body, re.S)
        outs = re.findall(r"<h3>\s*(?:Sample Output|出力例)[^<]*</h3>\s*<pre[^>]*>(.*?)</pre>", body, re.S)
        problems.append((idx.strip(), name.strip(), [(pre_text(i), pre_text(o)) for i, o in zip(ins, outs)]))
    return problems


# ---------------------------------------------------------------- make cf2268 / make abc370

def starts_in(seconds):
    return str(datetime.timedelta(seconds=int(seconds)))


def codeforces(cid):
    slug, gym = f"cf{cid}", int(cid) >= 100000
    title, url = f"Codeforces {cid}", f"https://codeforces.com/{'gym' if gym else 'contest'}/{cid}/problems"
    if not gym:  # the official API knows every round: catches typos and not-started rounds up front
        status, body = get("https://codeforces.com/api/contest.list?gym=false")
        if status == 200:
            contest = next((x for x in json.loads(body)["result"] if x["id"] == int(cid)), None)
            if not contest:
                return fail(f"there is no Codeforces contest {cid}")
            title = contest["name"]
            left = contest.get("startTimeSeconds", 0) - time.time()  # own clock: the API answer can be a minute stale
            if left > 0:
                return fail(f"{title} has not started (starts in {starts_in(left)})")
    header(title, slug)
    status, page = get(url)
    why = ""
    if 'problemindex="' not in page:
        say(c(DIM, "Codeforces serves problem pages to browsers only: reading them through Safari…"))
        page, why = safari(url, 'problemindex="', 45)
    if page:
        return scaffold(slug, parse_codeforces(page))
    # no statements: still create the files from the official problem list, minus samples
    status, body = get(f"https://codeforces.com/api/contest.standings?contestId={cid}")
    problems = [(p["index"], p["name"], []) for p in json.loads(body)["result"]["problems"]] if status == 200 else []
    code = scaffold(slug, problems) if problems else 1
    say(c(YELLOW, "no samples: ") + why, "fix that and run this again, or paste samples into "
        f"{slug}/tests/<P>/1.in and 1.out")
    return code or 1


def atcoder(slug):
    base = f"https://atcoder.jp/contests/{slug}"
    status, page = get(base + "/tasks_print")
    why = ""
    if 'id="task-statement"' not in page:
        status, top = get(base)
        if status == 404:
            return fail(f"'{slug}' is not a .cpp file here, and not a contest on AtCoder or Codeforces")
        if status != 200:
            return fail(f"could not reach AtCoder ({status or top})")
        start = re.search(r"<time class='fixtime fixtime-full'>([^<]+)</time>", top)
        if start:
            left = (datetime.datetime.strptime(start.group(1), "%Y-%m-%d %H:%M:%S%z")
                    - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            if left > 0:
                return fail(f"{slug} has not started (starts in {starts_in(left)})")
        say(c(DIM, "AtCoder only shows these tasks to logged-in participants: reading them through Safari…"))
        page, why = safari(base + "/tasks_print", 'id="task-statement"', 25)
        if not page:
            return fail(f"could not read the tasks of {slug}: {why}")
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    header(html.unescape(title.group(1)).strip() if title else slug, slug)
    return scaffold(slug, parse_atcoder(page))


def scaffold(slug, problems):
    if not problems:
        return fail("found the contest but no problems in it")
    folder = os.path.join(ROOT, slug)
    with open(os.path.join(ROOT, "code.cpp"), encoding="utf-8") as f:
        template = f.read()
    os.makedirs(folder, exist_ok=True)
    if not os.path.exists(os.path.join(folder, "Makefile")):
        write(os.path.join(folder, "Makefile"), "include ../Makefile\n")
    for idx, name, samples in problems:
        stem = re.sub(r"\W", "", idx)
        try:
            with open(os.path.join(folder, stem + ".cpp"), "x", encoding="utf-8") as f:  # "x": never clobber a solution
                f.write(template)
            state = c(GREEN, "new")
        except FileExistsError:
            state = c(DIM, "kept")
        for n, (inp, out) in enumerate(samples, 1):
            write(os.path.join(folder, "tests", stem, f"{n}.in"), inp)
            write(os.path.join(folder, "tests", stem, f"{n}.out"), out)
        count = f"{len(samples)} sample{'s' * (len(samples) != 1)}"
        room = W - 34
        say(f"{c(BOLD + ';' + CYAN, stem.ljust(4))}{fit(name, room)}  "
            f"{c(DIM if samples else YELLOW, count.rjust(10))}  {(stem + '.cpp').ljust(9)}{state}")
    print(rule())
    first = re.sub(r"\W", "", problems[0][0])
    say(f"cd {slug} && vim {first}.cpp" + c(DIM, f"      <Space>t in vim, or `make {first}`, runs the samples"))
    print()
    return 0


def fail(message):
    print()
    say(c(RED, "✘ ") + message)
    print()
    return 1


# ---------------------------------------------------------------- make A

def same(got, expected):
    """Token-wise equality, like the default judges; reals may differ by 1e-6."""
    g, e = got.split(), expected.split()
    if len(g) != len(e):
        return False
    for a, b in zip(g, e):
        if a == b:
            continue
        if "." not in a + b:  # only real numbers get a tolerance, never big integers
            return False
        try:
            x, y = float(a), float(b)
        except ValueError:
            return False
        if not abs(x - y) <= 1e-6 * max(1.0, abs(y)):
            return False
    return True


def limits():
    # a runaway `while (1) cout << x` must not fill the disk mid-contest
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))


def run(exe, infile, seconds):
    """-> (returncode or None on timeout, stdout, stderr, milliseconds)"""
    with open(infile, "rb") as stdin, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        began = time.time()
        try:
            code = subprocess.run([exe], stdin=stdin, stdout=out, stderr=err, timeout=seconds,
                                  preexec_fn=limits).returncode
        except subprocess.TimeoutExpired:
            code = None
        ms = (time.time() - began) * 1000
        out.seek(0), err.seek(0)
        return code, out.read(4 << 20).decode("utf-8", "replace"), err.read(1 << 20).decode("utf-8", "replace"), ms


def fit(s, cols):
    s = s.expandtabs(4)
    if width(s) > cols:
        while width(s) > cols - 1:
            s = s[:-1]
        s += "…"
    return s + " " * (cols - width(s))


def block(title, text, limit=14, tail=False):
    lines = text.splitlines() or [""]
    hidden = len(lines) - limit
    if hidden > 0:
        lines = lines[-limit:] if tail else lines[:limit]
    say(c(DIM, title))
    if hidden > 0 and tail:
        say(c(DIM, f"│ … {hidden} earlier lines"))
    for line in lines:
        say(c(DIM, "│ ") + fit(line, W - 2).rstrip())
    if hidden > 0 and not tail:
        say(c(DIM, f"│ … {hidden} more lines"))


def side_by_side(expected, got, limit=24):
    e, g = expected.splitlines(), got.splitlines()
    col = (W - 5) // 2
    say(c(DIM, "expected".ljust(col + 2) + "  │ yours"))
    for i in range(min(max(len(e), len(g)), limit)):
        a, b = (e[i] if i < len(e) else ""), (g[i] if i < len(g) else "")
        wrong = a.split() != b.split()
        say(c(DIM, "│ ") + c(GREEN if wrong else "0", fit(a, col)) + c(DIM, "  │ ") + c(RED if wrong else "0", fit(b, col)).rstrip())
    if max(len(e), len(g)) > limit:
        say(c(DIM, f"│ … {max(len(e), len(g)) - limit} more lines"))


def test(src):
    src = os.path.abspath(src)
    folder, stem = os.path.dirname(src), os.path.splitext(os.path.basename(src))[0]
    exe = os.path.join(folder, ".build", stem)
    cxx = os.environ.get("CXX", "g++-16")
    flags = shlex.split(os.environ.get("CXXFLAGS", "-std=c++23 -O2 -Wall") + " " + os.environ.get("TESTFLAGS", "-DDEBUG"))
    seconds = float(os.environ.get("TL", "5"))
    header(stem, os.path.basename(folder))

    os.makedirs(os.path.dirname(exe), exist_ok=True)
    began = time.time()
    # always rebuild: 0.8s, and no stale binary can ever lie about the code on screen
    build = subprocess.run([cxx, *flags, os.path.basename(src), "-o", exe] + ["-fdiagnostics-color=always"] * TTY,
                           cwd=folder, capture_output=True, encoding="utf-8", errors="replace")
    if build.returncode != 0:
        say(c(BADGE["CE"], " CE ") + "  does not compile", "")
        print(build.stderr.rstrip())
        print()
        return 1
    say(c(DIM, f"compiled in {time.time() - began:.1f}s"))
    if build.stderr.strip():
        print(build.stderr.rstrip())

    inputs = sorted(glob.glob(os.path.join(glob.escape(folder), "tests", glob.escape(stem), "*.in")),
                    key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", os.path.basename(p))])
    if not inputs:
        say("", c(YELLOW, "no tests yet: ") + f"put samples in tests/{stem}/1.in and tests/{stem}/1.out", "")
        return 1

    # macOS vets a fresh binary on its first launch (~0.3s): pay that here, not in sample 1's time
    try:
        subprocess.run([exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
    except subprocess.TimeoutExpired:
        pass
    print()
    results = []
    for path in inputs:
        name = os.path.basename(path)[:-3]
        expected = None
        if os.path.exists(path[:-3] + ".out"):
            with open(path[:-3] + ".out", encoding="utf-8", errors="replace") as f:
                expected = f.read()
        code, out, err, ms = run(exe, path, seconds)
        if code is None:
            verdict, note = "TLE", f"killed after {seconds:g}s"
        elif code != 0:
            verdict, note = "RE", signal.Signals(-code).name if code < 0 else f"exit code {code}"
            if note == "SIGXFSZ":
                note = "printed more than 64MB"
        elif expected is None:
            verdict, note = "??", "no expected output to compare with"
        elif same(out, expected):
            verdict, note = "AC", ""
        else:
            verdict = "WA"
            note = "only the letter case differs" if out.lower().split() == expected.lower().split() else ""
        results.append((name, verdict, note, path, expected, out, err))
        took = f"{ms:.0f} ms"
        say(c(BADGE[verdict], f" {verdict} ".ljust(5)) + f"  {fit(name, 8)}" + c(DIM, fit(note, W - 15 - len(took)))
            + c(DIM, took))

    for name, verdict, note, path, expected, out, err in results:
        if verdict == "AC":
            continue
        print()
        print(rule(f"{name} · " + {"WA": "wrong answer" + ": " * bool(note) + note, "RE": "runtime error: " + note,
                                    "TLE": "time limit: " + note, "??": "output"}[verdict]))
        with open(path, encoding="utf-8", errors="replace") as f:
            block("input", f.read(), limit=12)
        if verdict == "WA":
            side_by_side(expected, out)
        elif out.strip() or verdict == "??":
            block("output" if verdict == "??" else "output before it stopped", out)
        err = "\n".join(line for line in re.sub(r"\033\[[0-9;]*m", "", err).splitlines() if line.strip())
        if err:
            block("stderr", err, limit=16, tail=True)

    passed = sum(v == "AC" for _, v, *_ in results)
    judged = sum(v != "??" for _, v, *_ in results)
    print()
    print(rule())
    if passed == len(results):
        say(c(BADGE["AC"], " ALL PASSED ") + f"  {passed}/{passed}")
    elif passed == judged:
        say(c(BADGE["??"], " RAN ") + f"  {passed}/{judged} passed, {len(results) - judged} with nothing to compare against")
    else:
        failed = " ".join(n for n, v, *_ in results if v not in ("AC", "??"))
        say(c(BADGE["WA"], " FAILED ") + f"  {passed}/{judged} passed" + c(DIM, f"   failing: {failed}"))
    print()
    return 0 if passed == judged else 1


# ---------------------------------------------------------------- entry

def selftest():
    cf = ('<div class="problemindexholder" problemindex="C1" data-uuid="x"><div class="header"><div class="title">'
          'C1. Easy &amp; Fun</div></div><div class="sample-test"><div class="input"><div class="title">Input</div><pre>\n'
          '<div class="test-example-line test-example-line-even">2</div><div class="test-example-line">1 &lt; 2</div>'
          '</pre></div><div class="output"><div class="title">Output</div><pre>\nYES\n</pre></div>'
          '<div class="input"><div class="title">Input</div><pre>8<br /></pre></div>'
          '<div class="output"><div class="title">Output</div><pre>NO<br /></pre></div></div></div>')
    assert parse_codeforces(cf) == [("C1", "Easy & Fun", [("2\n1 < 2\n", "YES\n"), ("8\n", "NO\n")])], parse_codeforces(cf)
    at = ('<span class="h2">A - Raise</span><span class="lang-ja"><h3>入力例 1</h3><pre>9\r\n</pre><h3>出力例 1</h3>'
          '<pre>ja\r\n</pre></span><span class="lang-en"><h3>Sample Input 1</h3><pre>1 0\r\n</pre>'
          '<h3>Sample Output 1</h3><pre>Yes\r\n</pre></span><span class="h2">B - Old</span><h3>入力例 1</h3>'
          '<pre class="prettyprint">3\n</pre><h3>出力例 1</h3><pre>4\n</pre>')
    assert parse_atcoder(at) == [("A", "Raise", [("1 0\n", "Yes\n")]), ("B", "Old", [("3\n", "4\n")])], parse_atcoder(at)
    assert same("1 2\n3\n", "1  2 3") and not same("1 2", "1 2 3") and not same("Yes", "YES")
    assert same("0.3333333", "0.333333333") and not same("0.34", "0.33") and not same("nan", "0.5")
    assert not same("1000000000000000001", "1000000000000000000")
    print("selftest ok")
    return 0


def main(argv):
    arg = argv[1] if len(argv) > 1 else "help"
    if arg in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    if arg == "selftest":
        return selftest()
    src = arg if arg.endswith(".cpp") else arg + ".cpp"
    if os.path.isfile(src):
        return test(src)
    cf = re.fullmatch(r"(?:cf)?(\d+)", arg) or re.search(r"codeforces\.com/(?:contest|gym)/(\d+)", arg)
    if cf:
        return codeforces(cf.group(1))
    at = re.search(r"atcoder\.jp/contests/([\w-]+)", arg) or re.fullmatch(r"([a-z][\w-]*)", arg)
    if at:
        return atcoder(at.group(1))
    return fail(f"there is no {src} here, and '{arg}' is not a contest id (try `make help`)")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        sys.exit(130)
