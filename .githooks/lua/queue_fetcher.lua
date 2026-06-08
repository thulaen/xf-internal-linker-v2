local queue_fetcher = {}

function queue_fetcher.run(xf_cap)
  local depth, err = xf_cap.redis.eval("return queue_depth")
  if not depth then
    return { exit_code = 1, error = err or "LuaRedisUnavailableError" }
  end
  return { exit_code = 0, output = tostring(depth) }
end

return queue_fetcher
