"""Pins mdheaders: what a run writes, what it leaves alone, and how it refuses a bad page."""

import os

import pytest

import mdheaders

OPEN = '<!-- header engine-api "Engine API" | Literals #engine-literals | FFI docs/FFI.md#init -->'
CLOSE = "<!-- /header -->"
PAGE = f"# Title\n\nIntro.\n\n{OPEN}\n{CLOSE}\n\nBody.\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / "README.md").write_text(PAGE)
  return tmp_path


def run(*args):
  return mdheaders.main(["--img", "img", *args])


def test_a_run_fills_the_block_and_writes_both_themes(repo):
  assert run("README.md") == 0
  text = (repo / "README.md").read_text()
  assert text.startswith("# Title\n\nIntro.\n\n" + OPEN + "\n<p align=\"right\"><a id=\"engine-api\"></a>")
  assert text.endswith(CLOSE + "\n\nBody.\n")
  assert '<a href="docs/FFI.md#init">' in text and 'alt="Engine API"' in text
  names = sorted(p.name for p in (repo / "img").iterdir())
  assert names == sorted(["_rule.svg", "_rule.dark.svg", "readme.engine-api.title.svg", "readme.engine-api.title.dark.svg",
                          "readme.engine-api.0.svg", "readme.engine-api.0.dark.svg",
                          "readme.engine-api.1.svg", "readme.engine-api.1.dark.svg"])


def test_a_second_run_writes_nothing(repo, capsys):
  run("README.md")
  stamp = os.stat(repo / "README.md").st_mtime_ns
  assert run("README.md") == 0
  assert os.stat(repo / "README.md").st_mtime_ns == stamp
  assert "0 files written" in capsys.readouterr().out


def test_check_reports_without_writing(repo, capsys):
  assert run("--check", "README.md") == 1
  assert (repo / "README.md").read_text() == PAGE
  assert not (repo / "img").exists()
  assert "out of date: README.md" in capsys.readouterr().err
  run("README.md")
  assert run("--check", "README.md") == 0


def test_text_outside_the_markers_is_kept_and_text_inside_is_replaced(repo):
  (repo / "README.md").write_text(PAGE.replace(CLOSE, "hand edit\n" + CLOSE).replace("Body.", "Body, edited."))
  run("README.md")
  text = (repo / "README.md").read_text()
  assert "hand edit" not in text and "Body, edited." in text


def test_markers_inside_fenced_code_are_ignored(repo):
  (repo / "README.md").write_text(f"````md\n{OPEN}\n```\n{CLOSE}\n````\n\n~~~\n{OPEN}\n~~~\n")
  assert run("README.md") == 0
  assert (repo / "README.md").read_text().count("<picture>") == 0


def test_crlf_pages_stay_crlf(repo):
  (repo / "README.md").write_bytes(PAGE.replace("\n", "\r\n").encode())
  run("README.md")
  raw = (repo / "README.md").read_bytes()
  assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_a_nested_page_points_at_the_images_relative_to_itself(repo):
  (repo / "docs").mkdir()
  (repo / "docs" / "FFI.md").write_text(PAGE)
  run("README.md", "docs/FFI.md")
  text = (repo / "docs" / "FFI.md").read_text()
  assert 'src="../img/docs-ffi.engine-api.title.svg"' in text
  assert (repo / "img" / "docs-ffi.engine-api.title.svg").is_file()


def test_a_removed_header_prunes_only_its_own_signed_images(repo):
  (repo / "OTHER.md").write_text(PAGE)
  run("README.md", "OTHER.md")
  (repo / "img" / "readme.handmade.svg").write_text("<svg/>")
  (repo / "README.md").write_text("# Title\n")
  assert run("README.md") == 0
  names = {p.name for p in (repo / "img").iterdir()}
  assert not any(n.startswith("readme.engine-api") for n in names)
  assert "readme.handmade.svg" in names
  assert "other.engine-api.title.svg" in names


cases = {
  "never closed": (f"{OPEN}\n", "README.md:1: header 'engine-api' is never closed"),
  "opened twice": (f"{OPEN}\n{OPEN}\n{CLOSE}\n", "README.md:2: header opened while 'engine-api' from line 1 is still open"),
  "stray close": (f"text\n{CLOSE}\n", "README.md:2: closing marker with no open header"),
  "no title": ("<!-- header engine-api -->\n<!-- /header -->\n", "README.md:1: expected <!-- header ID"),
  "bad id": ('<!-- header Engine_API "Engine API" -->\n<!-- /header -->\n', "README.md:1: expected <!-- header ID"),
  "link with no target": ('<!-- header a "A" | Lonely -->\n<!-- /header -->\n', "README.md:1: link 'Lonely' needs a label and a target"),
  "duplicate id": (f"{OPEN}\n{CLOSE}\n\n{OPEN}\n{CLOSE}\n", "README.md:4: header 'engine-api' is already declared at line 1"),
}


@pytest.mark.parametrize("text,message", cases.values(), ids=cases.keys())
def test_a_bad_page_stops_the_run_and_writes_nothing(repo, capsys, text, message):
  (repo / "README.md").write_text(text)
  (repo / "OTHER.md").write_text(PAGE)
  assert run("OTHER.md", "README.md") == 2
  assert message in capsys.readouterr().err
  assert (repo / "OTHER.md").read_text() == PAGE
  assert not (repo / "img").exists()


def test_a_missing_page_is_an_error(repo, capsys):
  assert run("NOPE.md") == 2
  assert "NOPE.md: no such page" in capsys.readouterr().err


def test_a_header_with_no_links_is_just_a_title(repo):
  (repo / "README.md").write_text('<!-- header solo "Solo" -->\n<!-- /header -->\n')
  assert run("README.md") == 0
  assert (repo / "README.md").read_text().count("<picture>") == 2


def test_warnings_name_the_line(repo, capsys):
  (repo / "README.md").write_text(f"## Engine API\n\n{OPEN}\n{CLOSE}\nflush against the marker\n")
  assert run("README.md") == 0
  err = capsys.readouterr().err
  assert "README.md:1: warning: this heading also makes #engine-api" in err
  assert "README.md:5: warning: leave a blank line after the closing marker" in err


def test_a_comment_in_fenced_code_is_not_a_heading(repo, capsys):
  (repo / "README.md").write_text(f"```make\n# Engine API\n```\n\n{OPEN}\n{CLOSE}\n")
  assert run("README.md") == 0
  assert "warning" not in capsys.readouterr().err
