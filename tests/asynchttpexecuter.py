# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import unittest
import time
from benchmark.asynchttpexecuter import AsyncHTTPExecuter
from benchmark.ratelimiting import RateLimiter

class TestExecuter(unittest.TestCase):

    def test_norate(self):
        call_count = 0
        async def work_fn(*_):
            nonlocal call_count
            call_count += 1

        exec = AsyncHTTPExecuter(work_fn, max_concurrency=1)
        exec.run(10)
        self.assertEqual(call_count, 10)

    def test_rate(self):
        call_count = 0
        async def work_fn(*_):
            nonlocal call_count
            call_count += 1

        exec = AsyncHTTPExecuter(work_fn, max_concurrency=1, rate_limiter=RateLimiter(2, 1.0))
        start_time = time.time()
        exec.run(10)
        duration = time.time() - start_time
        self.assertEqual(call_count, 10)
        # use 4.0 seconds since first 1 second has no rate limit
        self.assertAlmostEqual(duration, 4.0, delta=0.05)

    def test_rate_high_concurrency(self):
        call_count = 0
        async def work_fn(*_):
            nonlocal call_count
            call_count += 1

        exec = AsyncHTTPExecuter(work_fn, max_concurrency=10, rate_limiter=RateLimiter(2, 1.0))
        start_time = time.time()
        exec.run(10)
        duration = time.time() - start_time
        self.assertEqual(call_count, 10)
        # use 4.0 seconds since first 1 second has no rate limit
        self.assertAlmostEqual(duration, 4.0, delta=0.05)

    def test_rate_concurrency_lag(self):
        call_count = 0
        async def work_fn(*_):
            nonlocal call_count
            time.sleep(1)
            call_count += 1

        exec = AsyncHTTPExecuter(work_fn, max_concurrency=1, rate_limiter=RateLimiter(2, 1.0))
        start_time = time.time()
        exec.run(5)
        duration = time.time() - start_time
        self.assertEqual(call_count, 5)
        self.assertAlmostEqual(duration, 5.0, delta=0.1)

if __name__ == '__main__':
    unittest.main()
