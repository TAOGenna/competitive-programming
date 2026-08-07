"""The reading list, from TAOGenna/competitive-programming.

The source is a Markdown checklist: ~130 links under eight topic headings, titles only, no
descriptions. Rather than invent any, Codeforces' own `blogEntry.view` supplies the real ones
for the 117 entries that live there -- the author's title, their handle, the community score,
the tags, and an excerpt taken from the post itself. Links elsewhere keep the list's own text
and say where they point.

The community score is what makes "most interesting" a measurable claim instead of an
assertion, so it is what the shelf sorts by.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request

from .cf import DATA, CodeforcesError, _get

SOURCE = ("https://raw.githubusercontent.com/TAOGenna/competitive-programming/"
          "master/Interesting_blogs/README.md")
CF_ENTRY = re.compile(r"codeforces\.com/blog/entry/(\d+)")
ITEM = re.compile(r"- \[([ xX])\]\s*\[(.+?)\]\((https?://[^)]+)\)")
HEADING = re.compile(r"^#{1,4}\s*(.+?)\s*(?:<br\s*/?>)?\s*$", re.M)


def _text(markup: str, limit: int = 320) -> str:
    """HTML to prose. Codeforces returns rendered posts, not source."""
    out = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
    out = re.sub(r"<[^>]+>", " ", out)
    out = html.unescape(out)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:limit].rstrip() + ("…" if len(out) > limit else "")


def _fetch_source() -> str:
    path = DATA / "blogs" / "source.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text()
    with urllib.request.urlopen(SOURCE, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    path.write_text(body)
    return body


def parse(markdown: str) -> list[dict]:
    """Links in order, each tagged with the heading it sits under."""
    topic = "Other"
    out: list[dict] = []
    for line in markdown.splitlines():
        head = HEADING.match(line)
        if head:
            topic = re.sub(r"<[^>]+>", "", head.group(1)).strip(" -")
            continue
        item = ITEM.search(line)
        if not item:
            continue
        done, label, url = item.groups()
        label = re.sub(r"<[^>]+>", "", label).strip()
        cf = CF_ENTRY.search(url)
        out.append({
            "topic": topic,
            "label": label,
            "url": url,
            "read": bool(done.strip()),
            "entry_id": int(cf.group(1)) if cf else None,
            "host": re.sub(r"^www\.", "", url.split("/")[2]),
        })
    return out


def _enrich(item: dict) -> dict:
    """Add Codeforces' own metadata where the link points there."""
    if not item["entry_id"]:
        return item
    cached = DATA / "blogs" / f"{item['entry_id']}.json"
    cached.parent.mkdir(parents=True, exist_ok=True)
    if cached.exists():
        meta = json.loads(cached.read_text())
    else:
        try:
            r = _get("blogEntry.view", blogEntryId=item["entry_id"])
        except (CodeforcesError, urllib.error.URLError):
            return item
        meta = {
            "title": _text(r.get("title", ""), 200),
            "author": r.get("authorHandle"),
            "score": r.get("rating"),
            "tags": [t for t in (r.get("tags") or []) if t],
            "created": r.get("creationTimeSeconds"),
            "excerpt": _text(r.get("content", "")),
        }
        cached.write_text(json.dumps(meta))
    return {**item, **meta}


def shelf(progress=None) -> list[dict]:
    """The whole list, enriched. Cached; the first build fetches at ~1 req/s."""
    items = parse(_fetch_source())
    out = []
    for n, item in enumerate(items):
        if progress:
            progress(n, len(items), item["label"])
        out.append(_enrich(item))
    return out


def author_ratings(items: list[dict]) -> dict:
    """Every author's current rating, in one request.

    user.info takes a semicolon-separated list, so ~40 authors cost a single call. It lets
    the shelf colour handles by the same rank ladder the rating graph uses.
    """
    handles = sorted({i["author"] for i in items if i.get("author")})
    if not handles:
        return {}
    path = DATA / "blogs" / "authors.json"
    if path.exists():
        known = json.loads(path.read_text())
        if all(h in known for h in handles):
            return known
    out: dict[str, int] = {}
    for chunk in (handles[i:i + 300] for i in range(0, len(handles), 300)):
        try:
            for u in _get("user.info", handles=";".join(chunk)):
                if u.get("rating") is not None:
                    out[u["handle"]] = u["rating"]
        except CodeforcesError:
            continue
    path.write_text(json.dumps(out))
    return out


def topics(items: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for i in items:
        counts[i["topic"]] = counts.get(i["topic"], 0) + 1
    return [{"topic": t, "count": c} for t, c in counts.items()]
