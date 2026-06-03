local json_schema_validator = {}

local function has_event_type(payload)
  return tostring(payload or ""):find('"event_type"%s*:') ~= nil
end

function json_schema_validator.handle(payload, schema)
  if not schema then
    return { status = 503, error = "LuaUnavailableError: schema file missing" }
  end
  local text = tostring(payload or "")
  if text:sub(1, 1) ~= "{" or text:sub(-1) ~= "}" then
    return { status = 400, error = "malformed JSON" }
  end
  if not has_event_type(text) then
    return { status = 400, error = "missing required field: event_type" }
  end
  return { status = 0, stderr = "" }
end

return json_schema_validator
