#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""Serve markdown as github.com renders it, from the directory it runs in.

Usage: preview.py REPO PORT. A request for a .md path renders it through GitHub's markdown api by way of gh, in REPO's context, and wraps
it in github-markdown-css at the width of a repository README; ?theme=light or ?theme=dark
pins a theme. Any other path is served as a file, so relative images resolve.
"""

import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

CSS = "https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown{theme}.css"
PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title><base href="{base}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{css}">
<style>body{{margin:0;background:{bg}}} .markdown-body{{box-sizing:border-box;max-width:1030px;margin:0 auto;padding:32px}}</style>
</head><body><article class="markdown-body">
{body}
</article></body></html>
"""
BACKGROUND = {"": "Canvas", "-light": "#ffffff", "-dark": "#0d1117"}


def render(repo, page, theme=""):
  text = Path(page).read_text()
  html = subprocess.run(["gh", "api", "-X", "POST", "/markdown", "-f", "mode=gfm", "-f", f"context={repo}", "-F", "text=@-"],
                        input=text, capture_output=True, text=True, check=True).stdout
  # A pinned theme picks the picture sources as GitHub's themed-picture does, not by the OS preference.
  dark = 'media="(prefers-color-scheme: dark)"'
  html = html.replace(dark, 'media="not all"' if theme == "-light" else 'media="all"' if theme == "-dark" else dark)
  base = f"/{Path(page).parent.as_posix()}/".replace("/./", "/")
  return PAGE.format(title=page, base=base, css=CSS.format(theme=theme), bg=BACKGROUND[theme], body=html)


class Handler(SimpleHTTPRequestHandler):
  def __init__(self, *args, repo, **kw):
    self.repo = repo
    super().__init__(*args, **kw)

  def do_GET(self):
    url = urlsplit(self.path)
    if url.path == "/":
      self.send_response(302)
      self.send_header("Location", "/README.md")
      self.end_headers()
      return
    page = url.path.lstrip("/")
    if not page.endswith(".md") or not Path(page).is_file():
      return super().do_GET()
    theme = {"light": "-light", "dark": "-dark"}.get(parse_qs(url.query).get("theme", [""])[0], "")
    try:
      body = render(self.repo, page, theme).encode()
    except subprocess.CalledProcessError as e:
      self.send_error(502, f"gh api /markdown failed: {e.stderr.strip()}")
      return
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)


def main(argv):
  if len(argv) != 2:
    sys.exit(__doc__)
  repo, port = argv
  server = ThreadingHTTPServer(("localhost", int(port)), partial(Handler, repo=repo))
  print(f"serving {Path.cwd()} at http://localhost:{port}/ in the context of {repo}", flush=True)
  server.serve_forever()


if __name__ == "__main__":
  main(sys.argv[1:])
