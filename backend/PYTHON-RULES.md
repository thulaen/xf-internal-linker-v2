# Python Backend Rules — No Exceptions

Every AI agent (Claude, Codex, Gemini, etc.) writing Python in this repo must follow these rules. Every human reviewer must enforce them. No rule may be skipped "because it's just a quick fix."

**Before any Python backend work, read this file top to bottom.**

**Project context:** Django 5.2 + DRF, Celery 5.4, PostgreSQL 17 + pgvector, Redis, Django Channels, pybind11 C++ extensions, numpy 1.26, pandas 2.2, scikit-learn, requests, google-api-python-client. Python 3.12 runtime. Deployed in Docker.

---

## 1. Function & Variable Pitfalls

### 1.1 Mutable Default Arguments

A mutable default (list, dict, set) is shared across all calls. It grows silently.

```python
# WRONG
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags

# RIGHT
def add_tag(tag, tags=None):
    if tags is None:
        tags = []
    tags.append(tag)
    return tags
```

### 1.2 Unbound Local Errors

Assigning to a name inside a function makes it local for the entire function, even before the assignment line.

```python
# WRONG — UnboundLocalError because Python sees `count` as local
count = 0
def increment():
    count += 1  # crashes

# RIGHT
count = 0
def increment():
    global count  # or better: pass as argument and return
    count += 1
```

### 1.3 Missing Return Statements

Every code path must return explicitly. A function that sometimes returns `None` by falling off the end is a bug.

```python
# WRONG
def get_score(page):
    if page.is_published:
        return page.score
    # falls off — returns None

# RIGHT
def get_score(page):
    if page.is_published:
        return page.score
    return 0.0
```

### 1.4 Returning Inconsistent Types

A function must return the same type on every path. Do not mix `dict` and `None`, or `list` and `False`.

```python
# WRONG
def fetch_links(page_id):
    if not page_id:
        return False  # bool when caller expects list
    return Link.objects.filter(page_id=page_id)

# RIGHT
def fetch_links(page_id: int) -> QuerySet[Link]:
    if not page_id:
        return Link.objects.none()
    return Link.objects.filter(page_id=page_id)
```

### 1.5 Late Binding in Closures

Closures capture variables by reference, not by value. Loop variables are the usual trap.

```python
# WRONG — all five functions return 4
funcs = [lambda: i for i in range(5)]

# RIGHT — capture current value with default arg
funcs = [lambda i=i: i for i in range(5)]
```

### 1.6 Lambda Scoping Issues

Same root cause as 1.5. Lambdas in comprehensions share the enclosing scope variable.

```python
# WRONG
callbacks = {name: lambda: print(name) for name in ["a", "b", "c"]}
# all print "c"

# RIGHT
callbacks = {name: lambda n=name: print(n) for name in ["a", "b", "c"]}
```

### 1.7 Redundant Boolean Comparisons

Never compare to `True`, `False`, or `None` with `==`. Use `is` for singletons and bare truthiness for booleans.

```python
# WRONG
if active == True:
if result == None:

# RIGHT
if active:
if result is None:
```

### 1.8 Incorrect Use of `is` vs `==`

`is` checks identity (same object in memory). `==` checks equality (same value). Only use `is` for `None`, `True`, `False`.

```python
# WRONG — works by accident for small ints, breaks for large ones
if status_code is 200:

# RIGHT
if status_code == 200:
```

---

## 2. Data Structure Pitfalls

### 2.1 Modifying a List While Iterating

Mutating a list during iteration skips elements or causes `IndexError`.

```python
# WRONG
for item in items:
    if item.is_stale:
        items.remove(item)

# RIGHT
items = [item for item in items if not item.is_stale]
```

### 2.2 Mutating Dict Keys During Iteration

Same as lists. `RuntimeError: dictionary changed size during iteration`.

```python
# WRONG
for key in cache:
    if cache[key].expired:
        del cache[key]

# RIGHT
expired = [k for k, v in cache.items() if v.expired]
for key in expired:
    del cache[key]
```

### 2.3 Shallow Copy vs Deep Copy Confusion

`copy()` and slicing (`[:]`) create shallow copies. Nested mutables are still shared.

```python
# WRONG — nested list is shared
import copy
config = {"weights": [0.5, 0.3, 0.2]}
backup = config.copy()
backup["weights"].append(0.1)  # mutates original too

# RIGHT
backup = copy.deepcopy(config)
```

### 2.4 Dictionary Key Order Assumptions

Python 3.7+ dicts maintain insertion order, but never rely on position for logic. Use explicit sorting or `OrderedDict` when order is part of the contract.

### 2.5 Deeply Nested Dictionaries

More than 2 levels of nesting means you need a dataclass or Pydantic model.

```python
# WRONG
result["meta"]["scores"]["semantic"] = 0.85

# RIGHT
@dataclass
class ScoreResult:
    semantic: float = 0.0
    topical: float = 0.0

@dataclass
class PipelineResult:
    scores: ScoreResult = field(default_factory=ScoreResult)
```

---

## 3. Memory & Performance

### 3.1 Lists Instead of Generators

Building a full list when you only need to iterate once wastes memory. This matters for large page sets.

```python
# WRONG — builds entire list in memory
urls = [page.url for page in Page.objects.all()]
for url in urls:
    process(url)

# RIGHT — generator, one row at a time
urls = (page.url for page in Page.objects.iterator())
for url in urls:
    process(url)
```

### 3.2 String Concatenation Using `+`

`+` creates a new string each time. Quadratic time for loops.

```python
# WRONG
output = ""
for link in links:
    output += f"<a href='{link.url}'>{link.text}</a>"

# RIGHT
parts = [f"<a href='{link.url}'>{link.text}</a>" for link in links]
output = "".join(parts)
```

### 3.3 Excessive Object Creation in Loops

Never create expensive objects (compiled regex, HTTP sessions, DB connections) inside a loop.

```python
# WRONG
for url in urls:
    response = requests.Session().get(url)

# RIGHT
session = requests.Session()
for url in urls:
    response = session.get(url)
```

### 3.4 Memory Leaks in Long-Running Processes

Celery workers and Channels consumers run for hours. Leaks accumulate.

- Clear caches periodically. Use `@lru_cache(maxsize=N)`, never unbounded `@cache`.
- Avoid global lists that grow per-request.
- Use `weakref` for observer patterns.
- Profile workers monthly: `tracemalloc` or `objgraph`.

### 3.5 Relying on Reference Counting for Cleanup

CPython uses refcounting, but cycles are only collected by the GC periodically. Always use context managers for deterministic cleanup.

```python
# WRONG — relies on refcount hitting zero
f = open("data.csv")
data = f.read()

# RIGHT
with open("data.csv") as f:
    data = f.read()
```

### 3.6 Caching Without Bounds

Unbounded caches grow forever in long-running workers.

```python
# WRONG — unbounded, leaks memory in Celery workers
@cache
def get_embedding(text: str) -> np.ndarray: ...

# RIGHT — bounded
@lru_cache(maxsize=2048)
def get_embedding(text: str) -> np.ndarray: ...
```

### 3.7 Inefficient Substring Searching

For single checks, `in` is fine. For repeated pattern matching, compile once.

```python
# WRONG — re.search recompiles every call
for line in lines:
    if re.search(r"\bnofollow\b", line): ...

# RIGHT
NOFOLLOW_RE = re.compile(r"\bnofollow\b")
for line in lines:
    if NOFOLLOW_RE.search(line): ...
```

### 3.8 Regex Compilation Overhead Inside Loops

Same as 3.7. Every `re.search()` / `re.match()` with a raw string compiles the pattern. Compile once at module level.

### 3.9 Inefficient JSON Parsing

For large JSON payloads, use `orjson` (already faster than `json`). For streaming, use `ijson`.

```python
# WRONG for large payloads
import json
data = json.loads(huge_string)

# RIGHT
import orjson
data = orjson.loads(huge_string)
```

---

## 4. Import & Module Pitfalls

### 4.1 Circular Imports

Django apps importing from each other at module level causes `ImportError`. Import inside functions or use string references.

```python
# WRONG — circular at module level
from apps.suggestions.models import Suggestion  # in apps/pipeline/services.py
from apps.pipeline.models import PipelineRun     # in apps/suggestions/models.py

# RIGHT — import inside function
def get_suggestions_for_run(run_id):
    from apps.suggestions.models import Suggestion
    return Suggestion.objects.filter(pipeline_run_id=run_id)
```

### 4.2 Ignoring the `__init__.py` File

Every Python package directory needs `__init__.py`. Missing it makes imports silently fail or behave differently.

### 4.3 Naming Collisions with Standard Library

Never name a module `email.py`, `calendar.py`, `logging.py`, `json.py`, `test.py`, etc. These shadow stdlib modules and break everything.

### 4.4 Wildcard Imports

`from module import *` pollutes the namespace and makes it impossible to trace where a name comes from.

```python
# WRONG
from apps.pipeline.services import *

# RIGHT
from apps.pipeline.services import run_pipeline, score_candidates
```

### 4.5 Ignoring `__all__` in Modules

Public modules must define `__all__` to declare their public API. This protects internal helpers from accidental use.

```python
# In apps/pipeline/services/__init__.py
__all__ = ["run_pipeline", "score_candidates"]
```

### 4.6 Import-Time Side Effects

Module-level code that hits the database, network, or filesystem runs at import time. This breaks tests and slows startup.

```python
# WRONG — runs a query when the module is imported
DEFAULT_WEIGHTS = ScoringWeight.objects.values_list("value", flat=True)

# RIGHT — lazy evaluation
def get_default_weights():
    return list(ScoringWeight.objects.values_list("value", flat=True))
```

### 4.7 Mutable Module-Level State

A module-level dict or list is shared across all requests in the same process. In Django with ASGI or Celery, this causes race conditions.

```python
# WRONG — shared mutable state across requests
_request_cache: dict[str, Any] = {}

# RIGHT — use Django's cache framework or thread-local storage
from django.core.cache import cache
```

---

## 5. Class & OOP Pitfalls

### 5.1 Class Variables vs Instance Variables

Class variables are shared across all instances. Instance variables are per-object.

```python
# WRONG — all instances share the same list
class Pipeline:
    stages = []  # class variable — shared!

# RIGHT
class Pipeline:
    def __init__(self):
        self.stages = []  # instance variable — per-object
```

### 5.2 Hidden State in Classes

A class that reads from global state or environment variables inside methods is hard to test and debug. Pass dependencies explicitly.

```python
# WRONG
class Ranker:
    def score(self, page):
        weights = json.loads(os.environ["WEIGHTS"])  # hidden dependency
        return sum(w * s for w, s in zip(weights, page.signals))

# RIGHT
class Ranker:
    def __init__(self, weights: list[float]):
        self.weights = weights

    def score(self, page):
        return sum(w * s for w, s in zip(self.weights, page.signals))
```

### 5.3 Checking Type with `type()` Instead of `isinstance()`

`type()` does not respect inheritance. Use `isinstance()`.

```python
# WRONG
if type(obj) == dict:

# RIGHT
if isinstance(obj, dict):
```

### 5.4 Ignoring Abstract Base Classes

Base classes with methods that must be overridden should use `ABC` and `@abstractmethod`. Otherwise subclasses silently inherit a no-op.

```python
from abc import ABC, abstractmethod

class BaseScorer(ABC):
    @abstractmethod
    def score(self, page, target) -> float:
        ...
```

### 5.5 Improper Use of Multiple Inheritance

Prefer composition over multiple inheritance. If you must use it, understand MRO and use `super()` correctly.

### 5.6 Method Resolution Order Confusion

Python uses C3 linearization. If you mix multiple inheritance and direct parent calls, you will skip or double-call methods. Always use `super()` in cooperative inheritance.

### 5.7 Property Setter Side Effects

Property setters must not trigger network calls, database writes, or expensive computation. They look like simple attribute assignment to the caller.

```python
# WRONG
class Page:
    @url.setter
    def url(self, value):
        self.url = value
        requests.post(WEBHOOK_URL, json={"url": value})  # hidden side effect

# RIGHT — make the side effect explicit
class Page:
    def update_url(self, value):
        self.url = value
        self.notify_webhook()
```

### 5.8 Raising `NotImplemented` Instead of `NotImplementedError`

`NotImplemented` is a special return value for rich comparison methods. It is not an exception.

```python
# WRONG — returns NotImplemented (a truthy value), does not raise
def score(self):
    raise NotImplemented

# RIGHT
def score(self):
    raise NotImplementedError("Subclasses must implement score()")
```

---

## 6. Exception Handling

### 6.1 Catching `Exception` Instead of Specific Errors

Bare `except Exception` swallows `KeyboardInterrupt` escapes and masks real bugs.

```python
# WRONG
try:
    result = fetch_page(url)
except Exception:
    result = None

# RIGHT
try:
    result = fetch_page(url)
except (requests.ConnectionError, requests.Timeout) as e:
    logger.warning("Fetch failed for %s: %s", url, e)
    result = None
```

### 6.2 Unhandled Exceptions

Every external call (HTTP, DB, file I/O) must be wrapped in a try/except that handles the expected failure modes. Unhandled exceptions crash Celery tasks and drop WebSocket connections.

### 6.3 Swallowing Exceptions in `finally` Blocks

A `return` or new exception in `finally` silently replaces the original exception.

```python
# WRONG — original exception is lost
try:
    process(data)
except ValueError:
    raise
finally:
    return cleanup()  # this silently swallows the ValueError

# RIGHT
try:
    process(data)
except ValueError:
    raise
finally:
    cleanup()  # no return here
```

### 6.4 Using `eval()` / `exec()` with Untrusted Input

Forbidden. Period. No exceptions. If you need dynamic dispatch, use a dictionary of functions.

```python
# WRONG — remote code execution
result = eval(user_provided_expression)

# RIGHT
OPERATIONS = {"sum": sum, "mean": statistics.mean}
result = OPERATIONS[operation_name](values)
```

---

## 7. Resource Management

### 7.1 Resource Leaks from Missing Context Managers

Every resource that has a `.close()` method must be used with `with`.

```python
# WRONG
conn = psycopg.connect(DSN)
cursor = conn.cursor()
cursor.execute("SELECT 1")
# conn never closed if exception occurs

# RIGHT
with psycopg.connect(DSN) as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1")
```

### 7.2 Leaking File Descriptors

Same as 7.1. Every `open()` needs `with`. This matters in Docker where the default ulimit is 1024.

### 7.3 Unclosed Network Sockets

`requests.Session()` must be used as a context manager or explicitly closed. Leaked sockets hit the OS limit.

```python
# RIGHT
with requests.Session() as session:
    response = session.get(url)
```

### 7.4 Database Connection Leaks

Django manages connections per-request, but Celery tasks and management commands do not. Always close connections after long-running operations.

```python
from django.db import connection

def long_celery_task():
    try:
        do_work()
    finally:
        connection.close()
```

### 7.5 Improper Use of `del`

`del` removes a name binding. It does not guarantee the object is freed. Never use `del` as a substitute for proper resource cleanup.

---

## 8. Concurrency & Async

### 8.1 Blocking Operations in `asyncio`

Django Channels consumers run on an event loop. A blocking call (DB query, file I/O, HTTP request) freezes the entire loop.

```python
# WRONG — blocks the event loop
class MyConsumer(AsyncWebsocketConsumer):
    async def receive(self, text_data):
        data = Page.objects.get(pk=1)  # sync DB call blocks

# RIGHT
from channels.db import database_sync_to_async

class MyConsumer(AsyncWebsocketConsumer):
    async def receive(self, text_data):
        data = await database_sync_to_async(Page.objects.get)(pk=1)
```

### 8.2 Mixing Sync and Async Code

Never call `asyncio.run()` inside a running event loop. Use `sync_to_async` / `async_to_sync` from `asgiref`.

### 8.3 Un-awaited Coroutines

Calling an `async def` function without `await` returns a coroutine object that never executes. Python 3.12 emits a RuntimeWarning, but it is still a bug.

```python
# WRONG — coroutine is created but never awaited
async def send_notification(user_id):
    ...

send_notification(42)  # does nothing

# RIGHT
await send_notification(42)
```

### 8.4 Event Loop Blocking

CPU-bound work in an async context blocks the loop. Offload to a thread pool or Celery.

```python
# RIGHT — offload CPU work
import asyncio

loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, cpu_bound_function, arg)
```

### 8.5 GIL Bottlenecks in CPU-Bound Tasks

The GIL prevents true parallelism for CPU-bound Python. Use:
- C++ extensions via pybind11 (this project's approach for scoring hot paths)
- `multiprocessing` for embarrassingly parallel work
- numpy/pandas vectorized operations (they release the GIL internally)

Never use `threading` for CPU-bound work.

### 8.6 Silent Failures in Background Threads

Exceptions in background threads vanish silently. Always use `concurrent.futures.ThreadPoolExecutor` which captures exceptions, or set an `except_hook`.

### 8.7 Daemon Thread Abrupt Termination

Daemon threads are killed without cleanup when the main thread exits. Never use daemon threads for work that must complete (DB writes, file flushes).

### 8.8 Lock Contention in Threading

Holding a lock for too long serializes your threads. Keep critical sections minimal.

```python
# WRONG — lock held during I/O
with lock:
    data = requests.get(url).json()
    cache[url] = data

# RIGHT — lock only around the shared state
data = requests.get(url).json()
with lock:
    cache[url] = data
```

### 8.9 Multiprocessing Zombie Processes

Always join child processes. Use `multiprocessing.Pool` as a context manager.

```python
# RIGHT
with multiprocessing.Pool(4) as pool:
    results = pool.map(score_page, pages)
# pool is cleaned up here
```

### 8.10 Shared Memory Corruption

`multiprocessing.Value` and `multiprocessing.Array` need explicit locking. Prefer `multiprocessing.Queue` for inter-process communication.

### 8.11 Inefficient Inter-Process Communication

Pickling large objects (numpy arrays, DataFrames) for IPC is slow. Use shared memory (`multiprocessing.shared_memory`) or memory-mapped files for large data.

---

## 9. Django-Specific Rules

### 9.1 N+1 Query Problem

Every queryset used in a loop that accesses related objects must use `select_related()` (FK/OneToOne) or `prefetch_related()` (M2M/reverse FK).

```python
# WRONG — one query per page for page.site
for page in Page.objects.all():
    print(page.site.domain)

# RIGHT
for page in Page.objects.select_related("site").all():
    print(page.site.domain)
```

### 9.2 Timezone-Naive Datetimes

Django uses timezone-aware datetimes. Never use `datetime.now()` or `datetime.utcnow()`.

```python
# WRONG
from datetime import datetime
created_at = datetime.now()

# RIGHT
from django.utils import timezone
created_at = timezone.now()
```

### 9.3 Using `print` for Logging

`print()` goes to stdout and is lost in Docker. Use Django's logging framework.

```python
# WRONG
print(f"Processing page {page.id}")

# RIGHT
import logging
logger = logging.getLogger(__name__)
logger.info("Processing page %s", page.id)
```

Use `%s` style formatting in logger calls (lazy evaluation), not f-strings.

### 9.4 Excessive Logging

Do not log inside tight loops. One log line per batch, not per item.

```python
# WRONG — 10,000 log lines
for page in pages:
    logger.info("Scoring page %s", page.id)

# RIGHT
logger.info("Scoring %d pages", len(pages))
for page in pages:
    score(page)
logger.info("Scoring complete")
```

### 9.5 Exposing Debug Endpoints

Never ship `DEBUG = True` in production settings. Never expose Django Debug Toolbar, `/admin/` without auth, or DRF browsable API in production.

### 9.6 Missing CORS Headers

CORS is configured via `django-cors-headers`. Never set `CORS_ALLOW_ALL_ORIGINS = True` in production. Whitelist the Angular frontend origin only.

### 9.7 Missing Rate Limiting

Every public-facing DRF endpoint must have a throttle class. Use DRF's `UserRateThrottle` or `AnonRateThrottle`.

---

## 10. Celery-Specific Rules

### 10.1 Missing Request Timeouts

Every HTTP call inside a Celery task must have a `timeout` parameter. Default: `timeout=30`.

```python
# WRONG — hangs forever if remote server is down
response = requests.get(url)

# RIGHT
response = requests.get(url, timeout=30)
```

### 10.2 Unbounded Retries

Every `self.retry()` must have `max_retries` set. Default is 3. Use exponential backoff.

```python
@app.task(bind=True, max_retries=3)
def fetch_gsc_data(self, site_url):
    try:
        return call_gsc_api(site_url)
    except GoogleApiError as e:
        raise self.retry(exc=e, countdown=2 ** self.request.retries * 60)
```

### 10.3 Database Connection Stale After Fork

Celery workers fork. Database connections from the parent process are stale in children. Django handles this if you use `CONN_MAX_AGE` correctly, but always close connections in `worker_process_init` signal.

### 10.4 Pickling Untrusted Data

Celery serializes task arguments. Never pass user-controlled data that could exploit pickle deserialization. Use JSON serializer for Celery.

```python
# In settings
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
```

---

## 11. Security

### 11.1 Subprocess Shell Injection

Never pass user input to `subprocess` with `shell=True`.

```python
# WRONG — shell injection
subprocess.run(f"curl {user_url}", shell=True)

# RIGHT
subprocess.run(["curl", user_url], shell=False, timeout=30)
```

### 11.2 Path Traversal Vulnerabilities

Never use user-provided filenames directly in file paths.

```python
# WRONG
filepath = os.path.join(UPLOAD_DIR, user_filename)

# RIGHT
from pathlib import Path
safe_name = Path(user_filename).name  # strips directory components
filepath = Path(UPLOAD_DIR) / safe_name
assert filepath.resolve().is_relative_to(Path(UPLOAD_DIR).resolve())
```

### 11.3 XML External Entity Attacks

Never parse XML from untrusted sources with the default parser.

```python
# WRONG
import xml.etree.ElementTree as ET
tree = ET.parse(user_uploaded_file)

# RIGHT
from defusedxml import ElementTree
tree = ElementTree.parse(user_uploaded_file)
```

### 11.4 Unsafe YAML Loading

`yaml.load()` without a Loader executes arbitrary Python.

```python
# WRONG
data = yaml.load(content)

# RIGHT
data = yaml.safe_load(content)
```

### 11.5 String Formatting Vulnerabilities

Never use `.format()` or f-strings with user-controlled format strings.

```python
# WRONG — user can read arbitrary attributes
template = user_input  # e.g. "{0.__class__.__mro__}"
result = template.format(some_object)

# RIGHT — use a safe template engine or whitelist
from string import Template
result = Template(user_input).safe_substitute(name=value)
```

### 11.6 Insecure Hash Functions

Never use MD5 or SHA-1 for security purposes. Use SHA-256 minimum.

```python
# WRONG
import hashlib
h = hashlib.md5(data).hexdigest()

# RIGHT
h = hashlib.sha256(data).hexdigest()
```

### 11.7 Weak Cryptographic Keys

Use `secrets` module, not `random`, for tokens and keys.

```python
# WRONG — predictable
import random
token = "".join(random.choices("abcdef0123456789", k=32))

# RIGHT
import secrets
token = secrets.token_hex(32)
```

### 11.8 Predictable Random Numbers

`random` module uses a Mersenne Twister PRNG. Predictable. Never use for security.

- Security tokens, session IDs, CSRF: `secrets`
- Shuffling for ML training: `random` is fine
- Numpy random for scoring: `numpy.random.default_rng()` (not the legacy `np.random.seed()`)

### 11.9 Exposing Secrets in Environment Variables

Never log, print, or include env vars in error responses. Access via `django-environ` and treat as write-only.

```python
# WRONG
logger.info("Using API key: %s", env("GOOGLE_API_KEY"))

# RIGHT
logger.info("GSC API configured: %s", bool(env("GOOGLE_API_KEY", default="")))
```

### 11.10 Unrestricted File Uploads

Validate file type, size, and content. Never trust the extension alone.

```python
MAX_UPLOAD_MB = 10
ALLOWED_TYPES = {"text/csv", "application/json"}

def validate_upload(file):
    if file.size > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError("File too large")
    if file.content_type not in ALLOWED_TYPES:
        raise ValidationError("Unsupported file type")
```

---

## 12. Type Hints & Code Quality

### 12.1 Lack of Type Hinting

Every function must have type hints on all parameters and the return value. Use Python 3.12 syntax.

```python
# WRONG
def score_page(page, weights):
    ...

# RIGHT
def score_page(page: Page, weights: list[float]) -> float:
    ...
```

### 12.2 Overly Generic Type Hints

`Any` defeats the purpose. Be specific.

```python
# WRONG
def process(data: Any) -> Any: ...

# RIGHT
def process(data: dict[str, float]) -> list[ScoredLink]: ...
```

### 12.3 Ignoring PEP 8

All code must pass `ruff check` with the project config. Key rules:
- 88-character line limit (Black default)
- 4-space indentation
- Two blank lines between top-level definitions
- One blank line between methods
- Imports sorted by `isort` conventions

### 12.4 Overly Complex List Comprehensions

If a list comprehension has more than one `if` or one nested `for`, rewrite it as a regular loop.

```python
# WRONG — unreadable
result = [
    transform(x)
    for group in groups
    for x in group.items
    if x.active
    if x.score > threshold
]

# RIGHT
result = []
for group in groups:
    for x in group.items:
        if x.active and x.score > threshold:
            result.append(transform(x))
```

### 12.5 Monkey Patching

Forbidden in production code. Monkey patching causes unpredictable behavior and breaks test isolation. The only acceptable use is in test fixtures with `unittest.mock.patch`.

---

## 13. Numeric & Scientific Computing

### 13.1 Floating Point Precision Loss

Never compare floats with `==`. Use `math.isclose()` or numpy `np.isclose()`.

```python
# WRONG
if score == 0.3:

# RIGHT
import math
if math.isclose(score, 0.3, rel_tol=1e-9):
```

### 13.2 Pandas DataFrame Copy Warnings

Pandas warns when you modify a view instead of a copy. Use `.copy()` explicitly or `.loc[]` for assignment.

```python
# WRONG — SettingWithCopyWarning
df_filtered = df[df["score"] > 0.5]
df_filtered["rank"] = range(len(df_filtered))

# RIGHT
df_filtered = df[df["score"] > 0.5].copy()
df_filtered["rank"] = range(len(df_filtered))
```

### 13.3 NumPy Array Vectorization Misses

Never loop over numpy arrays element by element. Use vectorized operations.

```python
# WRONG — Python loop over numpy array
scores = np.zeros(len(embeddings))
for i in range(len(embeddings)):
    scores[i] = np.dot(embeddings[i], query)

# RIGHT — vectorized
scores = embeddings @ query
```

### 13.4 Infinite Generators

Generators that never end must be consumed with an explicit limit.

```python
# WRONG — runs forever
def page_stream():
    offset = 0
    while True:
        yield fetch_page(offset)
        offset += 1

for page in page_stream():  # never stops
    process(page)

# RIGHT
from itertools import islice
for page in islice(page_stream(), 10000):
    process(page)
```

---

## 14. File & Path Handling

### 14.1 Hardcoded File Paths

Never hardcode paths. Use `pathlib.Path` relative to `BASE_DIR` or Django settings.

```python
# WRONG
data = open("/app/backend/data/stopwords.txt")

# RIGHT
from django.conf import settings
data_path = settings.BASE_DIR / "data" / "stopwords.txt"
```

### 14.2 Incorrect File Encoding Assumptions

Always specify encoding when opening text files. The system default varies.

```python
# WRONG — encoding depends on system locale
with open(path) as f:
    text = f.read()

# RIGHT
with open(path, encoding="utf-8") as f:
    text = f.read()
```

---

## 15. Regular Expressions

### 15.1 Fragile Regular Expressions

Regex that match "anything" (`.*`) are greedy by default and match too much. Use non-greedy (`.*?`) or specific character classes.

### 15.2 Exponential Backtracking (ReDoS)

Nested quantifiers like `(a+)+` or `(a|b)*c` cause catastrophic backtracking on certain inputs. Test every regex with pathological input.

```python
# WRONG — exponential backtracking
EVIL_RE = re.compile(r"(a+)+b")

# RIGHT — no nested quantifiers
SAFE_RE = re.compile(r"a+b")
```

Set `re.TIMEOUT` or use the `regex` library with timeout support for user-facing patterns.

---

## 16. Dependencies & Environment

### 16.1 Missing Dependency Pinning

Every dependency in `requirements.txt` must have an exact version pin (`==`). Never use `>=` in production.

### 16.2 Using `requirements.txt` as a Lockfile

`requirements.txt` is the lockfile for this project. When adding a dependency:
1. Add it with an exact version
2. Add a comment explaining what it is for
3. Test the full Docker build

---

## 17. Mandatory Pre-Merge Checklist

Every Python backend PR must pass ALL of these before merge:

| # | Gate | Command | Pass Criteria |
|---|---|---|---|
| 1 | Lint | `ruff check backend/` | Zero errors |
| 2 | Format | `ruff format --check backend/` | Zero diffs |
| 3 | Type check | `mypy backend/ --ignore-missing-imports` | Zero errors on changed files |
| 4 | Unit tests | `pytest backend/ -x -q` | All pass, zero failures |
| 5 | No print statements | `ruff check --select T20` | Zero `print()` calls outside management commands |
| 6 | No hardcoded secrets | `ruff check --select S105,S106` | Zero hardcoded passwords or keys |
| 7 | Migrations | `python manage.py makemigrations --check` | No missing migrations |
| 8 | Import order | `ruff check --select I` | Imports sorted correctly |
| 9 | No `eval`/`exec` | `ruff check --select S307` | Zero uses |
| 10 | Docker build | `docker-compose build backend` | Clean build, no errors |
| 11 | Benchmark | `pytest backend/benchmarks/test_bench_*.py` | Hot-path functions have benchmark coverage at 3 input sizes |

---

## 18. Forbidden Patterns — Quick Reference

| Pattern | Why | Fix |
|---|---|---|
| `def f(x, items=[])` | Mutable default shared across calls | `items=None` + `if` guard |
| `from module import *` | Namespace pollution | Import specific names |
| `except Exception:` | Masks real bugs | Catch specific errors |
| `eval(user_input)` | Remote code execution | Dict dispatch |
| `datetime.now()` | Timezone-naive | `django.utils.timezone.now()` |
| `print(...)` | Lost in Docker, no levels | `logger.info(...)` |
| `open(f)` without `with` | File descriptor leak | `with open(f) as fh:` |
| `requests.get(url)` no timeout | Hangs forever | `timeout=30` |
| `@cache` unbounded | Memory leak in workers | `@lru_cache(maxsize=N)` |
| `yaml.load(data)` | Arbitrary code execution | `yaml.safe_load(data)` |
| `subprocess(..., shell=True)` | Shell injection | `shell=False` + list args |
| `random.random()` for tokens | Predictable | `secrets.token_hex()` |
| `hashlib.md5(...)` for security | Weak hash | `hashlib.sha256(...)` |
| `type(x) == MyClass` | Ignores inheritance | `isinstance(x, MyClass)` |
| `raise NotImplemented` | Returns a value, not an exception | `raise NotImplementedError(...)` |
| `os.path.join(dir, user_input)` | Path traversal | `Path(user_input).name` + resolve check |
| `str += str` in loop | Quadratic time | `"".join(parts)` |
| `np.random.seed(42)` | Legacy global state | `np.random.default_rng(42)` |
| `for x in list: list.remove(x)` | Skips elements | List comprehension filter |
| `asyncio.run()` in event loop | Crashes — loop already running | `await` or `sync_to_async` |
| `json.loads(big_payload)` | Slow for large data | `orjson.loads()` |
| `DEBUG = True` in production | Exposes stack traces | Environment-based settings |
| `CORS_ALLOW_ALL_ORIGINS = True` | Open to any origin | Whitelist frontend origin |
| Nested quantifiers in regex | ReDoS — catastrophic backtracking | Flatten quantifiers |
| `CELERY_TASK_SERIALIZER = "pickle"` | Deserialization attack | Use `"json"` |
| `CONN_MAX_AGE = None` | Leaks DB connections | Set a finite value (e.g., `600`) |
| Module-level DB queries | Runs at import time | Wrap in a function |
| `del obj` for cleanup | Does not guarantee freeing | Context managers |
