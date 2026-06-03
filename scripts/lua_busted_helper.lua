local helper = {}

local forbidden_patterns = {
  { name = "io", pattern = "%f[%w_]io%s*%." },
  { name = "os", pattern = "%f[%w_]os%s*%." },
  { name = "debug", pattern = "%f[%w_]debug%s*%." },
  { name = "require", pattern = "%f[%w_]require%s*%(" },
  { name = "loadfile", pattern = "%f[%w_]loadfile%s*%(" },
  { name = "dofile", pattern = "%f[%w_]dofile%s*%(" },
}

local function read_file(path)
  local handle, err = io.open(path, "rb")
  if not handle then
    error("LuaUnavailableError: " .. tostring(err))
  end
  local data = handle:read("*a")
  handle:close()
  return data
end

local function assert_sandboxed(source)
  for _, forbidden in ipairs(forbidden_patterns) do
    if source:find(forbidden.pattern) then
      error("LuaCapabilityForbiddenError")
    end
  end
end

local function sandbox_env()
  return {
    assert = assert,
    error = error,
    ipairs = ipairs,
    math = math,
    pairs = pairs,
    pcall = pcall,
    select = select,
    string = string,
    table = table,
    tonumber = tonumber,
    tostring = tostring,
    type = type,
    unpack = unpack,
    xf = xf,
  }
end

local function parse_fixture_json(data)
  local payload = {
    agent = data:match('"agent"%s*:%s*"([^"]+)"'),
    tool_name = data:match('"tool_name"%s*:%s*"([^"]+)"'),
    tool_input = {},
  }
  local input = data:match('"tool_input"%s*:%s*{(.-)}')
  if input then
    for key, value in input:gmatch('"([^"]+)"%s*:%s*"([^"]*)"') do
      payload.tool_input[key] = value
    end
  end
  return payload
end

local function load_chunk(source, chunk_name)
  assert_sandboxed(source)
  local chunk, err = loadstring(source, chunk_name)
  if not chunk then
    error("LuaUnavailableError: " .. tostring(err))
  end
  setfenv(chunk, sandbox_env())
  return chunk()
end

local function set_path(root, fn)
  local parts = {}
  for part in root:gmatch("[^.]+") do
    parts[#parts + 1] = part
  end
  local cursor = xf
  for index = 2, #parts - 1 do
    cursor[parts[index]] = cursor[parts[index]] or {}
    cursor = cursor[parts[index]]
  end
  cursor[parts[#parts]] = fn
end

function helper.reset()
  xf.fs = {}
  xf.redis = {}
  xf.tool_call = {}
  xf.advisor = {}
  xf.capabilities = {
    fs = xf.fs,
    redis = xf.redis,
    tool_call = xf.tool_call,
    advisor = xf.advisor,
  }
end

function helper.mock_capability(name, fn)
  set_path(name, fn)
end

function helper.load_script(path)
  return load_chunk(read_file(path), "@" .. path)
end

function helper.load_inline(source)
  return load_chunk(source, "@inline")
end

function helper.load_fixture(path)
  local data = read_file(path)
  if path:match("%.json$") then
    return parse_fixture_json(data)
  end
  return data
end

function helper.now_ms()
  return math.floor(os.clock() * 1000)
end

xf = xf or {}
xf.test = helper
helper.reset()

function property(name, fn)
  local caller_env = getfenv(2)
  local it_fn = caller_env.it or rawget(_G, "it")
  if not it_fn then
    error("LuaUnavailableError: busted it() is not available")
  end
  it_fn(name, function()
    local samples = {
      "",
      "plain text",
      "click here",
      "[QUOTE]hidden[/QUOTE] visible",
      "a longer destination title with more than twelve words for trimming checks",
    }
    for _, sample in ipairs(samples) do
      if not fn(sample, "content for " .. sample) then
        error("property failed for sample: " .. tostring(sample))
      end
    end
  end)
end
