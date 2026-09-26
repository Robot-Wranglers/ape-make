#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""mdheaders: section headers for GitHub markdown, generated in place between marker comments.

Self-contained and stdlib only; run it with --help for the marker syntax and the rules.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

EPILOG = """\
A header is one comment line that declares it and one that closes it:

  <!-- header engine-api "Engine API" | Literals #engine-literals | Grammar #extended-grammar -->
  <!-- /header -->

The id is lowercase letters, digits, and dashes, and becomes the anchor. Each link is a
label and a target separated by its last space, and a header may have none. Everything
between the two lines belongs to the tool and is rewritten on every run; the rest of the
page is left byte for byte. Markers inside fenced code are ignored.

Every page is parsed before anything is written, and an error stops the run with its
file and line. Images are named for their page, and a run prunes the images it signed
for the pages it was given that no longer appear in them. Exit status: 0 when done or up
to date, 1 when --check finds something out of date, 2 on an error.
"""

SIGNATURE = "<!-- mdheaders -->"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
THEMES = {
  "": {"fg": "#1f2328", "link": "#0969da", "fill": "#f6f8fa", "edge": "#d1d9e0"},
  ".dark": {"fg": "#f0f6fc", "link": "#4493f8", "fill": "#151b23", "edge": "#3d444d"},
}
RULE = "_rule"
ROW = 40
EM = {**dict.fromkeys("iljtf.,:;!|' ", 0.3), **dict.fromkeys("mwMW", 0.85)}

OPEN = re.compile(r"<!--\s*header(?:\s+(?P<spec>.*?))?\s*-->$")
SPEC = re.compile(r'(?P<id>[a-z0-9][a-z0-9-]*)\s+"(?P<title>[^"]+)"\s*(?P<links>\|.*)?$')
CLOSE = re.compile(r"<!--\s*/header\s*-->$")
FENCE = re.compile(r"^ {0,3}(?P<mark>`{3,}|~{3,})(?P<info>.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
SYNTAX = 'expected <!-- header ID "Title" | Label target ... -->'


class SpecError(Exception):
  pass


@dataclass
class Header:
  id: str
  title: str
  links: list[tuple[str, str]]
  open: int
  close: int = -1


@dataclass
class Page:
  path: Path
  name: str
  text: str
  newline: str
  slug: str
  headers: list[Header] = field(default_factory=list)
  code: set[int] = field(default_factory=set)


def text_width(text, size):
  return sum(EM.get(c, 0.68 if c.isupper() else 0.55) for c in text) * size


def svg(w, h, body, stretch=False):
  ratio = ' preserveAspectRatio="none"' if stretch else ""
  return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h}" viewBox="0 0 {w:.0f} {h}"{ratio}>'
          f'{SIGNATURE}{body}</svg>\n')


def title_svg(text, t):
  # Natural spacing with room to spare: the width estimate is rough and empty space on the right is invisible.
  size = 24
  return svg(text_width(text, size) * 1.15, ROW,
             f'<text x="0" y="29" font-family="{FONT}" font-size="{size}" font-weight="600" fill="{t["fg"]}">{escape(text)}</text>')


def button_svg(text, t):
  size, pad, gap = 13, 10, 3
  w = text_width(text, size)
  return svg(w + 2 * pad + 2 * gap, ROW,
             f'<rect x="{gap}" y="8.5" width="{w + 2 * pad:.0f}" height="24" rx="12" fill="{t["fill"]}" stroke="{t["edge"]}"/>'
             f'<text x="{gap + pad}" y="25" font-family="{FONT}" font-size="{size}" fill="{t["link"]}" '
             f'textLength="{w:.0f}" lengthAdjust="spacingAndGlyphs">{escape(text)}</text>')


def rule_svg(t):
  return svg(2000, 1, f'<rect width="2000" height="1" fill="{t["edge"]}"/>', stretch=True)


def themed(name, make):
  return {f"{name}{suffix}.svg": make(theme) for suffix, theme in THEMES.items()}


def lines_of(text):
  # Split on newlines only, keeping each one, so line numbers match an editor's and a rejoin restores the text exactly.
  return re.findall(r"[^\n]*\n|[^\n]+$", text)


def slugify(path):
  return re.sub(r"[^a-z0-9]+", "-", path.with_suffix("").as_posix().lower()).strip("-")


def github_slug(text):
  text = re.sub(r"<[^>]+>|[`*_\[\]]|\(([^)]*)\)", "", text).strip().lower()
  return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def parse_spec(spec, where):
  m = SPEC.match(spec or "")
  if not m:
    raise SpecError(f"{where}: {SYNTAX}")
  links = []
  for part in (m["links"] or "").split("|")[1:]:
    label, _, target = part.strip().rpartition(" ")
    if not label.strip() or not target:
      raise SpecError(f"{where}: link {part.strip()!r} needs a label and a target")
    links.append((label.strip(), target))
  return m["id"], m["title"].strip(), links


def parse(path, root):
  name = os.path.relpath(path, root)
  try:
    raw = path.read_bytes().decode("utf-8")
  except FileNotFoundError:
    raise SpecError(f"{name}: no such page") from None
  except UnicodeDecodeError as e:
    raise SpecError(f"{name}: not utf-8 ({e.reason} at byte {e.start})") from None
  page = Page(path, name, raw, "\r\n" if "\r\n" in raw else "\n", slugify(Path(name)))
  lines, fence, current = [line.rstrip("\r\n") for line in lines_of(raw)], None, None
  for n, line in enumerate(lines):
    where, stripped = f"{name}:{n + 1}", line.strip()
    if fm := FENCE.match(line):
      if fence is None:
        fence = fm["mark"]
      elif fm["mark"][0] == fence[0] and len(fm["mark"]) >= len(fence) and not fm["info"].strip():
        fence = None
      page.code.add(n)
      continue
    if fence:
      page.code.add(n)
      continue
    if CLOSE.match(stripped):
      if current is None:
        raise SpecError(f"{where}: closing marker with no open header")
      current.close = n
      page.headers.append(current)
      current = None
    elif om := OPEN.match(stripped):
      if current is not None:
        raise SpecError(f"{where}: header opened while {current.id!r} from line {current.open + 1} is still open")
      current = Header(*parse_spec(om["spec"], where), open=n)
  if current is not None:
    raise SpecError(f"{name}:{current.open + 1}: header {current.id!r} is never closed")
  seen = {}
  for h in page.headers:
    if h.id in seen:
      raise SpecError(f"{name}:{h.open + 1}: header {h.id!r} is already declared at line {seen[h.id]}")
    seen[h.id] = h.open + 1
  return page


def warnings(page):
  lines, owned = [line.rstrip("\r\n") for line in lines_of(page.text)], set(page.code)
  for h in page.headers:
    owned.update(range(h.open, h.close + 1))
  ids = {h.id: h for h in page.headers}
  for n, line in enumerate(lines):
    if n in owned:
      continue
    if (m := HEADING.match(line)) and github_slug(m["text"]) in ids:
      yield f"{page.name}:{n + 1}: warning: this heading also makes #{github_slug(m['text'])}, so GitHub suffixes one of them"
    for i in re.findall(r'\b(?:id|name)="([^"]+)"', line):
      if i in ids:
        yield f"{page.name}:{n + 1}: warning: #{i} is also the anchor of the header at line {ids[i].open + 1}"
  for h in page.headers:
    if h.close + 1 < len(lines) and lines[h.close + 1].strip():
      yield f"{page.name}:{h.close + 2}: warning: leave a blank line after the closing marker, or this line joins the header's html"


def picture(src, alt, attrs=""):
  dark = src.replace(".svg", ".dark.svg")
  return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{dark}">'
          f'<img{attrs} src="{src}" alt="{escape(alt)}"></picture>')


def render(page, h, img):
  # Inline buttons in a right-aligned paragraph wrap in reading order, where right floats would stack reversed.
  src = lambda name: Path(os.path.relpath(img / name, page.path.parent)).as_posix()
  base = f"{page.slug}.{h.id}"
  title = f'<a href="#{h.id}">{picture(src(f"{base}.title.svg"), h.title, " align=left")}</a>'
  buttons = "".join(f'<a href="{escape(target)}">{picture(src(f"{base}.{i}.svg"), label)}</a>'
                    for i, (label, target) in enumerate(h.links))
  rule = picture(src(f"{RULE}.svg"), "", " width=2000 height=1")
  return [f'<p align="right"><a id="{h.id}"></a>{title}{buttons}<br clear="all">{rule}</p>']


def images(page, h):
  base = f"{page.slug}.{h.id}"
  out = themed(f"{base}.title", lambda t: title_svg(h.title, t))
  for i, (label, _) in enumerate(h.links):
    out |= themed(f"{base}.{i}", lambda t, label=label: button_svg(label, t))
  return out


def rewrite(page, img):
  lines = lines_of(page.text)
  for h in reversed(page.headers):
    lines[h.open + 1:h.close] = [line + page.newline for line in render(page, h, img)]
  return "".join(lines)


def plan(pages, img):
  files = {img / name: body for name, body in themed(RULE, rule_svg).items()}
  for page in pages:
    files[page.path] = rewrite(page, img)
    for h in page.headers:
      files |= {img / name: body for name, body in images(page, h).items()}
  slugs = {page.slug for page in pages}
  stale = [f for f in sorted(img.glob("*.svg"))
           if f not in files and f.name.split(".")[0] in slugs and SIGNATURE in f.read_text(errors="replace")]
  return files, stale


def changed(path, body):
  return not path.is_file() or path.read_bytes().decode("utf-8", errors="replace") != body


def main(argv=None):
  ap = argparse.ArgumentParser(prog="mdheaders", description=__doc__.splitlines()[0],
                               epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("--img", type=Path, required=True, help="directory for the generated images")
  ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if anything is out of date")
  ap.add_argument("pages", nargs="+", type=Path, help="markdown pages to process")
  args = ap.parse_args(argv)
  root = Path.cwd()
  try:
    pages = [parse(p if p.is_absolute() else root / p, root) for p in dict.fromkeys(args.pages)]
  except SpecError as e:
    print(f"mdheaders: {e}", file=sys.stderr)
    return 2
  for page in pages:
    for w in warnings(page):
      print(f"mdheaders: {w}", file=sys.stderr)
  img = args.img if args.img.is_absolute() else root / args.img
  files, stale = plan(pages, img)
  todo = [p for p, body in files.items() if changed(p, body)]
  rel = lambda p: os.path.relpath(p, root)
  if args.check:
    for p in todo:
      print(f"mdheaders: out of date: {rel(p)}", file=sys.stderr)
    for p in stale:
      print(f"mdheaders: stale image: {rel(p)}", file=sys.stderr)
    return 1 if todo or stale else 0
  img.mkdir(parents=True, exist_ok=True)
  for p in todo:
    p.write_bytes(files[p].encode("utf-8"))
  for p in stale:
    p.unlink()
  headers = sum(len(page.headers) for page in pages)
  print(f"mdheaders: {headers} headers in {len(pages)} pages; {len(todo)} files written, {len(stale)} stale images removed")
  return 0


if __name__ == "__main__":
  sys.exit(main())
