# C ABI Wrapper Standard

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Sources

- Microsoft Learn documents `extern "C"` and DLL export decoration for C-compatible exports: https://learn.microsoft.com/en-us/cpp/build/exporting-c-functions-for-use-in-c-or-cpp-language-executables
- Microsoft Learn documents `__declspec(dllexport)` / `__declspec(dllimport)` export attributes: https://learn.microsoft.com/en-us/cpp/cpp/dllexport-dllimport
- The Rust Reference documents panic behavior and FFI unwinding boundaries: https://doc.rust-lang.org/stable/reference/panic.html
- The Go cgo documentation covers `runtime/cgo.Handle` and cgo boundary rules: https://pkg.go.dev/cmd/cgo and https://go.dev/wiki/cgo
- The GHC User Guide documents `ccall`, `unsafe`, `safe`, and `interruptible` foreign calls: https://ghc.gitlab.haskell.org/ghc/doc/users_guide/exts/ffi.html

## Behavior

Given a native library is consumed across Python, Go, Haskell, Rust, or Lua,
When the library exposes a public boundary,
Then it must expose one flat C ABI header with versioned structs, status-code
returns, explicit export macros, prefixed symbols, and no language-native types
crossing the boundary.

## Rules

- Public C ABI headers live under `backend/extensions/**/include/xf_*.h` or an equivalent service-local `include/xf_*.h`.
- Every public struct starts with `uint32_t abi_size;` followed by `uint32_t abi_version;`.
- Every exported function uses `XF_API`, a symbol name beginning with `xf_`, and `XF_NOEXCEPT`.
- Functions that can fail return `xf_status_t`; error text is retrieved by a separate exported function.
- C++ classes, templates, STL containers, exceptions, and RTTI never cross the boundary.
- Rust C ABI exports use `#[repr(C)]`, `extern "C"`, and abort-on-panic behavior.
- PyBind11 and inline-c-cpp are forbidden for new or migrated native boundaries.


[SPEC CITED: feature=fr-c-abi-wrapper-standard kind=technical_doc id=https://learn.microsoft.com/en-us/cpp/build/exporting-c-functions-for-use-in-c-or-cpp-language-executables verified_at=2026-06-02]
