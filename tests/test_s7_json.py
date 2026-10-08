"""Pins `lib/s7/json.scm`, a JSON reader for stock s7, loaded by name from the engine's load path.

Pinned are the value mapping, every string escape, strings holding escaped quotes or a
trailing backslash, and json-error for malformed text and for text shaped to escape a string.
"""

import pytest

from conftest import sh

prelude = "\n".join([
  '(load "json.scm" (rootlet))',
  "(define (show v) (display (catch 'json-error (lambda () (v)) (lambda (t info) (string-append \"(refused \" (apply format #f info) \")\")))))",
  "",
])


def run(amk, tmp_path, *body):
  (tmp_path / "case.scm").write_text(prelude + "\n".join(body) + "\n")
  mk = tmp_path / "f.mk"
  mk.write_text('x := $(s7.exec (load "case.scm"))\nall:\n\t@echo \'$(x)\'\n')
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout.strip()


@pytest.mark.engines("s7")
def test_an_object_reads_as_a_hash_table_keyed_by_symbol(amk, tmp_path):
  out = run(amk, tmp_path,
            r'(let ((r (json-read "{\"pid\": 41, \"code\": 0, \"status\": \"success\", \"o\": {\"a\": [1]}}")))',
            r"  (display (list (r 'pid) (r 'code) (r 'status) ((r 'o) 'a) (hash-table? r))))")
  assert out == '(41 0 "success" #(1) #t)'


@pytest.mark.engines("s7")
def test_arrays_literals_and_numbers(amk, tmp_path):
  out = run(amk, tmp_path, r'(display (json-read "[0, -1, 2.5, -2.5e1, true, false, null, []]"))')
  assert out == "#(0 -1 2.5 -25.0 #t #f () #())"


@pytest.mark.engines("s7")
def test_every_escape_decodes(amk, tmp_path):
  out = run(amk, tmp_path, r'(write (json-read "\"q\\\" b\\\\ s\\/ t\\t n\\n u\\u00e9 p\\ud83d\\ude00\""))')
  assert out == r'"q\" b\\ s/ t\t n\n ué p😀"'


@pytest.mark.engines("s7")
def test_escaped_quotes_and_a_trailing_backslash_stay_in_the_string(amk, tmp_path):
  out = run(amk, tmp_path,
            r'''(write (list ((json-read "{\"m\": \"a\\\"b\\\"c\"}") 'm) ((json-read "{\"m\": \"end\\\\\"}") 'm)))''')
  assert out == r'("a\"b\"c" "end\\")'


@pytest.mark.engines("s7")
@pytest.mark.parametrize("text,why", [
  (r"{} x", "text after the value"),
  (r"\"\\q\"", "unknown escape"),
  (r"[1,", "expected a value"),
  (r"", "expected a value"),
  (r"{\"a\" 1}", "expected"),
  (r"[1 2]", "expected a comma or the close"),
  (r"\"abc", "unterminated string"),
])
def test_malformed_text_is_refused_as_json_error(amk, tmp_path, text, why):
  out = run(amk, tmp_path, f'(show (lambda () (json-read "{text}")))')
  assert out.startswith("(refused json-read: " + why), out


@pytest.mark.engines("s7")
def test_text_shaped_to_escape_a_string_is_refused_not_run(amk, tmp_path):
  out = run(amk, tmp_path,
            "(define ran #f)",
            r'(show (lambda () (json-read "{\"a\": \"x\\\" ) (set! ran #t) (\\\"")))',
            "(display (list 'ran ran))")
  assert out.startswith("(refused json-read: unterminated string"), out
  assert out.endswith("(ran #f)"), out
