describe("queue_fetcher", function()
  local run
  local redis

  before_each(function()
    run = xf.test.load_script(".githooks/lua/queue_fetcher.lua").run
    redis = { eval = function(script)
      assert.are.equal("return queue_depth", script)
      return 7
    end }
    xf.test.mock_capability("xf.redis.eval", redis.eval)
  end)

  after_each(function()
    xf.test.reset()
  end)

  it("reads queue depth from Redis without booting Django", function()
    local result = run({ redis = redis })
    assert.are.equal("7", result.output)
  end)

  it("exits 0 on success", function()
    local result = run({ redis = redis })
    assert.are.equal(0, result.exit_code)
  end)

  it("exits non-zero on Redis unavailable", function()
    redis.eval = function() return nil, "LuaRedisUnavailableError" end
    local result = run({ redis = redis })
    assert.is_not.equal(0, result.exit_code)
    assert.are.equal("LuaRedisUnavailableError", result.error)
  end)

  it("uses LuaRedisUnavailableError when Redis omits an error", function()
    redis.eval = function() return nil end
    local result = run({ redis = redis })
    assert.are.equal("LuaRedisUnavailableError", result.error)
  end)

  it("completes in under 100ms", function()
    local start_ms = xf.test.now_ms()
    run({ redis = redis })
    assert.is_true(xf.test.now_ms() - start_ms < 100)
  end)
end)
