"""Small shared helpers. ASCII-only console output so Windows PowerShell never chokes."""
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path


def setup_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class _Out:
    stream = None


def redirect_to_stderr():
    """Used by the MCP server: stdout carries the protocol, so progress goes to stderr."""
    _Out.stream = sys.stderr


def _s():
    return _Out.stream or sys.stdout


def say(msg=""):
    print(msg, file=_s(), flush=True)


def say_inline(msg):
    print(msg, end="", file=_s(), flush=True)


def stage(name):
    print(f"\n=== {name} ===", file=_s(), flush=True)


def slugify(text, maxlen=40):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:maxlen].strip("-")) or "game"


def snake(text, maxlen=24):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return (s[:maxlen].strip("_")) or "sprite"


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@contextmanager
def timed(timings, key):
    """Accumulate wall-clock seconds for a pipeline stage into a dict."""
    t0 = time.time()
    try:
        yield
    finally:
        timings[key] = round(timings.get(key, 0.0) + time.time() - t0, 2)
