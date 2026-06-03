-- LuaJIT 2.1 dialect check helper. Run as: luajit scripts/check_lua_dialect.lua file.lua ...
local forbidden = {
  { pattern = "%f[%w]goto%f[%W]", reason = "goto is not allowed in the project Lua dialect" },
  { pattern = "%f[%w]__close%f[%W]", reason = "Lua 5.4 to-be-closed variables are forbidden" },
  { pattern = "%f[%w]utf8%f[%W]", reason = "Lua 5.3 utf8 library is forbidden" },
  { pattern = "[^%.]//", reason = "Lua 5.3 integer division is forbidden" },
  { pattern = "[^%w_]~[&|]?", reason = "Lua 5.3 bitwise operators are forbidden; use LuaJIT bit library" },
}

local failed = false
for _, path in ipairs(arg) do
  local fh = assert(io.open(path, "rb"))
  local text = fh:read("*a")
  fh:close()
  for _, rule in ipairs(forbidden) do
    if text:find(rule.pattern) then
      io.stderr:write(path .. ": " .. rule.reason .. "\n")
      failed = true
    end
  end
end

if failed then
  os.exit(1)
end
