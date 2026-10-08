-- actor/init.lua: amk.actor for lua, the handle a bound member reads its group through, answering from the group's data as it is now.
local json = require("dkjson")

local function data(group)
  return json.decode(amk.call(group .. ".get", "."))
end

-- One member's view of its group: its id, the config, its siblings' entries now, the mailbox verbs as itself, and every member's entry under its id.
local function on(group, id)
  local H = { id = id }
  function H.siblings()
    local t = {}
    for k, entry in pairs(data(group).children) do
      if k ~= id then t[k] = entry end
    end
    return t
  end
  function H.cast(to, msg) return amk.call(group .. ".cast", to, msg) end
  function H.recv() return amk.call(group .. ".recv", id) end
  function H.ask(to, msg) return amk.call(group .. ".ask", id, to, msg) end
  function H.reply(req, answer) return amk.call(group .. ".reply", req, answer) end
  return setmetatable(H, { __index = function(_, k)
    local d = data(group)
    if k == "config" then return d end
    return d.children[k]
  end })
end

-- The define name as a make function: its body compiled with the group's handle as a local of the group's name, and as __group__.
local function bind(group, name)
  local body = assert(load("local " .. group .. ", __group__ = ...\n" .. amk.var.raw[name], "=" .. name))
  amk.func(name, function()
    local h = on(group, name)
    local answer = body(h, h)
    return answer == nil and "done" or tostring(answer)
  end)
end

return { on = on, bind = bind }
