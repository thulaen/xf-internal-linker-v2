-- LuaJIT FFI smoke placeholder for C ABI headers.
local ok, ffi = pcall(function()
  return require("ffi")
end)

if not ok then
  error("LuaJIT FFI unavailable")
end

ffi.cdef[[
typedef unsigned int xf_status_t;
]]

print("lua-cross-language-smoke: ffi loaded")
