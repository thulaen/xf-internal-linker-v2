# C++ Extension Rules — No Exceptions

Every AI agent (Claude, Codex, Gemini, etc.) writing C++ in this repo must follow these rules. Every human reviewer must enforce them. No rule may be skipped "because it's just a small extension."

**Before writing any C++ extension, read this file top to bottom.**

---

## 1. Mandatory Compiler Flags

Every extension in `setup.py` must compile with ALL of these:

```
-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror
-Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion
-Wnull-dereference -Wformat=2 -Wimplicit-fallthrough
-fno-exceptions           # pybind11 handles exceptions at the boundary
-fno-rtti                 # no dynamic_cast inside extensions
```

On Windows: `/std:c++17 /O2 /arch:AVX2 /W4 /WX /sdl`

For testing builds, add: `-fsanitize=address,undefined -fno-omit-frame-pointer`

**No pragma to disable warnings. No `-Wno-*` flags. Fix the code instead.**

---

## 2. Threading Rules

### Priority Inversion
- Never hold a `std::mutex` while calling into Python (GIL inversion).
- If two locks are needed, always acquire in alphabetical order by variable name.
- Use `std::scoped_lock(a, b)` for multi-lock acquisition — never nested `lock_guard`.

### Spurious Wakeups
- Every `condition_variable::wait()` must use the predicate overload:
  ```cpp
  cv.wait(lock, [&]{ return ready; });  // CORRECT
  // cv.wait(lock);                     // FORBIDDEN — spurious wakeup bug
  ```

### Missing Memory Barriers
- Atomic operations that communicate between threads must use `memory_order_acquire` / `memory_order_release` pairs at minimum.
- `memory_order_relaxed` is only allowed for counters that are read for diagnostics (never for correctness).
- `memory_order_seq_cst` is forbidden in hot paths (too expensive) — use acquire/release.
- Every atomic flag or counter must have a comment explaining its ordering choice.

### Volatile Misuse
- `volatile` is forbidden. It does not provide thread safety. Use `std::atomic` instead.
- The only exception: memory-mapped I/O registers (which we never use).

### ABA Problem
- Never use raw compare-and-swap on pointers without a generation counter.
- Preferred: `std::atomic<std::pair<T*, uint64_t>>` or tagged pointers.
- Lock-free data structures must document their ABA prevention strategy.

### Thread Pool Exhaustion
- Every `worksteal_pool` task must have a timeout (`max_task_ms = 5000`).
- Pool size = `std::thread::hardware_concurrency()` — never more.
- Queue depth hard cap: 10,000 items. Reject beyond that with an error, never block.

### Unjoined Threads
- `std::thread` objects must be joined or detached before destruction.
- Preferred: use `std::jthread` (C++20) which auto-joins, or wrap in RAII.
- **Never call `std::thread::detach()`** — detached threads are unmonitorable.

### Condition Variable Lost Wakeups
- Always set the predicate flag **before** calling `notify_one()` / `notify_all()`.
- Always check the predicate **after** acquiring the lock in the waiter.

### Mutex Recursive Locking
- `std::recursive_mutex` is forbidden. If you think you need it, refactor.

### Read-Write Lock Starvation
- `std::shared_mutex` writers must not starve. Use a writer-priority wrapper or fairness ticket lock if write latency matters.

### Spinlock CPU Usage
- Spinlocks must use `_mm_pause()` (x86) in the spin loop.
- Spin count limit: 1000 iterations, then fall back to `std::mutex`.

### Thread-Local Storage
- `thread_local` variables must not hold heap allocations that outlive the thread.
- Prefer stack allocation or arena-per-thread patterns.

---

## 3. Memory Rules

### Pointer Arithmetic
- Raw pointer arithmetic is forbidden outside of SIMD intrinsic blocks.
- Use `std::span<T>` (C++20) or pass `(T* data, size_t len)` pairs with bounds checking.
- Every array access: `assert(idx < len)` in debug builds.

### Unaligned Access
- SIMD loads must use `_mm256_loadu_ps` (unaligned) unless the buffer is guaranteed aligned via `posix_memalign` or `_mm_malloc`.
- If aligned: document the alignment guarantee with a comment and `assert(reinterpret_cast<uintptr_t>(ptr) % 64 == 0)`.

### Stack Overflow
- No VLA (variable-length arrays). They are non-standard C++ and blow the stack.
- No `alloca()`. Use `std::vector` or arena allocation.
- Recursive functions must have a depth limit and use iterative fallback.

### Heap Fragmentation
- Hot-path allocations: use arena/pool/slab allocators (OPT-07 to OPT-12).
- Never call `new` / `delete` inside a per-candidate scoring loop.
- Prefer `std::vector::reserve()` upfront over repeated `push_back()` growth.

### Custom Allocator Bugs
- Every custom allocator must implement `deallocate()` that is safe to call on any pointer returned by `allocate()`.
- Every allocator must survive: double-free (assert + no-op), zero-size alloc (return non-null), max-size alloc (throw `std::bad_alloc`).

### Missing Array Delete
- `new[]` must pair with `delete[]`. `new` must pair with `delete`.
- Preferred: never use raw `new` / `delete`. Use `std::vector`, `std::unique_ptr<T[]>`, or arena allocation.

### Deleting Void Pointers
- `delete` on `void*` is undefined behaviour. Forbidden.
- If type-erased storage is needed, use `std::any` or a destructor callback.

### Copy-on-Write Buffer Rules
- COW buffers (OPT-09) must use atomic reference counting.
- The copy path must deep-copy the entire buffer, not just the header.

### RAII Wrappers
- Every system resource (file descriptor, socket, mmap handle, GPU buffer) must be wrapped in an RAII class.
- No raw `open()` / `close()` pairs. No raw `malloc()` / `free()` pairs.
- Destructor must be `noexcept` and must release the resource unconditionally.

---

## 4. Object Lifetime Rules

### Self-Assignment
- Every `operator=` must handle `this == &other` safely.
- Preferred: use copy-and-swap idiom.

### Shallow Copies
- Classes owning heap memory must either: delete copy ctor/assign (`= delete`), or implement deep copy.
- Default copy is only acceptable for POD/trivially-copyable types.

### String View Dangling
- `std::string_view` must never outlive the `std::string` it points to.
- Never return `std::string_view` from a function that creates a temporary string.
- Never store `std::string_view` as a class member unless the backing string's lifetime is documented and enforced.

### Returning Reference to Local
- Never return `const T&` or `T&` to a stack-local variable. Compiler warning `-Wreturn-local-addr` catches this — it's `-Werror` so it won't compile.

### Lambda Capture Dangling
- Lambdas stored beyond the current scope must capture by value (`[=]`) or by `std::shared_ptr`.
- `[&]` capture is only allowed for lambdas that execute synchronously in the same scope.

### Coroutine Lifetime (if used)
- Coroutine frames must not reference stack locals of the caller after the first suspension point.
- Coroutine handles must be wrapped in RAII (`std::unique_ptr` with custom deleter).
- **Current policy: coroutines are not used in this project.** If needed in future, get design review first.

---

## 5. Type Safety Rules

### Narrowing Conversions
- Forbidden. The compiler flag `-Wconversion -Werror` enforces this.
- Explicit `static_cast<T>()` required for every intentional narrowing.
- Every `static_cast` that narrows must have a comment explaining why it's safe.

### Signed-Unsigned Mismatch
- Loop indices: use `size_t` for container iteration, `int32_t` for counted loops with known bounds.
- Never compare signed and unsigned without explicit cast.
- `-Wsign-conversion -Werror` enforces this.

### Strict Aliasing Violations
- Never cast between unrelated pointer types (`float*` to `int*`).
- For type-punning: use `std::memcpy` or `std::bit_cast` (C++20). Never union-based type punning (UB in C++).
- The `-fno-strict-aliasing` flag is forbidden — fix the code instead.

### Loss of Precision
- `double` to `float` conversion requires explicit `static_cast<float>()`.
- Accumulations (sums, dot products): use `double` internally, convert to `float` at the end.

### Unhandled Switch Cases
- Every `switch` on an enum must have all cases handled or a `default: assert(false);`.
- `-Wimplicit-fallthrough` is enabled — every intentional fallthrough needs `[[fallthrough]];`.

### Missing `explicit` Keyword
- Every single-argument constructor must be `explicit` unless implicit conversion is intentionally designed (document why).

### `std::optional` Bad Access
- Never dereference `std::optional` without checking `has_value()` first.
- Preferred: use `value_or(default)` for simple cases.

### `std::any` Cast Failure
- Every `std::any_cast` must be wrapped in try-catch or use the pointer overload (returns `nullptr` on mismatch).

---

## 6. Template & Compilation Rules

### Template Bloat
- Templates with more than 2 type parameters must be explicitly instantiated in the `.cpp` file for the types actually used.
- Never put template implementations in headers unless they are truly generic (used with 3+ types).

### Inlining Limits
- `inline` keyword is only for functions under 10 lines.
- `__attribute__((always_inline))` is forbidden — let the compiler decide beyond small helpers.
- `__attribute__((noinline))` is allowed for cold error-handling paths.

### `constexpr` Usage
- Every compile-time-computable constant must be `constexpr`.
- Lookup tables (OPT-59 sigmoid LUT, OPT-60 fast_log) must be `constexpr` arrays.

### Dead Code
- No commented-out code in merged files. Use version control instead.
- No `#if 0` blocks.

---

## 7. SIMD / AVX2 Rules

### SSE/AVX Transition Penalties
- Never mix SSE (`_mm_*`) and AVX (`_mm256_*`) intrinsics in the same function without `_mm256_zeroupper()` or `_mm256_zeroall()` at the transition.
- Preferred: use only AVX2 intrinsics in hot paths. SSE is allowed in scalar fallback only.

### Unaligned SIMD Loads
- Default to `_mm256_loadu_ps` / `_mm256_storeu_ps` (unaligned).
- Only use `_mm256_load_ps` when alignment is guaranteed and asserted.

### Register Spilling
- SIMD functions should use at most 12 YMM registers to avoid spills.
- If a function needs more, split it into two functions.

### Auto-Vectorization
- For simple loops, prefer writing scalar code with `#pragma omp simd` or letting `-O3 -march=native` auto-vectorize.
- Only hand-write intrinsics when benchmarks show auto-vectorization failed.
- Add a comment: `// hand-vectorized because auto-vec produced X, benchmark shows Y`.

### Cache Line Splits
- Structures accessed in SIMD loops must not straddle cache line boundaries.
- Use `alignas(64)` on hot arrays.

---

## 8. Floating Point Rules

### Denormalized Float Penalties
- Set flush-to-zero and denormals-are-zero at extension init:
  ```cpp
  _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
  _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
  ```

### NaN Propagation
- Every function that accepts float input must check for NaN/Inf at the entry point:
  ```cpp
  if (!std::isfinite(value)) throw std::invalid_argument("NaN/Inf input");
  ```
- NaN must never silently propagate through a scoring pipeline.

### Floating Point Accumulation
- Dot products and sums over >100 elements must use Kahan compensated summation or `double` accumulator.
- Never accumulate `float` values in a `float` register for long reductions.

### FPU Control Word
- Never change the FPU rounding mode globally. If needed for a specific operation, save and restore.

---

## 9. Performance Anti-Pattern Rules

### RVO / NRVO Failure
- Return local objects by value — the compiler applies Return Value Optimisation.
- Never `return std::move(local_object);` — this **prevents** NRVO. Just `return local_object;`.

### `std::move` on Const
- `std::move(const_object)` does nothing (it's still a copy). Never do this.

### Pessimizing Moves
- Never `std::move()` in a `return` statement when the object is a local or parameter.

### Forwarding Reference Misuse
- `std::forward<T>` only inside `template<typename T> void f(T&& arg)`.
- Never `std::forward` on an lvalue reference.

### Temporary Object Creation
- String concatenation in loops: use `std::string::reserve()` + `append()`, never `operator+` repeatedly.
- Prefer `std::string_view` parameters over `const std::string&` when no ownership transfer.

### `std::endl` Flushing
- Forbidden in hot paths. Use `'\n'` instead. `std::endl` forces a buffer flush every time.

### `std::function` Allocation
- `std::function` heap-allocates for large callables. In hot paths, use template parameters or function pointers instead.

### `dynamic_cast` Overhead
- Forbidden (we compile with `-fno-rtti`). Use static dispatch or `enum`-based variant.

### Regex Compilation
- `std::regex` must be compiled once (`static const std::regex re(...)`) and reused.
- Never compile a regex inside a loop.

### Hash Function Quality
- `std::unordered_map` with integer keys: use a mixing hash (e.g., `splitmix64`), not the identity hash.
- `std::unordered_map` with string keys: use `std::hash<std::string>` (acceptable) or `xxHash` for large maps.

---

## 10. Container Rules

### `std::vector` Overallocation
- Always `reserve()` before a known-size fill loop.
- After bulk removal, call `shrink_to_fit()` if the vector will live for a long time.

### `std::unordered_map` Bucket Collisions
- Set `max_load_factor(0.7)` on construction.
- For maps over 100K entries, prefer `robin_map` (OPT-13) or `absl::flat_hash_map`.

### `std::shared_ptr` Control Block
- Every `shared_ptr` allocates a control block. Prefer `std::unique_ptr` unless shared ownership is truly needed.
- Use `std::make_shared<T>()` (single allocation) instead of `std::shared_ptr<T>(new T)` (two allocations).

### Circular `shared_ptr` References
- If two objects point to each other, one must use `std::weak_ptr`.
- Every `shared_ptr` cycle must be documented with a comment.

### Unbounded Queue Growth
- Every queue (`ring_queue`, work-steal deque, etc.) must have a capacity limit.
- When full: drop oldest, reject new, or block — never grow unbounded.

---

## 11. Error Handling Rules

### Exception Safety
- Every function must provide at least the **basic guarantee** (no resource leaks on throw).
- Functions that modify shared state must provide the **strong guarantee** (rollback on throw) or be marked `noexcept`.

### Throwing from Destructors
- Forbidden. Destructors must be `noexcept`. Period.

### Catching by Value
- Catch exceptions by `const&`, never by value (avoids slicing).
  ```cpp
  catch (const std::exception& e) { ... }  // CORRECT
  // catch (std::exception e) { ... }       // FORBIDDEN — slicing
  ```

### pybind11 Boundary
- C++ exceptions are caught at the pybind11 boundary and converted to Python exceptions.
- Inside pure C++ code: use return codes or `std::expected` (C++23) / `std::optional` for expected failures.
- `throw` only for truly exceptional conditions (bad input, OOM, invariant violation).

---

## 12. Build & Linking Rules

### DLL Boundary Memory
- Memory allocated in the extension must be freed in the extension. Never pass ownership to Python and expect Python to `free()` it.
- Use pybind11's buffer protocol (`py::buffer_info`) for zero-copy data exchange.

### Cyclic Dependencies
- Extensions must not `#include` headers from other extensions.
- Shared utilities go in a `common/` header-only directory.

### Symbol Visibility
- Only pybind11 module init symbols should be exported.
- All internal functions: `static` or in an anonymous namespace.

### Link-Time Optimisation
- LTO (`-flto`) is allowed but optional. Never rely on LTO for correctness.

---

## 13. I/O & System Rules

### File Descriptor Leaks
- Every `open()` / `fopen()` must be wrapped in RAII.
- Preferred: `std::ifstream` / `std::ofstream` which auto-close.

### Socket Leaks
- Same as file descriptors: RAII wrapper mandatory.

### `system()` Calls
- `system()` is forbidden. Command injection risk. Use `posix_spawn` or avoid entirely.

### Signal Handler Safety
- Signal handlers must only set `volatile sig_atomic_t` flags. No allocations, no I/O, no locks.

### Fork Safety
- Never `fork()` without immediate `exec()` in a multithreaded process.

---

## 14. Security Rules

### Format String Vulnerabilities
- Never pass user-provided strings as format arguments to `printf` / `snprintf`.
- Use `fmt::format()` or `std::format()` (C++20) which are type-safe.

### Credentials in Memory
- Never store API keys or passwords in C++ extension memory.
- If temporary sensitive data exists, `memset_s()` / `SecureZeroMemory()` before free.

### TOCTOU (Time-of-Check Time-of-Use)
- File existence checks followed by file opens: use `open()` with `O_CREAT | O_EXCL` atomically.

---

## 15. Cache & CPU Pipeline Rules

### TLB Misses
- Keep hot working sets under 2 MB (L2 cache) when possible.
- Struct-of-arrays (OPT-35) layout to keep hot fields contiguous.

### Instruction Cache Thrashing
- Keep hot functions under 4 KB of machine code.
- Cold error paths: `__attribute__((cold))` or `[[unlikely]]` to move them out of the hot path.

### Data Cache Thrashing
- Access arrays sequentially (stride-1) whenever possible. Random access patterns kill performance.
- Prefetch (OPT-55): `__builtin_prefetch(ptr + 16 * 64, 0, 1)` — 16 cache lines ahead, read-only, low locality.

### CPU Pipeline Stalls
- Avoid data-dependent branches in inner loops. Use branchless `cmov` patterns or SIMD masks.
- Store forwarding: ensure stores and loads to the same address use the same width.

### False Sharing
- Atomics and per-thread counters: pad to `std::hardware_destructive_interference_size` (64 bytes).
  ```cpp
  alignas(64) std::atomic<uint64_t> counter;
  ```

### NUMA Awareness
- For large allocations (>1 MB): document which NUMA node it targets.
- In Docker (our deployment): single-node, so NUMA is informational only.

---

## 16. Mandatory Pre-Merge Checklist

Every C++ extension PR must pass ALL of these before merge:

| Gate | Tool | Pass criteria |
|---|---|---|
| 1. Compiles clean | `setup.py build_ext` | Zero warnings with `-Werror -Wall -Wextra` |
| 2. Python reference parity | `pytest test_parity_*.py` | Output matches Python reference within 1e-4 |
| 3. AddressSanitizer | `ASAN=1 build + pytest` | Zero ASAN/UBSan errors |
| 4. Performance | `bench_extensions.py` | C++ is 3x+ faster than Python reference |
| 5. Edge cases | `pytest test_edges_*.py` | Empty input, single item, NaN/Inf, n=10000 all pass |
| 6. Valgrind (Linux) | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7. Thread safety | `TSAN=1 build + pytest` | Zero ThreadSanitizer data races (for threaded extensions) |
| 8. Code review | Human reviewer | Confirms all rules in this file are followed |

---

## 17. Forbidden Patterns — Quick Reference

| Pattern | Why | Fix |
|---|---|---|
| `volatile` | Not thread-safe | `std::atomic` |
| `new` / `delete` in hot path | Heap fragmentation | Arena / pool allocator |
| `std::recursive_mutex` | Design smell | Refactor lock hierarchy |
| `std::thread::detach()` | Unmonitorable | `std::jthread` or join |
| `dynamic_cast` | RTTI disabled | Static dispatch |
| `alloca()` / VLA | Stack overflow | `std::vector` |
| `std::endl` in loops | Flushes every time | `'\n'` |
| `return std::move(x)` | Prevents RVO | `return x;` |
| `catch (Exception e)` | Slicing | `catch (const Exception& e)` |
| `#pragma warning(disable:...)` | Hides bugs | Fix the warning |
| Raw `system()` call | Injection risk | `posix_spawn` or avoid |
| `printf(user_string)` | Format string vuln | `fmt::format(user_string)` |
| `std::function` in hot loop | Heap alloc per call | Template parameter |
| `memory_order_relaxed` for sync | Missing barrier | `acquire` / `release` |
| Mixing SSE + AVX | Transition penalty | AVX2 only, or `zeroupper` |
| `float` accumulator for sums | Precision loss | `double` accumulator |
