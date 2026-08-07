"""Local web server. Standard library only, so `python -m vrating.web.server` just runs.

Results stream over Server-Sent Events. On a cold cache each contest costs a couple of
seconds of rate-limited Codeforces calls, so the page plots each contest the moment it
lands instead of staring at a spinner for a minute.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dataclasses import asdict as _asdict

from ..career import atcoder, engine, upsolve
from ..sources import cf as src

STATIC = Path(__file__).parent / "static"

# Codeforces rate-limits per IP, not per user, so concurrent replays contend for one budget.
# Cap the heavy endpoints; queued requests wait rather than thrashing the API.
MAX_CONCURRENT_SCANS = int(os.environ.get("VRATING_MAX_SCANS", "4"))
_scans = threading.BoundedSemaphore(MAX_CONCURRENT_SCANS)


def _parse_ranks(text: str):
    """'abc300:412,arc158:88' -> ordered sittings. Order is the order they were sat in."""
    out = []
    for chunk in text.split(","):
        cid, sep, rank = chunk.partition(":")
        cid, rank = cid.strip(), rank.strip()
        if not sep or not cid or not rank.isdigit() or int(rank) < 1:
            continue
        out.append({"contest_id": cid, "rank": int(rank)})
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _event(self, name, payload):
        chunk = f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode()
        self.wfile.write(chunk)
        self.wfile.flush()

    def _sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # Honoured by nginx and by Cloudflare Tunnel: do not buffer this response.
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()

    @contextlib.contextmanager
    def _heartbeat(self, every=20.0):
        """Emit an SSE comment while a phase is doing silent work.

        Cloudflare closes a proxied request with 524 if the origin sends nothing for 100
        seconds, and a cold cache can spend minutes fetching standings without producing an
        event. A comment line keeps the stream alive and is ignored by EventSource.
        """
        stop = threading.Event()

        def beat():
            while not stop.wait(every):
                try:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                except Exception:
                    return
        t = threading.Thread(target=beat, daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)

        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(),
                              "text/html; charset=utf-8")

        if url.path == "/healthz":
            # Cache coverage is the one number that decides whether this feels fast.
            data = src.DATA
            cached = len(list((data / "st").glob("*.npz"))) if (data / "st").is_dir() else 0
            rated = len(list((data / "rc").glob("*.npz"))) if (data / "rc").is_dir() else 0
            indexed = len(list((data / "prior").glob("*.npy"))) if (data / "prior").is_dir() else 0
            warm = cached >= 0.9 * max(indexed, 1)
            return self._send(200, {
                "ok": True,
                "standings_cached": cached,
                "contests_known": rated,
                "prior_index": indexed,
                "warm": bool(indexed and warm),
                "hint": None if (indexed and warm)
                        else "run: python3 -m vrating.sources.prewarm",
            })

        if url.path == "/api/stream":
            handle = (query.get("handle") or [""])[0].strip()
            if not handle:
                return self._send(400, {"error": "handle required"})
            return self._stream(handle)

        if url.path == "/api/upsolve":
            handle = (query.get("handle") or [""])[0].strip()
            if not handle:
                return self._send(400, {"error": "handle required"})
            return self._upsolve(handle)

        if url.path == "/api/ac/candidates":
            handle = (query.get("handle") or [""])[0].strip()
            if not handle:
                return self._send(400, {"error": "handle required"})
            try:
                return self._send(200, {
                    "handle": handle,
                    "sittings": atcoder.candidate_sittings(handle),
                    "real": atcoder.real_curve(handle),
                })
            except Exception as exc:
                return self._send(200, {"error": str(exc)})

        if url.path == "/api/ac/career":
            handle = (query.get("handle") or [""])[0].strip()
            ranks = (query.get("ranks") or [""])[0]
            sittings = _parse_ranks(ranks)
            if not handle or not sittings:
                return self._send(400, {"error": "handle and at least one rank required"})
            try:
                return self._send(200, atcoder.career_json(handle, sittings))
            except Exception as exc:
                return self._send(200, {"error": str(exc)})

        return self._send(404, {"error": "not found"})

    def _upsolve(self, handle, parts=None, real=None, primary=None, prefetched=None):
        self._sse_headers()
        if not _scans.acquire(timeout=120):
            self._event("failed", {"error": "server busy, try again in a moment"})
            self.close_connection = True
            return
        try:
            handles = handle if isinstance(handle, list) else engine.parse_handles(handle)
            if parts is None:
                career = engine.career_json(handles)
            else:
                entries = [asdict(e) for e in engine.build_career(handles, participations=parts)]
                career = engine.summarize(handles, entries, real or [], primary or handles[0])
                career["entries"] = entries
            virtual_ratings = {e["contest_id"]: e["old_rating"] for e in career["entries"]}
            self._event("meta", {"handle": " + ".join(handles), "rating": career["rating"]})

            with self._heartbeat():          # this phase can be silent for minutes when cold
                rounds, solved = upsolve.history(handles, virtual_ratings=virtual_ratings,
                                                 prefetched=prefetched)
            self._event("meta", {"handle": " + ".join(handles), "rating": career["rating"],
                                 "rounds": len(rounds), "already_solved": len(solved)})

            def progress(done, total, label):
                self._event("progress", {"done": done, "total": total, "label": label})

            items = upsolve.suggest(career["rating"], rounds,
                                    already_solved=solved, progress=progress)
            self._event("done", {"rating": career["rating"],
                                 "rounds": len(rounds),
                                 "already_solved": len(solved),
                                 "items": [_asdict(i) for i in items],
                                 "tags": upsolve.by_tag(items)})
        except BrokenPipeError:
            pass
        except Exception as exc:
            try:
                self._event("failed", {"error": str(exc)})
            except BrokenPipeError:
                pass
        finally:
            _scans.release()
        self.close_connection = True

    def do_POST(self):
        """Same stream, but the caller has already fetched the per-user data.

        Codeforces serves user.status and user.rating with CORS, so the page pulls them
        itself -- in parallel, against the visitor's own rate-limit budget rather than this
        server's shared one. That is 3.5 of the 3.7 seconds a warm replay used to take.
        """
        url = urlparse(self.path)
        if url.path not in ("/api/stream", "/api/upsolve"):
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 64 * 1024 * 1024:
                return self._send(413, {"error": "payload too large"})
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            return self._send(400, {"error": "malformed body"})

        handles = engine.parse_handles(" ".join(payload.get("handles") or []))
        if not handles:
            return self._send(400, {"error": "handles required"})
        subs = payload.get("submissions") or {}
        real = payload.get("real") or []
        primary = payload.get("real_handle") or handles[0]
        parts = engine.group_virtual([(h, subs.get(h) or []) for h in handles])
        if url.path == "/api/upsolve":
            return self._upsolve(handles, parts=parts, real=real, primary=primary,
                                 prefetched=payload.get("prefetched") or None)
        self._stream(handles, parts=parts, real=real, primary=primary)

    def _stream(self, handle, parts=None, real=None, primary=None):
        self._sse_headers()
        entries: list[dict] = []
        if not _scans.acquire(timeout=120):
            self._event("failed", {"error": "server busy, try again in a moment"})
            self.close_connection = True
            return
        try:
            handles = handle if isinstance(handle, list) else engine.parse_handles(handle)
            if primary is None:
                primary = engine.main_handle(handles)
            if real is None:
                real = engine.real_curve(primary)
            if parts is None:
                with self._heartbeat():
                    parts = engine.virtual_participations(handles)
            self._event("meta", {"handle": " + ".join(handles), "handles": handles,
                                 "real_handle": primary, "total": len(parts), "real": real})
            for entry in engine.iter_career(handles, participations=parts):
                entries.append(asdict(entry))
                self._event("entry", asdict(entry))
            self._event("done", engine.summarize(handles, entries, real, primary))
        except BrokenPipeError:
            pass
        except Exception as exc:
            try:
                self._event("failed", {"error": str(exc)})
            except BrokenPipeError:
                pass
        finally:
            _scans.release()
        self.close_connection = True


def main(port: int | None = None, host: str | None = None, banner: bool = True):
    port = port or int(os.environ.get("VRATING_PORT", "8770"))
    host = host or os.environ.get("VRATING_HOST", "127.0.0.1")
    shown = host if host not in ("0.0.0.0", "::") else "0.0.0.0"
    if banner:      # `python -m vrating` prints its own, nicer one
        print(f"vrating -> http://{shown}:{port}  (max {MAX_CONCURRENT_SCANS} concurrent scans)",
              flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
