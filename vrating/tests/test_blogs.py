"""Parsing the reading list, and turning Codeforces posts into card content."""
import pytest

from vrating.sources import blogs

SAMPLE = """**Welcome to the Blogs-Poderosos- wiki!**

***
## Data Structures<br/>
- [ ] [Prefix sum, difference array](https://codeforces.com/blog/entry/88474)
- [x] [Already read this one](https://codeforces.com/blog/entry/12345)<br/>
- [ ] [A visual Introduction](https://medium.com/carpanese/an-illustrated-intro-8c1989d53308)<br/>

## Graphs <br/>
- [ ] [[Tutorial] The DFS tree](https://codeforces.com/blog/entry/68138)<br/>
"""


def test_parse_keeps_topic_order_and_read_state():
    items = blogs.parse(SAMPLE)
    assert [i["topic"] for i in items] == ["Data Structures"] * 3 + ["Graphs"]
    assert [i["read"] for i in items] == [False, True, False, False]


def test_parse_extracts_codeforces_entry_ids_and_hosts():
    items = blogs.parse(SAMPLE)
    assert items[0]["entry_id"] == 88474
    assert items[0]["host"] == "codeforces.com"
    assert items[2]["entry_id"] is None, "a non-Codeforces link has no entry to enrich"
    assert items[2]["host"] == "medium.com"


def test_parse_strips_markup_from_labels():
    items = blogs.parse(SAMPLE)
    assert items[3]["label"] == "[Tutorial] The DFS tree"
    assert "<br" not in "".join(i["label"] for i in items)


def test_headings_lose_their_trailing_break_tags():
    assert blogs.parse(SAMPLE)[3]["topic"] == "Graphs"


def test_text_renders_codeforces_html_as_prose():
    html = '<div class="ttypography"><p>Hi!</p><p>Prefix sums &amp; more</p></div>'
    assert blogs._text(html) == "Hi! Prefix sums & more"


def test_text_drops_scripts_and_truncates_with_an_ellipsis():
    assert "alert" not in blogs._text("<script>alert(1)</script><p>safe</p>")
    long = blogs._text("<p>" + "word " * 400 + "</p>", limit=40)
    assert len(long) <= 41 and long.endswith("…")


def test_topics_counts_each_section():
    counts = {t["topic"]: t["count"] for t in blogs.topics(blogs.parse(SAMPLE))}
    assert counts == {"Data Structures": 3, "Graphs": 1}


@pytest.mark.gate
def test_the_real_list_parses_and_is_mostly_codeforces():
    items = blogs.parse(blogs._fetch_source())
    assert len(items) > 100
    assert sum(1 for i in items if i["entry_id"]) > 0.8 * len(items)
    assert all(i["url"].startswith("http") for i in items)
    assert len({i["topic"] for i in items}) >= 6


def test_refresh_rereads_the_list_but_keeps_fetched_posts(tmp_path, monkeypatch):
    """Adding a blog upstream should not throw away already-fetched post metadata."""
    import io
    monkeypatch.setattr(blogs, "DATA", tmp_path)
    served = [SAMPLE, SAMPLE + "- [ ] [New one](https://codeforces.com/blog/entry/999)\n"]
    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return io.BytesIO(served[min(len(calls) - 1, 1)].encode())

    monkeypatch.setattr(blogs.urllib.request, "urlopen", fake_urlopen)

    assert len(blogs.parse(blogs._fetch_source())) == 4          # first read, one fetch
    assert len(blogs.parse(blogs._fetch_source())) == 4          # cached, no fetch
    assert len(calls) == 1

    assert len(blogs.parse(blogs._fetch_source(refresh=True))) == 5   # re-read picks it up
    assert len(calls) == 2

    # a post fetched earlier is still on disk and is not re-requested
    (tmp_path / "blogs" / "88474.json").write_text('{"title":"cached","score":1}')
    item = next(i for i in blogs.parse(blogs._fetch_source()) if i["entry_id"] == 88474)
    assert blogs._enrich(item)["title"] == "cached"
