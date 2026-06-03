local ngx_mock = {}

function ngx_mock.new(body)
  local state = { body = body or "", status = 200, output = {}, exited = nil }
  return {
    state = state,
    req = {
      read_body = function() end,
      get_body_data = function()
        return state.body
      end,
    },
    say = function(message)
      state.output[#state.output + 1] = message
    end,
    exit = function(code)
      state.exited = code
      return code
    end,
  }
end

return ngx_mock
