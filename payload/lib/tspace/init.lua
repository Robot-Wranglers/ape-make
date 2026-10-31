-- tspace/init.lua: amk.tspace for lua, the tuple space of init.amk, whose formals in a pattern are lua's own type names, as type and math.type answer them, and "any"; nil is null.
local json = require("dkjson")

local formals = { any = "?", integer = "?int", float = "?float", number = "?number", string = "?str", boolean = "?bool", table = "?table", ["nil"] = "?null" }

local function call(space, verb, pattern, ...)
  local args = { space .. "." .. verb }
  for i = 1, select("#", ...) do
    local f = select(i, ...)
    args[#args + 1] = pattern and formals[f] or json.encode(f)
  end
  local found = {}
  for line in amk.call(table.unpack(args)):gmatch("[^\n]+") do
    found[#found + 1] = json.decode(line).t
  end
  return found
end

-- A field a handle lacks is the make function of that name under tspace, else the space of that name, as on answers it.
local on
local indexed = { __index = function(_, name)
  if amk["fxn?"]("tspace." .. name) == "1" then
    return function(...) return amk.call("tspace." .. name, ...) end
  end
  return on(name)
end }
function on(space)
  local S = setmetatable({ on = on }, indexed)
  function S.out(...) call(space, "out", false, ...) end
  function S.read(...) return call(space, "read", true, ...) end
  function S.inp(...) return call(space, "inp", true, ...)[1] end
  -- The blocking verbs, in_ for Linda's in since in is a keyword; the owner answers each once its condition holds.
  function S.in_(...) return call(space, "in", true, ...)[1] end
  function S.rd(...) return call(space, "rd", true, ...)[1] end
  function S.no(...) call(space, "no", true, ...) return true end
  -- The one-shot copies, the absence test as a boolean, the whole space, the bulk forms over tuples as tables, and the uniform forms.
  function S.rdp(...) return call(space, "rdp", true, ...)[1] end
  function S.nop(...) return (pcall(call, space, "nop", true, ...)) end
  function S.all() return call(space, "all", true) end
  function S.set(...) call(space, "set", false, ...) end
  function S.out_all(...) call(space, "out_all", false, ...) end
  function S.in_all(...) return call(space, "in_all", true, ...) end
  function S.urdp(...) return call(space, "urdp", true, ...)[1] end
  function S.uinp(...) return call(space, "uinp", true, ...)[1] end
  function S.urd(...) return call(space, "urd", true, ...)[1] end
  function S.uin(...) return call(space, "uin", true, ...)[1] end
  -- Handlers: register a make function by name with its pattern; list them; remove one by name.
  function S.out_s(...) call(space, "out_s", true, ...) end
  function S.rd_s() return call(space, "rd_s", true) end
  function S.in_s(name) return call(space, "in_s", false, name)[1] end
  return S
end

-- A routed field arrives as text; each type word reads it back as lua's own value.
local reads = {
  int = tonumber, float = tonumber, number = tonumber,
  bool = function(v) return v == "1" end, null = function() return nil end,
  list = json.decode, dict = json.decode, table = json.decode,
}

-- The define name as a make function: its body compiled with the space and the named fields as locals.
local function bind(space, name, spec)
  local fields, locals = {}, { space }
  for n, t in spec:gmatch("(%S+):(%S+)") do
    fields[#fields + 1] = { n, reads[t] }
    if n ~= "-" then locals[#locals + 1] = n end
  end
  local body = assert(load("local " .. table.concat(locals, ", ") .. " = ...\n" .. amk.var.raw[name], "=" .. name))
  amk.func(name, function(...)
    local args, k = { on(space) }, 1
    for i, f in ipairs(fields) do
      if f[1] ~= "-" then
        local v = select(i, ...)
        k = k + 1
        if f[2] then args[k] = f[2](v) else args[k] = v end
      end
    end
    body(table.unpack(args, 1, #locals))
    return ""
  end)
end

-- The verbs are make functions, so a makefile that never loaded the space fails here rather than at the first verb.
if amk.origin("tspace.spaces") == "undefined" then
  error("amk.tspace: the makefile has no tuple space; add load tspace", 0)
end

local default = on("tuplespace")
default.bind = bind
return default
