"""Pins a guest server inside make: micropy serves TCP from a recipe and answers each request by expanding make.

Pinned: the server listens while the recipe runs, a request reaches lua, js, and s7 functions
through amk.expand, and a goal chain fed per request answers fresh for each input in one
process. demos/json-rpc.mk shows the same pieces over HTTP; this file does not read it.
"""

import json
import socket
import subprocess
import time

import pytest

from conftest import popen

pytestmark = [pytest.mark.integration, pytest.mark.engines("lua", "s7", "micropy", "js")]

makefile = r'''
goal.dir := goals

@lua.import
define lua.methods
  function add(a, b) return tonumber(a) + tonumber(b) end
endef

@js.import
define js.methods
  function shout(s) { return s.toUpperCase() + "!"; }
endef

@s7.import
define s7.methods
  (define (fact n) (let loop ((n (string->number n)) (acc 1)) (if (< n 2) acc (loop (- n 1) (* n acc)))))
endef

@lua.import.target
define sorted
  local xs = {}
  for x in ("@nums.txt@"):gmatch("%S+") do xs[#xs + 1] = tonumber(x) end
  table.sort(xs)
  print(table.concat(xs, " "))
endef

@s7.import.target
define total
  (format #t "~A" (apply + (list @sorted@)))
endef

$(goal.dir)/nums.txt: ;

rpc.add = $(add $1,$2)
rpc.shout = $(shout $1)
rpc.fact = $(fact $1)
rpc.stats = $(file >$(goal.dir)/nums.txt,$1)$(goal sorted)/$(goal total)

@micropy.import
define rpc.server
  import amk, asyncio, json

  async def _handle(reader, writer):
    while True:
      line = await reader.readline()
      if not line:
        break
      q = json.loads(line)
      params = [" ".join(map(str, p)) if isinstance(p, list) else str(p) for p in q["params"]]
      result = amk.call("rpc." + q["method"], *params)
      writer.write(json.dumps({"id": q["id"], "result": result}).encode() + b"\n")
      await writer.drain()
    writer.close()
    await writer.wait_closed()

  async def _main(port):
    await asyncio.start_server(_handle, "127.0.0.1", int(port))
    while True:
      await asyncio.sleep(3600)

  def serve(port):
    asyncio.run(_main(port))
endef

serve:
	$(serve $(PORT))
'''


@pytest.fixture
def server(amk, tmp_path, free_port):
  """The makefile's serve recipe, running until the test ends, and a connection to it."""
  (tmp_path / "serve.mk").write_text(makefile)
  proc = popen(amk, ["-s", "-f", "serve.mk", "serve", f"PORT={free_port}"], cwd=tmp_path,
               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  deadline, conn = time.time() + 60, None
  while conn is None:
    if proc.poll() is not None:
      pytest.fail(f"the server exited {proc.returncode} before listening: {proc.stdout.read().decode()[-2000:]}")
    if time.time() > deadline:
      proc.kill()
      pytest.fail("the server never listened")
    try:
      conn = socket.create_connection(("127.0.0.1", free_port), timeout=30)
    except OSError:
      time.sleep(0.1)
  stream = conn.makefile("rwb")
  ids = iter(range(1, 1000))

  def call(method, *params):
    n = next(ids)
    stream.write(json.dumps({"id": n, "method": method, "params": list(params)}).encode() + b"\n")
    stream.flush()
    reply = json.loads(stream.readline())
    assert reply["id"] == n, reply
    return reply["result"]

  yield call
  conn.close()
  proc.kill()
  proc.wait(timeout=30)


def test_a_request_reaches_a_function_in_each_language(server):
  assert server("add", 40, 2) == "42"
  assert server("shout", "hi") == "HI!"
  assert server("fact", 20) == "2432902008176640000"


def test_a_goal_chain_answers_fresh_for_each_request(server):
  assert server("stats", [3, 1, 4, 1, 5]) == "1 1 3 4 5/14"
  assert server("stats", [30, 10, 20]) == "10 20 30/60"
  assert server("stats", [3, 1, 4, 1, 5]) == "1 1 3 4 5/14"
