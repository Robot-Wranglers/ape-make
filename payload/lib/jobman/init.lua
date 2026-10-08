-- jobman/init.lua: amk.jobman for lua, the job functions with lua's own values and no pool, and a pool of jobs over them, a host plex: spawn takes a token of the pool before the fork, wait gives it back on reap and waits only on the pool's own members, kill, stop and resume signal a job, map runs goal lists under the bound, in order, stopping at the first failure when fail_fast is set, race answers the first of its lists to finish and ends the rest, and close ends every member.
local json = require("dkjson")

local function decode(t)
  if t == "" then return nil end
  return json.decode(t)
end

-- A spawn of a kind, through amk.job.spawn kind=what, which knows the kinds and refuses the rest: what as a table or as words, then opts.foreground and opts.stdout, or a call's argument; answers the pid.
local function spawn_kind(kind, what, opts)
  local args = { kind .. "=" .. (type(what) == "table" and table.concat(what, " ") or what) }
  if type(opts) == "table" then
    if opts.foreground then args[#args + 1] = "foreground=1" end
    if opts.stdout then args[#args + 1] = "stdout=" .. opts.stdout end
  elseif opts ~= nil then
    args[#args + 1] = tostring(opts)
  end
  return tonumber(amk.job.spawn(table.unpack(args)))
end
local function spawn(goals, opts) return spawn_kind("goals", goals, opts) end

-- spawn.<kind> names what is spawned; spawn called bare spawns goals.
local function by_kind(fn)
  return setmetatable({}, {
    __index = function(_, kind) return function(what, opts) return fn(kind, what, opts) end end,
    __call = function(_, what, opts) return fn("goals", what, opts) end,
  })
end

-- A wait answering the job's record as a table, or nil when block is false and none has finished.
local function wait(pid, block)
  if block == false then return decode(amk.job.wait(pid or "", "0")) end
  if pid then return decode(amk.job.wait(pid)) end
  return decode(amk.job.wait())
end

-- A job's record without consuming it, or nil while it runs.
local function peek(pid) return decode(amk.job.peek(pid)) end

-- Job control over a job of this process, true when the signal went.
local function kill(pid, sig)
  if sig then return amk.kill(pid, sig) == "1" end
  return amk.kill(pid) == "1"
end
local function stop(pid) return amk.stop(pid) == "1" end
local function resume(pid) return amk.resume(pid) == "1" end
local function foreground(pid) return amk.foreground(pid) == "1" end

local function on(pool)
  local P = { name = pool }
  local held = {}

  -- A record leaving the pool gives its token back; a stopped job keeps it.
  local function settle(r)
    if r and r.status ~= "stopped" and held[r.pid] then
      held[r.pid] = nil
      amk.pool.release(pool)
    end
    return r
  end

  -- The first of a set of members to report.
  local function among(pids, block)
    if #pids == 0 then return nil end
    local words = {}
    for i, pid in ipairs(pids) do words[i] = tostring(pid) end
    return settle(decode(amk.job.any(table.concat(words, " "), block == false and "0" or "")))
  end

  function P.pending()
    local pids = {}
    for pid in pairs(held) do pids[#pids + 1] = pid end
    table.sort(pids)
    return pids
  end

  P.spawn = by_kind(function(kind, what, opts)
    amk.pool.acquire(pool)
    local pid = spawn_kind(kind, what, opts)
    held[pid] = true
    return pid
  end)

  function P.wait(pid, block)
    if pid then return settle(wait(pid, block)) end
    return among(P.pending(), block)
  end

  P.peek = peek

  -- The module's job control, which takes no token; a killed job still holds its token until it is reaped.
  P.kill, P.stop, P.resume, P.foreground = kill, stop, resume, foreground

  function P.map(lists, opts)
    opts = opts or {}
    local fail_fast = opts.fail_fast
    if fail_fast == nil then fail_fast = amk.var["jobman." .. pool .. ".fail_fast"] == "true" end
    local results, slot, pids, stop = {}, {}, {}, false
    local function collect(r)
      local i = r and slot[r.pid]
      if i then
        slot[r.pid] = nil
        results[i] = r
        if fail_fast and r.status ~= "success" then stop = true end
      end
    end
    local function running()
      local out = {}
      for _, pid in ipairs(pids) do if slot[pid] then out[#out + 1] = pid end end
      return out
    end
    for i, goals in ipairs(lists) do
      while not stop and amk.pool.acquire(pool, "0") == "" do collect(among(running())) end
      if stop then break end
      local pid = spawn(goals, opts)
      held[pid] = true
      slot[pid] = i
      pids[#pids + 1] = pid
    end
    while next(slot) do collect(among(running())) end
    return results
  end

  -- The first of the lists to finish; the others are ended and reaped.
  function P.race(lists, opts)
    local mine, winner = {}, nil
    for _, goals in ipairs(lists) do
      if amk.pool.acquire(pool, "0") == "" then
        if #mine > 0 then winner = among(mine) break end
        amk.pool.acquire(pool)
      end
      local pid = spawn(goals, opts)
      held[pid] = true
      mine[#mine + 1] = pid
    end
    winner = winner or among(mine)
    for _, pid in ipairs(mine) do
      if held[pid] then kill(pid) resume(pid) settle(wait(pid)) end
    end
    return winner
  end

  -- Every member ended and reaped, its tokens given back; the records in pid order.
  function P.close()
    local records = {}
    for _, pid in ipairs(P.pending()) do
      kill(pid)
      resume(pid)
      records[#records + 1] = settle(wait(pid))
    end
    return records
  end

  return P
end

-- The module: the job verbs with no pool, on for a jobman, __jobs__, and any other pool's jobman by its name.
return setmetatable({
  spawn = by_kind(spawn_kind), wait = wait, peek = peek, kill = kill, stop = stop, resume = resume, foreground = foreground,
  on = on, __jobs__ = on("__jobs__"),
}, { __index = function(_, k) return on(k) end })
