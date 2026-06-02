# Agent Code Standards Middleware

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]
[SPEC CITED: feature=agent-code-standards-middleware kind=technical_doc id=https://www.lua.org/manual/5.1/ verified_at=2026-05-26]
[SPEC CITED: feature=agent-code-standards-middleware kind=technical_doc id=https://luajit.org/running.html verified_at=2026-05-26]
[SPEC CITED: feature=agent-code-standards-middleware kind=technical_doc id=https://platform.openai.com/docs/guides/structured-outputs?api-mode=chat verified_at=2026-05-26]
[SPEC CITED: feature=agent-code-standards-middleware kind=technical_literature id=978-0321146533-Beck-2002 verified_at=2026-05-26]

## Goal

Give Codex, Claude, Gemini, and future agents one shared host-owned middleware
for code-related model calls.

The host owns all decisions that affect the model call. Lua is a hot-reloadable
validator that returns a simple result. Lua does not stop the call, hide the
answer, or run the retry.

## Sources Of Truth

| Area | Source | Design decision |
|---|---|---|
| Lua pattern checks | Lua 5.1 reference manual | Use simple Lua string pattern matching for code-block and function-name checks. |
| Lua runtime | LuaJIT running guide | Run the validator through LuaJIT 2.1, matching the repo's Lua runtime rule. |
| Structured host result | OpenAI structured outputs documentation | Keep the host result schema explicit: valid flag, reasons, original response, and optional retry instruction. |
| Test-first workflow | Beck 2002, Test-Driven Development | The middleware must ask for tests before implementation and must itself be added with focused tests first. |

## Behavior

Given an agent prompt is code-related,
When the host prepares the outgoing model request,
Then it appends the system constraints for TDD, KISS, and DRY exactly once.

Given an agent prompt is not code-related,
When the host prepares the outgoing model request,
Then it leaves the system prompt unchanged.

Given a model response contains implementation code before test code,
When the host validates the response through Lua,
Then Lua returns `valid=false` with a reason and the host creates a retry
instruction.

Given Lua returns `valid=false`,
When the host handles the validation result,
Then the host shows the original response to the user and may make one
corrective model call. Lua does not own that retry.

## Required Files

- `apps/governance/agent_middleware/code_standards.py` owns host request and
  response helpers.
- `apps/governance/lua_runtime/advisors/validate_code_standards.lua` owns the
  hot-reloadable validation rule.
- `tests/test_agent_code_standards_middleware.py` checks the host helpers.
- `apps/governance/lua_runtime/advisors/tests/validate_code_standards_spec.lua`
  checks the Lua rule.

## Safety Rules

- The Lua validator must use the existing sandbox subset. It may not call direct
  `io`, `os`, `debug`, `require`, `loadfile`, or `dofile`.
- The host may call LuaJIT through a tiny driver and may decide whether to retry.
- Retry attempts must be bounded by the caller. This first slice only returns
  the retry instruction and does not create an unbounded loop.
