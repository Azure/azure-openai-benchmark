# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import asyncio
import collections
import time
import math

# allow up to 5% burst of max calls
RATE_ESTIMATOR_BURST_FACTOR = 1.0

class RateLimiter:
    """
    Simple rate limiter.
    """
    def __init__(self, calls: int, period: float):
        """
        Create a new RateLimiter with restricted calls per period. The implementation
        uses simple linear rate estimator.
        """
        self.calls = collections.deque()
        self.period = period
        self.max_calls = calls

    async def __aenter__(self):
        sleep_time = 0
        if len(self.calls) >= self.max_calls:
            sleep_time = self.period - self._timespan()
        elif len(self.calls) > 1:
            sleep_time = (self.period - self._timespan()) / (math.ceil(self.max_calls * RATE_ESTIMATOR_BURST_FACTOR) - len(self.calls))

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        return self

    async def __aexit__(self, *args):
        self.calls.append(time.time())
        while self._timespan() >= self.period:
            self.calls.popleft()

    def _timespan(self):
        return self.calls[-1] - self.calls[0]


class NoRateLimiter:
    """
    Dummy rate limiter that does not impose any limits.
    """
    async def __aenter__(self):
        pass
    async def __aexit__(self, *args):
        pass
