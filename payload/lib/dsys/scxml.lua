-- dsys/scxml.lua: an scxml document, parsed by lxsc, written as the machine config dsys/fsm takes, with a list of what the config cannot carry.
local json = require("dkjson")
local LXSC = require("lxsc")

local M = {}

local function object(t)
  return setmetatable(t or {}, { __jsontype = "object" })
end

-- A state's absolute id under the machine: its ancestors' ids and its own, dotted.
local function path(s, machine)
  local ids = {}
  while s and s ~= machine.root do
    table.insert(ids, 1, s.id)
    s = rawget(s, "parent")
  end
  return "#" .. machine.name .. "." .. table.concat(ids, ".")
end

-- Ids as written, each an absolute id where the document has it: one as a string, several as a list.
local function targets_of(text, by, machine)
  local targets = {}
  for id in string.gmatch(text or "", "[^%s]+") do
    table.insert(targets, by[id] and path(by[id], machine) or id)
  end
  if #targets == 1 then return targets[1] end
  if #targets > 1 then return targets end
  return nil
end

-- The attribute as written, the initial element's target, or the first child in document order.
local function initial_of(s, by, machine)
  local init = rawget(s, "initial")
  if type(init) ~= "string" then
    for _, c in ipairs(s.states or {}) do
      if c._kind == "initial" and c.transitions[1] then init = rawget(c.transitions[1], "_target") end
    end
  end
  return targets_of(init, by, machine) or (s.reals[1] and s.reals[1].id) or nil
end

-- One entry under on: its targets, and its cond as the guard's name, a state test as that state's path.
local function entry(t, by, machine)
  local e = object()
  e.target = targets_of(rawget(t, "_target"), by, machine)
  local cond = rawget(t, "cond")
  if cond then
    local id = cond:match("^In%('([^']+)'%)$")
    e.guard = id and by[id] and ("@" .. (path(by[id], machine):gsub("^#[^.]*%.", ""))) or cond
  end
  return e
end

-- An scxml descriptor as xstate keys: a name takes its own name and every name under it, a done event names its state's path.
local function descriptor(ev, by, machine)
  if ev == "*" or ev:sub(-2) == ".*" then return { ev } end
  local id = ev:match("^done%.state%.(.+)$")
  if id and by[id] then ev = "done.state." .. path(by[id], machine):gsub("^#[^.]*%.", "") end
  return { ev, ev .. ".*" }
end

-- A state's children as the config lists them: lxsc's real ones and its history states.
local function children(s)
  local out = {}
  for _, c in ipairs(s.states or {}) do
    if c._kind ~= "initial" then table.insert(out, c) end
  end
  return out
end

-- The kinds of executable content in a list of elements, each once, in document order.
local function kinds(items)
  local seen, out = {}, {}
  for _, item in ipairs(items or {}) do
    for _, x in ipairs(rawget(item, "_exec") or rawget(item, "_kids") or { item }) do
      local k = rawget(x, "_kind")
      if k and not seen[k] then
        seen[k] = true
        table.insert(out, k)
      end
    end
  end
  return #out > 0 and (" (" .. table.concat(out, " ") .. ")") or ""
end

-- What the config cannot carry of one state, named for the report.
local function drops(s, who, dropped)
  if #(rawget(s, "_datamodels") or {}) > 0 then table.insert(dropped, "datamodel" .. (who and " of " .. who or "")) end
  if not who then return end
  if #(rawget(s, "_onentrys") or {}) > 0 then table.insert(dropped, "onentry of " .. who .. kinds(s._onentrys)) end
  if #(rawget(s, "_onexits") or {}) > 0 then table.insert(dropped, "onexit of " .. who .. kinds(s._onexits)) end
  if #(rawget(s, "_invokes") or {}) > 0 then table.insert(dropped, "invoke in " .. who) end
  for _, t in ipairs(s.transitions or {}) do
    if #(rawget(t, "_exec") or {}) > 0 then table.insert(dropped, "content of a transition in " .. who .. kinds({ t })) end
  end
end

local function state(s, by, machine, dropped)
  local out = object()
  if s._kind == "final" then out.type = "final" end
  if s._kind == "parallel" then out.type = "parallel" end
  if s._kind == "history" then out.type = "history" end
  drops(s, s.id, dropped)
  local on = object()
  for _, t in ipairs(s.transitions or {}) do
    local events = rawget(t, "_event")
    if events then
      for ev in string.gmatch(events, "[^%s]+") do
        for _, key in ipairs(descriptor(ev, by, machine)) do
          on[key] = on[key] or {}
          table.insert(on[key], entry(t, by, machine))
        end
      end
    else
      out.always = out.always or {}
      table.insert(out.always, entry(t, by, machine))
    end
  end
  for ev, list in pairs(on) do
    if #list == 1 and not list[1].guard and type(list[1].target) == "string" then on[ev] = list[1].target end
  end
  if next(on) then out.on = on end
  if s.reals and #s.reals > 0 then
    out.states = object()
    for _, c in ipairs(children(s)) do out.states[c.id] = state(c, by, machine, dropped) end
    out.initial = initial_of(s, by, machine)
  end
  return out
end

-- Every state of the document by id.
local function index(s, by)
  for _, c in ipairs(s.states or {}) do
    if c.id then by[c.id] = c end
    index(c, by)
  end
  return by
end

-- The document as the config and the list of what it leaves out, in document order.
function M.read(text)
  local m = LXSC:parse(text)
  local name = rawget(m, "name")
  if name == "(lxsc)" then name = nil end
  name = name or "machine"
  local by = index(m, {})
  local machine = { root = m, name = name }
  local dropped = {}
  drops(m, nil, dropped)
  if rawget(m, "_script") then table.insert(dropped, "script") end
  local cfg = object({ id = name, initial = initial_of(m, by, machine), states = object() })
  for _, s in ipairs(children(m)) do cfg.states[s.id] = state(s, by, machine, dropped) end
  return cfg, dropped
end

-- The config as JSON, and the drops as a second value.
function M.convert(text)
  local cfg, dropped = M.read(text)
  return json.encode(cfg), dropped
end

-- A make variable holding a document: its config as JSON, with the drops reported on stderr under the variable's name.
function M.import(name)
  local cfg, dropped = M.convert(amk.var[name])
  if #dropped > 0 then
    io.stderr:write(name .. ": scxml leaves out " .. table.concat(dropped, ", ") .. "\n")
  end
  return cfg
end

return M
