#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["fonttools"]
# ///
"""mdheaders: section headers for GitHub markdown, generated in place between marker comments.

Stdlib only but for fonttools, which a title drawn as an image needs; run it with --help for the marker syntax and the rules.
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

  <!-- header ### engine-api "Engine API" | Literals #engine-literals | Grammar #extended-grammar -->
  <!-- /header -->

The leading hashes set the heading level as in markdown, and default to ## when left out.
The title is the heading's text, so it shows in GitHub's outline. A title in backticks,
"`module::amk.tspace`", is drawn instead as an image in the logo's typeface, Russo One,
smaller than heading text so a long name leaves room for the buttons; its alt text is the
title. A drawn title naming a module starts with an arrow: a submodule, "`mod :: dsys/petri`",
gets a left arrow to its parent module's page, dsys.md beside it, and any other module an
up arrow to the --index page and anchor. A link labeled ^, "| ^ ../README.md#engines", is
an up arrow to its target on any header, ahead of both. The other links are buttons
on the right of the same line, and levels 3 and below get a rule underneath, where GitHub
draws none of its own.

The id is lowercase letters, digits, and dashes, and becomes the anchor, written into the
heading so links survive a change of title. Every other heading needs a permalink of its
own, an <a id> on a line before it; --check fails on one without. Each link is a
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
ARROW = 0.6
TITLE_FONT = Path(__file__).parent / "fonts" / "RussoOne-Regular.ttf"
TITLE_SIZE, TITLE_BASE = 22, 29
EM = {**dict.fromkeys("iljtf.,:;!|' ", 0.3), **dict.fromkeys("mwMW", 0.85)}

OPEN = re.compile(r"<!--\s*header(?:\s+(?P<spec>.*?))?\s*-->$")
SPEC = re.compile(r'(?:(?P<level>#{1,6})\s+)?(?P<id>[a-z0-9][a-z0-9-]*)\s+"(?P<title>[^"]+)"\s*(?P<links>\|.*)?$')
CLOSE = re.compile(r"<!--\s*/header\s*-->$")
FENCE = re.compile(r"^ {0,3}(?P<mark>`{3,}|~{3,})(?P<info>.*)$")
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
ANCHOR = re.compile(r'<a\s+(?:id|name)=')
SYNTAX = 'expected <!-- header [##] ID "Title" | Label target ... -->'


class SpecError(Exception):
  pass


@dataclass
class Header:
  id: str
  title: str
  links: list[tuple[str, str]]
  level: int
  open: int
  close: int = -1
  drawn: bool = False
  up: str | None = None


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


def arrow_svg(d, w, t):
  # A bold arrow drawn as a path, scaled about the row's middle, with room after it before the title.
  y = ROW / 2 * (1 - ARROW)
  return svg(w * ARROW + 13, ROW,
             f'<path transform="translate(0 {y:.0f}) scale({ARROW})" d="{d}" fill="{t["link"]}"/>')


def left_svg(t):
  return arrow_svg("M1 20 L13 10 V16 H27 V24 H13 V30 Z", 27, t)


def up_svg(t):
  return arrow_svg("M11 7 L21 19 H15 V33 H7 V19 H1 Z", 21, t)


def button_svg(text, t):
  size, pad, gap = 13, 10, 3
  w = text_width(text, size)
  return svg(w + 2 * pad + 2 * gap, ROW,
             f'<rect x="{gap}" y="8.5" width="{w + 2 * pad:.0f}" height="24" rx="12" fill="{t["fill"]}" stroke="{t["edge"]}"/>'
             f'<text x="{gap + pad}" y="25" font-family="{FONT}" font-size="{size}" fill="{t["link"]}" '
             f'textLength="{w:.0f}" lengthAdjust="spacingAndGlyphs">{escape(text)}</text>')


def title_svg(text, t):
  # The title's glyphs as outlines, since an image on GitHub loads no fonts of its own.
  from fontTools.pens.svgPathPen import SVGPathPen
  from fontTools.ttLib import TTFont
  font = TTFont(TITLE_FONT)
  glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
  scale = TITLE_SIZE / font["head"].unitsPerEm
  x, paths = 0.0, []
  for c in text:
    name = cmap.get(ord(c), ".notdef")
    pen = SVGPathPen(glyphs)
    glyphs[name].draw(pen)
    if d := pen.getCommands():
      paths.append(f'<path transform="translate({x:.2f} {TITLE_BASE}) scale({scale:.5f} {-scale:.5f})" d="{d}"/>')
    x += hmtx[name][0] * scale
  return svg(x + 2, ROW, f'<g fill="{t["fg"]}">{"".join(paths)}</g>')


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
  title = m["title"].strip()
  drawn = len(title) > 2 and title.startswith("`") and title.endswith("`")
  return m["id"], title.strip("`") if drawn else title, links, len(m["level"] or "##"), drawn


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
      hid, title, links, level, drawn = parse_spec(om["spec"], where)
      up = next((target for label, target in links if label == "^"), None)
      current = Header(hid, title, [link for link in links if link[0] != "^"], level, open=n, drawn=drawn, up=up)
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


def unanchored(page):
  """Every markdown heading outside the generated headers and fenced code whose last non-blank line before it holds no anchor: a link to it breaks when its text changes."""
  lines, owned = [line.rstrip("\r\n") for line in lines_of(page.text)], set(page.code)
  for h in page.headers:
    owned.update(range(h.open, h.close + 1))
  prev = ""
  for n, line in enumerate(lines):
    if n in owned:
      continue
    if (m := HEADING.match(line)) and not ANCHOR.search(prev):
      yield f'{page.name}:{n + 1}: heading has no permalink: put <a id="{github_slug(m["text"])}"></a> on a line before it'
    if line.strip():
      prev = line


def nav_of(page, h, index):
  """Where a module title's arrow goes: a submodule, `mod :: dsys/petri`, left to dsys.md beside it; any other module up to the index."""
  if h.up:
    return h.up, "up", up_svg
  if not (h.drawn and h.title.startswith("mod ::")):
    return None
  if parent := h.title.rpartition("::")[2].strip().rpartition("/")[0]:
    return f'{parent.rpartition("/")[2]}.md', f"up to {parent}", left_svg
  if index:
    path, _, frag = index.partition("#")
    href = Path(os.path.relpath(Path.cwd() / path, page.path.parent)).as_posix() + (f"#{frag}" if frag else "")
    return href, "up to the module index", up_svg
  return None


def picture(src, alt, attrs=""):
  dark = src.replace(".svg", ".dark.svg")
  return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{dark}">'
          f'<img{attrs} src="{src}" alt="{escape(alt)}"></picture>')


def render(page, h, img, index=None):
  # Right floats stack in reverse, so the buttons go in last first to read left to right.
  src = lambda name: Path(os.path.relpath(img / name, page.path.parent)).as_posix()
  base = f"{page.slug}.{h.id}"
  anchor = f'<a id="{h.id}"></a>'
  buttons = "".join(f'<a href="{escape(target)}">{picture(src(f"{base}.{i}.svg"), label, " align=right")}</a>'
                    for i, (label, target) in reversed(list(enumerate(h.links))))
  rule = picture(src(f"{RULE}.svg"), "", " width=2000 height=1") if h.level > 2 else ""
  title = picture(src(f"{base}.title.svg"), h.title) if h.drawn else escape(h.title)
  if nav := nav_of(page, h, index):
    href, alt, _ = nav
    title = f'<a href="{escape(href)}">{picture(src(f"{base}.up.svg"), alt)}</a>{title}'
  tag = f"h{h.level}"
  return [f'<{tag}>{anchor}{title}{buttons}<br clear="all">{rule}</{tag}>']


def images(page, h, index=None):
  base = f"{page.slug}.{h.id}"
  out = themed(f"{base}.title", lambda t: title_svg(h.title, t)) if h.drawn else {}
  if nav := nav_of(page, h, index):
    out |= themed(f"{base}.up", nav[2])
  for i, (label, _) in enumerate(h.links):
    out |= themed(f"{base}.{i}", lambda t, label=label: button_svg(label, t))
  return out


def rewrite(page, img, index=None):
  lines = lines_of(page.text)
  for h in reversed(page.headers):
    lines[h.open + 1:h.close] = [line + page.newline for line in render(page, h, img, index)]
  return "".join(lines)


def plan(pages, img, index=None):
  files = {img / name: body for name, body in themed(RULE, rule_svg).items()}
  for page in pages:
    files[page.path] = rewrite(page, img, index)
    for h in page.headers:
      files |= {img / name: body for name, body in images(page, h, index).items()}
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
  ap.add_argument("--index", help="page#anchor, from the working directory, that a module title's up arrow links to")
  ap.add_argument("pages", nargs="+", type=Path, help="markdown pages to process")
  args = ap.parse_args(argv)
  root = Path.cwd()
  try:
    pages = [parse(p if p.is_absolute() else root / p, root) for p in dict.fromkeys(args.pages)]
  except SpecError as e:
    print(f"mdheaders: {e}", file=sys.stderr)
    return 2
  bare = []
  for page in pages:
    for w in warnings(page):
      print(f"mdheaders: {w}", file=sys.stderr)
    bare += list(unanchored(page))
  for b in bare:
    print(f"mdheaders: {b}", file=sys.stderr)
  img = args.img if args.img.is_absolute() else root / args.img
  files, stale = plan(pages, img, args.index)
  todo = [p for p, body in files.items() if changed(p, body)]
  rel = lambda p: os.path.relpath(p, root)
  if args.check:
    for p in todo:
      print(f"mdheaders: out of date: {rel(p)}", file=sys.stderr)
    for p in stale:
      print(f"mdheaders: stale image: {rel(p)}", file=sys.stderr)
    return 1 if todo or stale or bare else 0
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
