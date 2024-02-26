# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import asyncio
import logging
import time
from typing import Optional

import aiohttp
import backoff

# TODO: switch to using OpenAI client library once new headers are exposed.

REQUEST_ID_HEADER = "apim-request-id"
UTILIZATION_HEADER = "azure-openai-deployment-utilization"
RETRY_AFTER_MS_HEADER = "retry-after-ms"
RETRY_AFTER_S_HEADER = "retry-after"  
MAX_RETRY_SECONDS = 60.0

TELEMETRY_USER_AGENT_HEADER = "x-ms-useragent"
USER_AGENT = "aoai-benchmark"

class RequestStats:
    """
    Statistics collected for a particular AOAI request.
    """
    def __init__(self):
        self.request_start_time: Optional[float] = None
        self.response_status_code: int = 0
        self.response_time: Optional[float] = None
        self.first_token_time: Optional[float] = None
        self.response_end_time: Optional[float] = None
        self.context_tokens: int = 0
        self.generated_tokens: Optional[int] = None
        self.deployment_utilization: Optional[float] = None
        self.calls: int = 0
        self.last_exception: Optional[Exception] = None

def _terminal_http_code(e) -> bool:
    # we only retry on 429
    return e.response.status != 429

class OAIRequester:
    """
    A simple AOAI requester that makes a streaming call and collect corresponding
    statistics.
    :param api_key: Azure OpenAI resource endpoint key.
    :param url: Full deployment URL in the form of https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completins?api-version=<api_version>
    :param backoff: Whether to retry throttled or unsuccessful requests.
    """
    def __init__(self, api_key: str, url: str, backoff=False):
        self.api_key = api_key
        self.url = url
        self.backoff = backoff

    async def call(self, session:aiohttp.ClientSession, body: dict) -> RequestStats:
        """
        Makes a single call with body and returns statistics. The function
        forces the request in streaming mode to be able to collect token
        generation latency.
        In case of failure, if the status code is 429 due to throttling, value
        of header retry-after-ms will be honored. Otherwise, request
        will be retried with an exponential backoff.
        Any other non-200 status code will fail immediately.

        :param body: json request body.
        :return RequestStats.
        """
        stats = RequestStats()
        # operate only in streaming mode so we can collect token stats.
        body["stream"] = True
        try:
            await self._call(session, body, stats)
        except Exception as e:
            stats.last_exception = e

        return stats

    @backoff.on_exception(backoff.expo,
                      aiohttp.ClientError,
                      jitter=backoff.full_jitter,
                      max_time=MAX_RETRY_SECONDS,
                      giveup=_terminal_http_code)
    async def _call(self, session:aiohttp.ClientSession, body: dict, stats: RequestStats):
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
            TELEMETRY_USER_AGENT_HEADER: USER_AGENT,
        }
        stats.request_start_time = time.time()
        while stats.calls == 0 or time.time() - stats.request_start_time < MAX_RETRY_SECONDS:
            stats.calls += 1
            response = await session.post(self.url, headers=headers, json=body)
            stats.response_status_code = response.status
            # capture utilization in all cases, if found
            self._read_utilization_header(response, stats)

            if response.status == 429:
                retry_after_ms = self._read_retry_after_headers(response)
                
                if retry_after_ms is None:
                    break
                
                if self.backoff: 
                    logging.debug(f"retry-after sleeping for {retry_after_ms}ms")  
                    await asyncio.sleep(retry_after_ms/1000.0)
            else:
                break

        if response.status != 200 and response.status != 429:
            logging.warning(f"call failed: {REQUEST_ID_HEADER}={response.headers[REQUEST_ID_HEADER]} {response.status}: {response.reason}")
        if self.backoff:
            response.raise_for_status()
        if response.status == 200:
            await self._handle_response(response, stats)
        
    async def _handle_response(self, response: aiohttp.ClientResponse, stats: RequestStats):
        async with response:
            stats.response_time = time.time()
            async for line in response.content:
                if not line.startswith(b'data:'):
                    continue
                if stats.first_token_time is None:
                    stats.first_token_time = time.time()
                if stats.generated_tokens is None:
                    stats.generated_tokens = 0
                stats.generated_tokens += 1
            stats.response_end_time = time.time()

    def _read_utilization_header(self, response: aiohttp.ClientResponse, stats: RequestStats):
        if UTILIZATION_HEADER in response.headers:
            util_str = response.headers[UTILIZATION_HEADER]
            if len(util_str) == 0:
                logging.warning(f"got empty utilization header {UTILIZATION_HEADER}")
            elif util_str[-1] != '%':
                logging.warning(f"invalid utilization header value: {UTILIZATION_HEADER}={util_str}")
            else:
                try:
                    stats.deployment_utilization = float(util_str[:-1])
                except ValueError as e:
                    logging.warning(f"unable to parse utilization header value: {UTILIZATION_HEADER}={util_str}: {e}")            
    
    def _read_retry_after_headers(self, response: aiohttp.ClientResponse):
        retry_after_ms = None
        if RETRY_AFTER_MS_HEADER in response.headers:
            try:
                retry_after_str = response.headers[RETRY_AFTER_MS_HEADER]
                retry_after_ms = float(retry_after_str)
            except ValueError as e:
                logging.warning(f"unable to parse {RETRY_AFTER_MS_HEADER} header value: {RETRY_AFTER_MS_HEADER}={retry_after_str}: {e}")   
        
        elif RETRY_AFTER_S_HEADER in response.headers:  
            try:  
                retry_after_str = response.headers[RETRY_AFTER_S_HEADER]
                retry_after_s = float(retry_after_str)  
                retry_after_ms = retry_after_s * 1000  
            except ValueError as e:  
                logging.warning(f"unable to parse {RETRY_AFTER_S_HEADER} header value: {RETRY_AFTER_S_HEADER}={retry_after_str}: {e}")  
        
        return retry_after_ms   

