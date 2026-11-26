"""Render third-party text safely into public GitHub issue bodies.

Discovery and coverage digests quote titles, source names, dates and URLs taken
from external feeds and lists. Interpolated raw, that text could inject markdown
or HTML, render links under misleading text, or @-mention (notify) arbitrary
users. Everything external therefore goes through these helpers:

  code(s)   inline code span: GitHub renders markdown and HTML inside it
            literally and does not turn @name into a mention
  link(u)   [link](u) for http(s) URLs only, with link-breaking characters
            percent-encoded; anything else renders as plain text
  cap(..)   keeps a body under GitHub's issue-body limit
Stdlib only, so tests can import it without the scripts' network dependencies.
"""
from __future__ import annotations

import re
import urllib.parse

MAX_TEXT = 200
MAX_URL = 500
# GitHub rejects issue bodies over 65,536 characters; leave room for the footer.
MAX_BODY = 60_000
_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def code(s, limit: int = MAX_TEXT) -> str:
    """One-line, length-capped inline code span for untrusted text."""
    text = _WS.sub(" ", _CTRL.sub(" ", str(s if s is not None else ""))).strip()
    # A backtick would close the span early; there is no escape inside code spans.
    text = text.replace("`", "'")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    # A span may not start or end with a space-only edge that collapses it.
    return f"`{text}`" if text else "`-`"


def link(url, label: str = "link") -> str:
    """Markdown link for an http(s) URL, or a plain marker when it is unusable."""
    u = _WS.sub("", _CTRL.sub("", str(url or "")))
    parts = urllib.parse.urlsplit(u)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or len(u) > MAX_URL:
        return "(no link)"
    # Everything outside `safe` is percent-encoded, including ( ) [ ] < > ' * `
    # that could end the link destination or open markup; % keeps existing escapes.
    return f"[{label}]({urllib.parse.quote(u, safe=':/?#@!$&+,;=%-._~')})"


def cap(header: str, lines: list[str], tail: str = "") -> str:
    """Join header + lines (+ tail), dropping trailing lines to stay under MAX_BODY."""
    out, size = [header], len(header) + len(tail) + 200
    for i, line in enumerate(lines):
        if size + len(line) + 1 > MAX_BODY:
            out.append(f"\n_… {len(lines) - i} more omitted to fit the issue size limit._")
            break
        out.append(line)
        size += len(line) + 1
    if tail:
        out.append(tail)
    return "\n".join(out) + "\n"
