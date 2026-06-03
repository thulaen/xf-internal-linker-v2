"""Test async http module for the pipeline app."""

import asyncio
import time
import unittest

try:
    import httpx
    from apps.pipeline.services.async_http import probe_urls
except ImportError:
    httpx = None  # type: ignore[assignment]
    probe_urls = None  # type: ignore[assignment]


@unittest.skipUnless(httpx, "httpx not installed")
class AsyncHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_urls_head_fallback_and_redirects(self):
        def handler(request: httpx.Request):
            url = str(request.url)
            if "405" in url and request.method == "HEAD":
                return httpx.Response(405)
            elif "405" in url and request.method == "GET":
                return httpx.Response(200)

            if "501" in url and request.method == "HEAD":
                return httpx.Response(501)
            elif "501" in url and request.method == "GET":
                return httpx.Response(200)

            if "redirect" in url:
                return httpx.Response(
                    301, headers={"Location": "https://example.com/target"}
                )

            if "timeout" in url:
                raise httpx.TimeoutException("timeout", request=request)

            return httpx.Response(200)

        transport = httpx.MockTransport(handler)

        import apps.pipeline.services.async_http as amod

        original_transport_class = amod.httpx.AsyncHTTPTransport
        amod.httpx.AsyncHTTPTransport = lambda retries: transport

        try:
            urls = [
                "https://example.com/405",
                "https://example.com/501",
                "https://example.com/redirect",
                "https://example.com/timeout",
                "https://example.com/normal",
            ]

            progress_calls = 0

            def on_progress(completed, url, res):
                nonlocal progress_calls
                progress_calls += 1

            results = await probe_urls(urls, on_progress=on_progress)

            self.assertEqual(results["https://example.com/405"], (200, ""))
            self.assertEqual(results["https://example.com/501"], (200, ""))
            self.assertEqual(
                results["https://example.com/redirect"],
                (301, "https://example.com/target"),
            )
            self.assertEqual(results["https://example.com/timeout"], (0, ""))
            self.assertEqual(results["https://example.com/normal"], (200, ""))
            self.assertEqual(progress_calls, 5)
        finally:
            amod.httpx.AsyncHTTPTransport = original_transport_class

    async def test_probe_urls_semaphore_and_perf(self):
        # URL count tuned for the test harness, not production. Raw
        # probe_urls with 1000 URLs runs in ~0.12s under asyncio.run, but
        # ~13s inside IsolatedAsyncioTestCase and ~41s under Django's
        # test runner — the test harness's event loop implementation
        # adds ~100x per-task overhead vs plain asyncio. 200 URLs is the
        # sweet spot: still exercises the 50-concurrency bound (4 full
        # batches). The max_active assertion is the meaningful proof; the
        # wall-clock assertion is only a broad hang detector because turbo
        # runs this alongside many other dirty-tree tests.
        active_requests = 0
        max_active = 0

        async def handler(request: httpx.Request):
            nonlocal active_requests, max_active
            active_requests += 1
            if active_requests > max_active:
                max_active = active_requests

            await asyncio.sleep(0)

            active_requests -= 1
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)

        import apps.pipeline.services.async_http as amod

        original_transport_class = amod.httpx.AsyncHTTPTransport
        amod.httpx.AsyncHTTPTransport = lambda retries: transport

        try:
            urls = [f"https://example.com/{i}" for i in range(200)]
            start = time.perf_counter()
            results = await probe_urls(urls, max_concurrency=50)
            duration = time.perf_counter() - start

            self.assertEqual(len(results), 200)
            self.assertLessEqual(max_active, 50)
            self.assertLess(duration, 30.0)
        finally:
            amod.httpx.AsyncHTTPTransport = original_transport_class

    async def test_probe_urls_completes_without_explicit_task_creation(self):
        def handler(request: httpx.Request):
            return httpx.Response(200)

        transport = httpx.MockTransport(handler)

        import apps.pipeline.services.async_http as amod

        original_transport_class = amod.httpx.AsyncHTTPTransport
        original_create_task = amod.asyncio.create_task
        amod.httpx.AsyncHTTPTransport = lambda retries: transport

        def fail_create_task(*_args, **_kwargs):
            raise AssertionError("probe_urls should gather coroutines directly")

        amod.asyncio.create_task = fail_create_task
        try:
            results = await probe_urls(["https://example.com/one"])
            self.assertEqual(results["https://example.com/one"], (200, ""))
        finally:
            amod.asyncio.create_task = original_create_task
            amod.httpx.AsyncHTTPTransport = original_transport_class
