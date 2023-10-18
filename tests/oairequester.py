# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import unittest
import time
import httpretty
from benchmark.oairequester import OAIRequester, UTILIZATION_HEADER, RETRY_AFTER_MS_HEADER

TEST_URL = "https://testresource.openai.azure.com/openai/deployments/depl/chat/completion?api-version=2023-05-15"

class TokenIterator:
    def __init__(self, delay: float):
        self.done = False
        self.delay = delay
        self.token_lines = b'data: {}\r\nend: {}\r\n'

    def __iter__(self):
        return self
    
    def __next__(self):        
        if self.done:
            raise StopIteration
        time.sleep(self.delay)
        self.done = True
        return self.token_lines

class TestRequester(unittest.TestCase):
    @httpretty.activate(allow_net_connect=False)
    def test_norate(self):
        httpretty.register_uri(httpretty.POST, TEST_URL,
            body=(l for l in TokenIterator(0.1)), streaming=True,
            adding_headers={UTILIZATION_HEADER: "11.2%"})
        
        requester = OAIRequester("", TEST_URL)
        stats = requester.call({})
        self.assertEqual(stats.calls, 1)
        self.assertIsNone(stats.last_exception)
        self.assertEqual(stats.generated_tokens, 1)
        self.assertEqual(stats.response_status_code, 200)
        self.assertAlmostEqual(stats.response_end_time-stats.request_start_time, 0.1, delta=0.02)
        self.assertAlmostEqual(stats.first_token_time-stats.request_start_time, 0.1, delta=0.02)
        self.assertEqual(stats.deployment_utilization, 11.2)

class TestRequesterTerminal(unittest.TestCase):
    @httpretty.activate(allow_net_connect=False)
    def test_norate(self):
        httpretty.register_uri(httpretty.POST, TEST_URL,
                               status=500)
        
        requester = OAIRequester("", TEST_URL)
        stats = requester.call({})
        self.assertEqual(stats.calls, 1)
        self.assertEqual(stats.response_status_code, 500)
        self.assertIsNotNone(stats.last_exception)

class TestRequesterRetryExponential(unittest.TestCase):
    @httpretty.activate(allow_net_connect=False)
    def test_norate(self):
        httpretty.register_uri(httpretty.POST, TEST_URL,
                               status=429)
        
        requester = OAIRequester("", TEST_URL)
        stats = requester.call({})
        self.assertGreaterEqual(stats.calls, 4)
        self.assertEqual(stats.response_status_code, 429)
        self.assertIsNotNone(stats.last_exception)

class TestRequesterRetryAfter(unittest.TestCase):
    @httpretty.activate(allow_net_connect=False)
    def test_norate(self):
        httpretty.register_uri(httpretty.POST, TEST_URL,
                               adding_headers={RETRY_AFTER_MS_HEADER: 100},
                               status=429)
        
        requester = OAIRequester("", TEST_URL)
        stats = requester.call({})
        self.assertGreaterEqual(stats.calls, 40)
        self.assertEqual(stats.response_status_code, 429)
        self.assertIsNotNone(stats.last_exception)
        self.assertAlmostEqual(time.time()-stats.request_start_time, 5.0, delta=0.1)
