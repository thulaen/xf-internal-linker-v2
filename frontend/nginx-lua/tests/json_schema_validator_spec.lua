describe("json_schema_validator", function()
  local handle

  before_each(function()
    handle = xf.test.load_script("frontend/nginx-lua/json_schema_validator.lua").handle
    ngx = xf.test.load_script("frontend/nginx-lua/tests/ngx_mock.lua").new("{}")
  end)

  after_each(function()
    ngx = nil
    xf.test.reset()
  end)

  it("accepts valid webhook payload", function()
    local result = handle('{"event_type":"push"}', {})
    assert.are.equal(0, result.status)
    assert.are.equal("", result.stderr)
  end)

  it("rejects malformed JSON with 400", function()
    local result = handle("bad", {})
    assert.are.equal(400, result.status)
  end)

  it("rejects nil payloads with 400", function()
    local result = handle(nil, {})
    assert.are.equal(400, result.status)
    assert.matches("malformed", result.error)
  end)

  it("rejects missing required field with 400", function()
    local result = handle('{"id":1}', {})
    assert.are.equal(400, result.status)
    assert.matches("event_type", result.error)
  end)

  it("emits LuaUnavailableError when schema file missing", function()
    local result = handle('{"event_type":"push"}', nil)
    assert.are.equal(503, result.status)
    assert.matches("LuaUnavailableError", result.error)
  end)
end)
