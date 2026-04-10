# C# HttpWorker Rules — No Exceptions

Every AI agent (Claude, Codex, Gemini, etc.) writing C# in this repo must follow these rules. Every human reviewer must enforce them. No rule may be skipped "because it's just a small service."

**Before writing any C# code in the HttpWorker, read this file top to bottom.**

---

## 1. Null Safety

### Null Reference Exceptions
- Enable `<Nullable>enable</Nullable>` in every `.csproj`. Treat every nullable warning as an error.
- Never use `!` (null-forgiving operator) to silence a warning. Fix the root cause instead.
- Use pattern matching for null checks:
  ```csharp
  if (result is { } value) { /* safe */ }
  ```

### Improper Casting
- Never use direct casts `(MyType)obj` on objects that might not match. Use `as` + null check or pattern matching.
  ```csharp
  // FORBIDDEN — throws InvalidCastException
  var item = (ScanResult)obj;

  // CORRECT
  if (obj is ScanResult item) { /* use item */ }
  ```

### Type Checking Overhead
- Avoid repeated `is` checks. Check once, bind via pattern matching, reuse the variable.
- Never chain `obj is T` followed by `(T)obj`. The pattern match already gives you the typed variable.

---

## 2. Resource Management

### Un-Disposed IDisposable Objects
- Every `IDisposable` must be wrapped in `using` or `await using`. No exceptions.
  ```csharp
  await using var conn = new NpgsqlConnection(connString);
  ```
- If a class owns an `IDisposable` field, that class must implement `IDisposable` itself and dispose the field.

### Leaking Unmanaged Resources
- `NpgsqlConnection`, `NpgsqlCommand`, `NpgsqlDataReader`, `HttpClient` instances, `CancellationTokenSource` — all must be disposed.
- Never rely on the finalizer to clean up. Dispose deterministically.

### Finalizer Overhead
- Do not write finalizers (`~ClassName()`). They delay GC, promote objects to Gen 2, and hurt throughput.
- If you wrap an unmanaged handle, use `SafeHandle` instead of a finalizer.

### Memory Leaks via Event Handlers
- Every `+=` event subscription must have a corresponding `-=` unsubscription.
- Prefer weak event patterns or scoped lifetimes. In a worker service, if a handler lives as long as the service, document that explicitly.

### Static Dictionary Memory Leaks
- Never add entries to a `static Dictionary` or `static ConcurrentDictionary` without an eviction policy.
- Every static cache must have a max size and a removal strategy (LRU, TTL, or bounded count).

---

## 3. Memory & Allocation

### String Concatenation in Loops
- Forbidden. Use `StringBuilder` or `string.Join()`.
  ```csharp
  // FORBIDDEN
  string result = "";
  foreach (var url in urls) result += url + ",";

  // CORRECT
  var sb = new StringBuilder(urls.Count * 50);
  foreach (var url in urls) sb.Append(url).Append(',');
  ```

### Boxing and Unboxing Overhead
- Never store value types in `object`, `ArrayList`, or non-generic collections.
- Watch for hidden boxing: `string.Format("{0}", myInt)` boxes the int. Use interpolation or `.ToString()`.

### Boxing in Non-Generic Collections
- `ArrayList`, `Hashtable`, and `System.Collections.Queue` are forbidden. Use `List<T>`, `Dictionary<TKey,TValue>`, `Queue<T>`.

### Excessive Boxing in String.Format
- Prefer string interpolation `$"Score: {score}"` over `string.Format("Score: {0}", score)`.
- For hot paths, use `score.ToString()` to avoid boxing entirely.

### LOH Fragmentation
- Arrays larger than 85,000 bytes land on the Large Object Heap. Avoid frequent allocation and deallocation of large arrays.
- Use `ArrayPool<T>.Shared.Rent()` / `Return()` for temporary large buffers.
  ```csharp
  var buffer = ArrayPool<byte>.Shared.Rent(128_000);
  try { /* use buffer */ }
  finally { ArrayPool<byte>.Shared.Return(buffer); }
  ```

### Excessive Garbage Generation
- In hot loops (URL scanning, score calculation): zero allocations. Pre-allocate, pool, or use `Span<T>` / `stackalloc`.
- Avoid LINQ in hot paths — it allocates enumerators and delegates per call.

### Hidden Allocations in LINQ
- Every LINQ method (`Select`, `Where`, `ToList`) allocates. In cold paths this is fine. In per-URL scoring, use `for` loops.
- `ToList()` and `ToArray()` allocate a new collection. Only call them when you need a materialised snapshot.

### Multiple Enumerations of IEnumerable
- Never enumerate an `IEnumerable<T>` more than once. It might re-execute a query or recalculate. Materialise with `ToList()` once, then reuse.
- ReSharper / Rider will warn you. Do not suppress the warning.

### Large Struct Copies
- Structs larger than 16 bytes should be passed by `in` or `ref` to avoid copying.
  ```csharp
  void ProcessScore(in ScoringContext ctx) { /* no copy */ }
  ```

### Mutability in Structs
- Structs should be `readonly struct`. Mutable structs cause silent copy bugs when used with `in` parameters or stored in collections.
  ```csharp
  public readonly struct LinkScore
  {
      public float Relevance { get; init; }
      public float Authority { get; init; }
  }
  ```

### Relying on Garbage Collection Timing
- Never call `GC.Collect()` in production code. The GC knows better than you.
- Never assume an object is collected at any specific time. Use `IDisposable` for deterministic cleanup.

### Weak References Misuse
- `WeakReference<T>` is only for optional caches where losing the object is acceptable.
- Never use weak references as a substitute for proper lifetime management. If you need the object, hold a strong reference.

### Unsafe Block Memory Corruption
- `unsafe` blocks are forbidden unless benchmarks prove a measurable gain AND the block is under 20 lines.
- Every `unsafe` block must have a comment citing the benchmark result.
- Never write past allocated bounds. Pin arrays with `fixed` only for the minimum scope needed.

### Stack Overflow from Deep Recursion
- No unbounded recursion. Every recursive function must have a depth limit (max 100).
- Prefer iterative approaches with an explicit `Stack<T>` for tree/graph traversal.

---

## 4. Async & Concurrency

### Async Void Methods
- Forbidden. Always return `Task` or `ValueTask`. The only exception: event handlers (which we don't have in a worker service, so zero exceptions).
  ```csharp
  // FORBIDDEN
  async void ProcessUrl(string url) { ... }

  // CORRECT
  async Task ProcessUrlAsync(string url, CancellationToken ct) { ... }
  ```

### Deadlocks from Task.Wait() / Task.Result
- `Task.Wait()`, `Task.Result`, and `Task.GetAwaiter().GetResult()` are forbidden. They block the thread and risk deadlocks.
- Always `await` instead. If you are in a synchronous context that truly cannot be made async, use `Task.Run(() => ...).GetAwaiter().GetResult()` as a last resort and add a comment explaining why.

### Thread Pool Starvation
- Never block a thread pool thread with synchronous I/O or `Thread.Sleep`.
- This service does heavy HTTP I/O. All of it must be async. If Npgsql or HttpClient offers both sync and async, always pick async.

### Missing ConfigureAwait(false)
- In library/service code (no UI thread): use `ConfigureAwait(false)` on every `await`.
  ```csharp
  var rows = await cmd.ExecuteNonQueryAsync(ct).ConfigureAwait(false);
  ```
- This avoids unnecessary synchronization context captures and improves throughput.

### Ignoring Cancellation Tokens
- Every async method must accept and forward a `CancellationToken`.
- Pass `ct` to every `Async` call: `ReadAsync(ct)`, `ExecuteNonQueryAsync(ct)`, `SendAsync(request, ct)`.
- Check `ct.ThrowIfCancellationRequested()` at the start of long-running loops.

### Unhandled Task Exceptions
- Every `Task` must be awaited or its exceptions observed. Fire-and-forget tasks must be wrapped:
  ```csharp
  _ = Task.Run(async () =>
  {
      try { await DoWorkAsync(ct).ConfigureAwait(false); }
      catch (Exception ex) { logger.LogError(ex, "Background task failed"); }
  }, ct);
  ```

### Unobserved Task Exceptions
- Hook `TaskScheduler.UnobservedTaskException` in `Program.cs` to log any unobserved exceptions. Never let them vanish silently.

### Relying on Thread.Sleep
- Forbidden. Use `await Task.Delay(ms, ct)` instead. `Thread.Sleep` blocks a thread pool thread.

### Thread Abort Usage
- `Thread.Abort()` does not exist in .NET 9. If legacy code references it, remove it. Use `CancellationToken` for cooperative cancellation.

### Blocking the UI Thread
- This service has no UI thread, but the rule still applies: never block any thread pool thread synchronously. All I/O is async.

---

## 5. Thread Safety

### Improper Use of lock(this)
- Forbidden. External code can also lock on `this`, causing deadlocks. Lock on a private `readonly object`:
  ```csharp
  private readonly object _syncRoot = new();
  lock (_syncRoot) { /* ... */ }
  ```

### Using Volatile Incorrectly
- `volatile` only guarantees visibility, not atomicity. It does not replace `Interlocked` or `lock`.
- For simple counters: `Interlocked.Increment(ref _count)`.
- For flags: `Interlocked.Exchange(ref _flag, 1)`.

### Thread Safety in Collections
- `Dictionary<K,V>` is not thread-safe. Use `ConcurrentDictionary<K,V>` for concurrent reads/writes.
- `List<T>` is not thread-safe. If shared across threads, guard with a lock or use `ImmutableList<T>`.

### Concurrent Collection Misuse
- `ConcurrentDictionary.GetOrAdd()` may invoke the factory multiple times. If the factory is expensive, use `Lazy<T>`:
  ```csharp
  _cache.GetOrAdd(key, _ => new Lazy<ExpensiveThing>(() => Compute())).Value;
  ```

### Race Conditions in Lazy Initialization
- `Lazy<T>` defaults to `LazyThreadSafetyMode.ExecutionAndPublication` (safe). Do not use `LazyThreadSafetyMode.None` in concurrent scenarios.

### Improper Use of Static Members
- Static mutable state is shared across all threads. Every static field that can be mutated must be either `ConcurrentDictionary`, guarded by a lock, or `Interlocked`-operated.
- Prefer dependency injection over static state.

### Parallel LINQ Overhead
- `AsParallel()` adds partitioning and thread synchronization overhead. Only use for CPU-bound work over 10,000+ items with measured benefit.
- Never use PLINQ on I/O-bound operations. Use `Task.WhenAll` with concurrency limits instead.

---

## 6. Database Access (Npgsql)

### Improper DbContext Lifetimes
- This project uses raw Npgsql, not EF Core. The same principle applies: connections must be short-lived. Open, query, close. Never hold a connection open across multiple awaits unless inside an explicit transaction.

### N+1 Query Problems
- Never execute a query inside a loop. Batch IDs into a single `WHERE id = ANY(@ids)` query.
  ```csharp
  // FORBIDDEN
  foreach (var id in ids)
      await QuerySingle(id, ct);

  // CORRECT
  await using var cmd = new NpgsqlCommand(
      "SELECT * FROM pages WHERE id = ANY(@ids)", conn);
  cmd.Parameters.AddWithValue("ids", ids.ToArray());
  ```

### SQL Injection via String Concatenation
- Forbidden. Every query must use parameterised SQL via `NpgsqlParameter` or `AddWithValue`.
  ```csharp
  // FORBIDDEN
  var sql = $"SELECT * FROM pages WHERE url = '{url}'";

  // CORRECT
  cmd.Parameters.AddWithValue("url", url);
  ```

### Unparameterized SQL Queries
- Same as above. No exceptions. Even for "safe" integer IDs, use parameters. This is a non-negotiable security rule.

### Missing Indexing on Database Queries
- Every `WHERE` clause column used in production queries must have a corresponding index. If you add a new filter, add the migration for the index in the same PR.

### Tracking Overhead in EF Core
- We do not use EF Core. If it is ever introduced, all read-only queries must use `AsNoTracking()`.

### Lazy Loading N+1 Issues
- We do not use EF Core lazy loading. If navigation properties ever appear, disable lazy loading globally and use explicit `Include()`.

### Hardcoded Connection Strings
- Forbidden. Connection strings come from environment variables or configuration. Never in source code.

---

## 7. Error Handling

### Swallowed Exceptions
- Forbidden. Every `catch` must either log and rethrow, log and handle, or log and return an error. An empty `catch {}` is never acceptable.
  ```csharp
  // FORBIDDEN
  catch (Exception) { }

  // CORRECT
  catch (Exception ex)
  {
      _logger.LogError(ex, "Failed to scan {Url}", url);
      throw;
  }
  ```

### Transient Fault Handling Failures
- HTTP calls, database connections, and external API calls must use retry with exponential backoff.
- Use Polly (or the built-in `HttpClientFactory` retry policies) for transient failures.
  ```csharp
  services.AddHttpClient("scanner")
      .AddStandardResilienceHandler();
  ```

### Ignoring API Rate Limits
- Every external HTTP call must respect rate limits. Use a `SemaphoreSlim` or token bucket. Never fire unbounded parallel requests.

### Ignoring Compiler Warnings
- `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>` in every `.csproj`. Zero warnings in CI.
- Never use `#pragma warning disable` without a tracking issue number in the comment.

### Suppressed Code Analysis Rules
- Do not disable Roslyn analysers globally. If a specific suppression is needed, it must be inline with a justification comment and issue number.

---

## 8. Type System & Equality

### Overriding Equals but Not GetHashCode
- If you override `Equals`, you must override `GetHashCode`. Period. The compiler warns; the project treats warnings as errors.
- For record types (C# 12): equality is auto-generated. Prefer `record` or `record struct` for value-semantic types.

### Improper DateTime Conversion
- Never use `DateTime.Now`. Use `DateTimeOffset.UtcNow` for timestamps.
  ```csharp
  // FORBIDDEN
  var timestamp = DateTime.Now;

  // CORRECT
  var timestamp = DateTimeOffset.UtcNow;
  ```

### Timezone Mishandling
- Store all times as UTC in the database (`timestamptz` in PostgreSQL).
- Convert to local time only at the display boundary (which this service never does — it's a worker).
- Never use `DateTime.ToLocalTime()` on a server.

### Unchecked Integer Overflow
- For calculations that might overflow (e.g., combining large counts), use `checked` context:
  ```csharp
  int total = checked(countA + countB);
  ```
- Or enable `<CheckForOverflowUnderflow>true</CheckForOverflowUnderflow>` project-wide.

---

## 9. Serialization & Security

### Insecure Deserialization
- Only use `System.Text.Json`. Never `BinaryFormatter` (removed in .NET 9), never `Newtonsoft.Json` with `TypeNameHandling` enabled.
- Deserialize into concrete known types. Never deserialize into `object` or `dynamic`.

### JSON Serialization Overhead
- Create a single `JsonSerializerOptions` instance and reuse it. Each new instance rebuilds the internal metadata cache.
  ```csharp
  private static readonly JsonSerializerOptions JsonOpts = new()
  {
      PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
      DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
  };
  ```
- For high-throughput paths, use source-generated serializers via `[JsonSerializable]`.

### Cross-Site Scripting Vulnerabilities
- This is a worker service, not a web app, but any HTML content stored or forwarded must be sanitized. Never trust scraped page content.

### Missing Authorization Checks
- Every RPC endpoint or queue message handler must validate the caller/source. Never assume the message queue is trusted.

---

## 10. Dependency Injection

### Improper Dependency Injection Lifetimes
- `HttpClient`: always inject via `IHttpClientFactory`, never `new HttpClient()`. Direct instantiation leaks sockets.
- Scoped services must never be injected into singletons. The DI container will throw at startup — do not suppress this.
- `NpgsqlDataSource` is singleton. Individual `NpgsqlConnection` instances are transient (opened per-operation).

### Circular Dependencies
- If A depends on B and B depends on A, refactor. Extract the shared logic into a third service C.
- The DI container will throw on circular dependencies. Do not work around it with `Lazy<T>` injection.

### Tightly Coupled Third-Party Libraries
- Wrap every third-party library behind an interface. `MathNet.Numerics`, `Npgsql`, and `System.Text.Json` must be accessed through thin wrappers that can be swapped in tests.

---

## 11. Design & Architecture

### Bloated Controllers / Handlers
- Each message handler class must do one thing. If a handler exceeds 100 lines, split it.

### God Objects
- No class may have more than 7 injected dependencies. If it needs more, it is doing too much. Split it.

### Anemic Domain Models
- Domain types (e.g., `LinkCandidate`, `ScanResult`) should carry behaviour (validation, scoring helpers), not just properties. Avoid a model that is just a bag of getters.

### Tight Coupling
- Depend on abstractions (`IScanService`, `IRanker`), not concrete classes. Every service registered in DI should have an interface.

### Improper Use of Partial Classes
- Partial classes are allowed only for source-generator output (JSON serializers, etc.). Never use partial classes to split a file that is too big. Make the class smaller instead.

### Overly Complex Switch Statements
- A `switch` with more than 7 cases should be replaced by a dictionary dispatch or strategy pattern.

### Deep Inheritance Hierarchies
- Max inheritance depth: 2 (base -> concrete). Prefer composition over inheritance.
- Interfaces with default method implementations are preferred over abstract base classes.

### Fragile Base Class Problem
- Virtual methods on base classes must be documented with their intended override contract.
- If a base class method is not intended for override, seal it.

### Improper Use of Virtual Methods
- Never call a virtual method from a constructor. The derived class is not yet initialized.

### Shadowing Inherited Members
- `new` keyword to hide a base member is forbidden. It silently breaks polymorphism. Override instead, or rename.

### Incorrect Use of new Keyword
- `new` to hide inherited members: forbidden (see above).
- `new` for object construction: fine, but prefer DI for services.

### Misuse of Extension Methods
- Extension methods must be pure (no side effects, no state mutation).
- Never put extension methods on `object` or `string` — too broad.
- Extension method classes go in a `Extensions/` folder, one static class per extended type.

### Overly Permissive Access Modifiers
- Default to `internal`. Use `public` only for types that must be visible outside the assembly.
- Fields are always `private`. Never `public` fields (use properties).

### Magic Numbers
- Every numeric literal in logic must be a named constant or configuration value.
  ```csharp
  // FORBIDDEN
  if (score > 0.72) { ... }

  // CORRECT
  private const float MinRelevanceThreshold = 0.72f;
  if (score > MinRelevanceThreshold) { ... }
  ```

### Magic Strings
- Same rule. Named constants or configuration keys. No bare string literals in logic.

### Hardcoded Credentials
- Forbidden. API keys, passwords, tokens come from environment variables or a secrets provider. Never in source. CI scans for secrets — any detection fails the build.

### Monolithic Architecture Bottlenecks
- Each message type (scan, sitemap, analytics, tuning) should have its own handler class and its own queue consumer. Never one mega-handler processing everything.

---

## 12. Reflection & Dynamic

### Reflection Performance Overhead
- `typeof(T).GetMethod()` and `Activator.CreateInstance()` are slow. Never use in hot paths.
- If reflection is needed at startup (configuration binding), cache the `MethodInfo` / `PropertyInfo` once.

### Dynamic Keyword Runtime Cost
- `dynamic` is forbidden. It bypasses compile-time checking and allocates heavily at runtime.
- Use generics, interfaces, or source generators instead.

---

## 13. Collections & Data Structures

### Dictionary Hash Collisions
- Custom key types must implement `GetHashCode()` with good distribution. Use `HashCode.Combine()`:
  ```csharp
  public override int GetHashCode() => HashCode.Combine(SiteId, Url);
  ```

### Unbounded Queues
- Every `Channel<T>` must have a bounded capacity. Never `Channel.CreateUnbounded<T>()`.
  ```csharp
  var channel = Channel.CreateBounded<ScanJob>(new BoundedChannelOptions(10_000)
  {
      FullMode = BoundedChannelFullMode.Wait,
  });
  ```

### Excessive Memory Caching
- Every `IMemoryCache` or `ConcurrentDictionary` used as a cache must have:
  - A max entry count or max memory size.
  - An eviction policy (TTL, LRU, or sliding expiration).
- Never cache without eviction. Memory will grow until OOM in a long-running worker.

### Missing Cache Eviction Policies
- Same rule as above. If you add a cache, the eviction policy goes in the same PR.

---

## 14. Regex & String Processing

### Inefficient Regex Instantiation
- Compile regexes once as `static readonly` with `RegexOptions.Compiled` or use source-generated regex (C# 12):
  ```csharp
  [GeneratedRegex(@"https?://[^\s""'>]+", RegexOptions.Compiled)]
  private static partial Regex UrlPattern();
  ```
- Never create a `new Regex(...)` inside a loop.

### Inefficient XML Parsing
- Prefer `System.Text.Json` for JSON (already mandated). For XML (sitemaps), use `XmlReader` (streaming, low-alloc) instead of `XDocument.Load()` which loads everything into memory.

---

## 15. Testing

### Lack of Unit Tests
- Every public method on every service must have at least one unit test. Coverage floor: 80%.

### Flaky Tests
- Tests must be deterministic. No `Thread.Sleep`, no real HTTP calls, no real database.
- Use `Moq` or `NSubstitute` for external dependencies. Use `Testcontainers` for integration tests only.

### Incorrect Use of Mock Objects
- Mock interfaces, not concrete classes. Never mock `NpgsqlConnection` directly — wrap it behind `IDbAccess` and mock that.
- Verify interactions only when the interaction IS the behaviour. Otherwise, assert on output.

### Testing Implementation Details
- Tests verify WHAT, not HOW. If refactoring a method's internals breaks a test, the test was wrong.

### Missing XML Documentation (Public APIs Only)
- Every `public` or `internal` interface method must have an `<summary>` XML doc comment.
- Implementation classes do not need XML docs unless the logic is non-obvious.

---

## 16. Performance Patterns

### Implicit Interface Implementation Issues
- Use explicit interface implementation when a type implements multiple interfaces with clashing member names.
- For DI resolution, implicit implementation is fine. Just be aware that explicit implementation hides members from the concrete type.

### Overly Permissive Exception Catching
- Never `catch (Exception)` at a low level. Catch the specific exception: `NpgsqlException`, `HttpRequestException`, `OperationCanceledException`.
- A top-level `catch (Exception)` is only acceptable in the outermost host loop for logging before shutdown.

### Prepared Statement Reuse
- For queries executed in a loop or on every message, use `NpgsqlCommand` with `Prepare()` or create commands from `NpgsqlDataSource.CreateCommand()` which auto-prepares.

---

## 17. Docker & Deployment

### HttpClient Socket Exhaustion
- Never `new HttpClient()`. Always `IHttpClientFactory`. The factory manages handler lifetimes and DNS rotation.
  ```csharp
  // In DI registration
  services.AddHttpClient("scanner", client =>
  {
      client.Timeout = TimeSpan.FromSeconds(30);
  });

  // In handler
  var client = _httpClientFactory.CreateClient("scanner");
  ```

### Logging
- Use structured logging via `ILogger<T>`. Never `Console.WriteLine`.
- Log template must use `{PlaceholderName}` (not string interpolation) so structured sinks can index fields.
  ```csharp
  _logger.LogInformation("Scanned {Url} in {ElapsedMs}ms", url, elapsed);
  ```

### Configuration
- All configuration from `appsettings.json` + environment variables. Bind to strongly-typed `IOptions<T>`.
- Secrets: environment variables only. Never in `appsettings.json`, never in source.

---

## 18. Mandatory Pre-Merge Checklist

Every C# PR in the HttpWorker must pass ALL of these before merge:

| Gate | Tool | Pass criteria |
|---|---|---|
| 1. Compiles clean | `dotnet build /warnaserror` | Zero warnings, zero errors |
| 2. Tests pass | `dotnet test` | 100% pass, no skipped tests without issue link |
| 3. Null safety | Nullable analysis | Zero nullable warnings |
| 4. Code analysis | .NET analysers + `dotnet format --verify-no-changes` | Zero diagnostics |
| 5. No secrets | CI secret scanner | Zero detected credentials or tokens |
| 6. SQL safety | Manual review | Every query uses parameters; zero string concatenation |
| 7. Async correctness | Manual review | Zero `async void`, zero `.Result` / `.Wait()`, all awaits have `ConfigureAwait(false)` |
| 8. Resource disposal | Manual review | Every `IDisposable` in `using` / `await using`, every cache has eviction |
| 9. Docker build | `docker build .` | Image builds, health check passes |
| 10. Code review | Human reviewer | Confirms all rules in this file are followed |
| 11. Benchmark | `dotnet run -c Release` in benchmarks project | Hot-path methods have BenchmarkDotNet coverage with `[Params]` for 3 input sizes |

---

## 19. Forbidden Patterns — Quick Reference

| Pattern | Why | Fix |
|---|---|---|
| `async void` | Unobservable exceptions | `async Task` |
| `.Result` / `.Wait()` | Deadlock risk | `await` |
| `Thread.Sleep` | Blocks thread pool | `await Task.Delay(ms, ct)` |
| `lock (this)` | External deadlock risk | `lock (private readonly object)` |
| `new HttpClient()` | Socket exhaustion | `IHttpClientFactory` |
| `volatile` for sync | Not atomic | `Interlocked` or `lock` |
| `string += ` in loop | O(n^2) allocations | `StringBuilder` |
| `DateTime.Now` | Timezone bugs | `DateTimeOffset.UtcNow` |
| `catch { }` (empty) | Swallowed exceptions | Log and rethrow or handle |
| `dynamic` | Runtime cost, no type safety | Generics or interfaces |
| `BinaryFormatter` | Insecure deserialization (removed in .NET 9) | `System.Text.Json` |
| `GC.Collect()` | Hurts throughput | Remove the call |
| `~ClassName()` finalizer | Gen 2 promotion penalty | `IDisposable` / `SafeHandle` |
| `new Regex(...)` in loop | Compiles every iteration | `static readonly` or `[GeneratedRegex]` |
| `ArrayList` / `Hashtable` | Boxing on every operation | `List<T>` / `Dictionary<K,V>` |
| `Channel.CreateUnbounded` | OOM under load | `Channel.CreateBounded` |
| `#pragma warning disable` | Hides real bugs | Fix the warning |
| SQL string concatenation | SQL injection | `NpgsqlParameter` |
| `Thread.Abort()` | Does not exist in .NET 9 | `CancellationToken` |
| `Console.WriteLine` | No structured logging | `ILogger<T>` |
| `public` field | Breaks encapsulation | Property with `private set` |
| `new` to hide base member | Silent polymorphism break | Override or rename |
| `XDocument.Load()` on large XML | Loads entire document into memory | `XmlReader` (streaming) |
| `Task.Run` without `try/catch` | Unobserved exception | Wrap body in try/catch with logging |
| `!` null-forgiving operator | Hides null bugs | Fix the nullability |
| Magic numbers / strings | Unreadable, un-searchable | Named constants |
| Recursive depth > 100 | Stack overflow | Iterative with `Stack<T>` |
| `Activator.CreateInstance` in hot path | Reflection overhead | Cached delegates or DI |
| `AsParallel()` on I/O work | Thread waste | `Task.WhenAll` with semaphore |
