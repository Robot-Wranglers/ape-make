"""Pins m5 from the prelude: the read-or-default accessor, select and pluck, and the subscript table.

Each body is a plain makefile whose recipe echoes one expression per line, so a case is a key,
an expression, and the value it reads back. The table's row map and its guarded call on an
unknown key read names m5 leaves to compose.mk, so those cases stay in compose.mk's suite."""

import pytest

from conftest import sh


def run(amk, tmp_path, body):
  mk = tmp_path / "t.mk"
  mk.write_text(body)
  r = sh(amk, ["-s", "-f", str(mk), "all"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout


def body(variables, cases):
  return "\n".join(variables + ["", "all:"] + [f'\t@echo "{key}=[{expr}]"' for key, expr, _ in cases]) + "\n"


def line(out, key):
  return next(ln for ln in out.splitlines() if ln.startswith(f"{key}="))


# --- m5|, the read-or-default accessor: definedness is by origin, so an empty variable reads back empty.

DEFAULT_VARS = ["hit = yes", "empty =", "spaced =   padded   "]
DEFAULT_CASES = [
  ("hit", "$(call m5|,hit,fallback)", "yes"),
  ("miss", "$(call m5|,nosuchvar,fallback)", "fallback"),
  ("emptyVar", "$(call m5|,empty,fallback)", ""),
  ("emptyDefault", "$(call m5|,nosuchvar,)", ""),
  ("valueNotStripped", "$(call m5|,spaced,fallback)", "padded   "),
  ("nameIsStripped", "$(call m5|, hit , fallback)", "yes"),
]


@pytest.fixture(scope="module")
def default_out(amk, tmp_path_factory):
  return run(amk, tmp_path_factory.mktemp("m5default"), body(DEFAULT_VARS, DEFAULT_CASES))


@pytest.mark.parametrize("key,expr,expected", DEFAULT_CASES, ids=[c[0] for c in DEFAULT_CASES])
def test_default_case(default_out, key, expr, expected):
  assert line(default_out, key) == f"{key}=[{expected}]", default_out


def test_default_expands_even_on_a_hit(amk, tmp_path):
  # the marker proves the unused branch ran, which is why costly fallbacks stay out.
  marker = tmp_path / "touched"
  out = run(amk, tmp_path, f"hit = yes\nprobe = $(shell touch {marker}; echo D)\n\nall:\n" '\t@echo "eagerHit=[$(call m5|,hit,$(probe))]"\n')
  assert "eagerHit=[yes]" in out, out
  assert marker.exists(), "default was not expanded on a hit"


# --- m5.select and m5.pluck: keep an element, or read its value, when the pattern names a defined variable.

SELECT_VARS = ["a.x = 1", "c.x = 3", "b.y = 9", "e.x =", "m.x = one two", "p.a = A", "p.c = C"]
SELECT_CASES = [
  ("sel", "$(call m5.select, a b c, %.x)", "a c"),
  ("plk", "$(call m5.pluck, a b c, %.x)", "1 3"),
  ("selPre", "$(call m5.select, a b c, p.%)", "a c"),
  ("plkPre", "$(call m5.pluck, a b c, p.%)", "A C"),
  ("selEmptyList", "$(call m5.select, , %.x)", ""),
  ("plkEmptyList", "$(call m5.pluck, , %.x)", ""),
  ("selNoHits", "$(call m5.select, q r, %.x)", ""),
  ("selEmptyVal", "$(call m5.select, a e c, %.x)", "a e c"),
  ("plkEmptyVal", "$(call m5.pluck, a e c, %.x)", "1 3"),
  ("plkMulti", "$(call m5.pluck, a m, %.x)", "1 one two"),
  ("selOrder", "$(call m5.select, c a, %.x)", "c a"),
  ("selUnpadded", "$(call m5.select,a b c,%.x)", "a c"),
]


@pytest.fixture(scope="module")
def select_out(amk, tmp_path_factory):
  return run(amk, tmp_path_factory.mktemp("m5select"), body(SELECT_VARS, SELECT_CASES))


@pytest.mark.parametrize("key,expr,expected", SELECT_CASES, ids=[c[0] for c in SELECT_CASES])
def test_select_case(select_out, key, expr, expected):
  assert line(select_out, key) == f"{key}=[{expected}]", select_out


@pytest.mark.parametrize("key", ["sel", "selPre", "selUnpadded"])
def test_select_result_is_whitespace_normalized(select_out, key):
  # a skipped element must leave no gap, since callers comma-join the result.
  assert "  " not in line(select_out, key), line(select_out, key)


# --- m5.table: forward and reverse lookup, membership, order, and dispatch through handler names.

# A many-to-one collision, A and C both map to 1, and a baked default of 9.
TABLE_VARS = ["$(call m5.table, tt, A=1 B=2 C=1, 9)"]
TABLE_CASES = [
  ("fwdA", "$(tt[A])", "1"),
  ("fwdB", "$(tt[B])", "2"),
  ("resHit", "$(call tt.resolve,A)", "1"),
  ("resBaked", "$(call tt.resolve,ZZ)", "9"),
  ("resCall", "$(call tt.resolve,ZZ,77)", "77"),
  ("rev1", "$(call tt.reverse,1)", "A C"),
  ("rev2", "$(call tt.reverse,2)", "B"),
  ("hasA", "$(call tt.has?,A)", "A"),
  ("hasZZ", "$(call tt.has?,ZZ)", ""),
  ("all", "$(tt.__all__)", "A B C"),
]

# A dispatch table whose values are handler names, with a default handler.
DISPATCH_VARS = [
  "$(call m5.table, dt, add=dh.add mul=dh.mul, dh.def)",
  "dh.add = A[$(1):$(2)]",
  "dh.mul = M[$(1):$(2)]",
  "dh.def = D[$(1)]",
]
DISPATCH_CASES = [
  ("dispAdd", "$(call dt.dispatch,add,3,4)", "A[3:4]"),
  ("dispMul", "$(call dt.dispatch,mul,3,4)", "M[3:4]"),
  ("dispDefault", "$(call dt.dispatch,zzz,3,4)", "D[3]"),
  ("callHit", "$(call dt.call,add,3,4)", "A[3:4]"),
  ("callDefault", "$(call dt.call,zzz,3,4)", "D[3]"),
]


@pytest.fixture(scope="module")
def table_out(amk, tmp_path_factory):
  return run(amk, tmp_path_factory.mktemp("m5table"), body(TABLE_VARS, TABLE_CASES))


@pytest.fixture(scope="module")
def dispatch_out(amk, tmp_path_factory):
  return run(amk, tmp_path_factory.mktemp("m5dtable"), body(DISPATCH_VARS, DISPATCH_CASES))


@pytest.mark.parametrize("key,expr,expected", TABLE_CASES, ids=[c[0] for c in TABLE_CASES])
def test_table_case(table_out, key, expr, expected):
  assert line(table_out, key) == f"{key}=[{expected}]", table_out


@pytest.mark.parametrize("key,expr,expected", DISPATCH_CASES, ids=[c[0] for c in DISPATCH_CASES])
def test_table_dispatch_case(dispatch_out, key, expr, expected):
  assert line(dispatch_out, key) == f"{key}=[{expected}]", dispatch_out
