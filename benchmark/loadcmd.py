# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import threading
import time
import os
import json
import aiohttp
import numpy as np
import wonderwords
import math
import logging
from typing import Iterable, Iterator
from .asynchttpexecuter import AsyncHTTPExecuter
from .oairequester import OAIRequester, RequestStats
from .ratelimiting import RateLimiter, NoRateLimiter
from .oaitokenizer import num_tokens_from_messages

import sys

class _Samples:
   def __init__(self):
      # [0] timestamp, [1] value
      self.samples:[(float, float)] = []

   def _trim_oldest(self, duration:float):
      while len(self.samples) > 0 and (time.time() - self.samples[0][0]) > duration:
         self.samples.pop(0)

   def _append(self, timestamp:float, value:float):
      self.samples.append((timestamp, value))

   def _values(self) -> [float]:
      values = []
      for entry in self.samples:
         values.append(entry[1])
      return values
   
   def _len(self) -> int:
      return len(self.samples)

class _StatsAggregator(threading.Thread):
   """
   A thread-safe request stats aggregator that can periodically emit statistics.
   """
   lock = threading.Lock()
   terminate: threading.Event

   start_time: float = 0
   total_requests_count: int = 0
   total_failed_count: int = 0
   requests_count: int = 0
   failed_count: int = 0
   throttled_count: int = 0

   request_timestamps = _Samples()
   request_latency = _Samples()
   call_tries = _Samples()
   response_latencies = _Samples()
   first_token_latencies = _Samples()
   token_latencies = _Samples()
   context_tokens = _Samples()
   generated_tokens = _Samples()
   utilizations = _Samples()

   def __init__(self, dump_duration:float=5, window_duration:float=60, json_output=False, *args,**kwargs):
      """
      :param dump_duration: duration in seconds to dump current aggregates.
      :param window_duration: duration of sliding window in second to consider for aggregation.
      :param json_output: whether to dump periodic stats as json or human readable.
      """
      self.dump_duration = dump_duration
      self.json_output = json_output
      self.window_duration = window_duration

      super(_StatsAggregator, self).__init__(*args, **kwargs)

   def run(self):
      """
      Start the periodic aggregator. Use stop() to stop.
      """
      self.start_time = time.time()
      self.terminate = threading.Event()
      while not self.terminate.wait(self.dump_duration):
         self._dump()
         self._slide_window()

   def stop(self):
      self.terminate.set()

   def aggregate_request(self, stats: RequestStats):
      """
      Aggregates request stat within the sliding window.
      :param stats: request stats object.
      """
      with self.lock:
         self.requests_count += 1
         self.total_requests_count += 1
         self.call_tries._append(stats.request_start_time, stats.calls)
         if stats.response_status_code != 200:
            self.failed_count += 1
            self.total_failed_count += 1
            if stats.response_status_code == 429:
               self.throttled_count += 1
         else:
            self.request_latency._append(stats.request_start_time, stats.response_end_time - stats.request_start_time)
            self.request_timestamps._append(stats.request_start_time, stats.request_start_time)
            self.response_latencies._append(stats.request_start_time, stats.response_time - stats.request_start_time)
            self.first_token_latencies._append(stats.request_start_time, stats.first_token_time - stats.request_start_time)
            self.token_latencies._append(stats.request_start_time, (stats.response_end_time - stats.first_token_time) / stats.generated_tokens)
            self.context_tokens._append(stats.request_start_time, stats.context_tokens)
            self.generated_tokens._append(stats.request_start_time, stats.generated_tokens)
         if stats.deployment_utilization is not None:
            self.utilizations._append(stats.request_start_time, stats.deployment_utilization)

   def _dump(self):
      with self.lock:
         run_seconds = round(time.time() - self.start_time)
         e2e_latency_avg = round(np.average(self.request_latency._values()), 3) if self.request_latency._len() > 0 else "n/a"
         e2e_latency_95th = round(np.percentile(self.request_latency._values(), 95), 3) if self.request_latency._len() > 1 else "n/a"
         context_per_minute = round(60.0 * np.sum(self.context_tokens._values()) / self.window_duration, 0)  if self.context_tokens._len() > 0 else "n/a"
         gen_per_minute = round(60.0 * np.sum(self.generated_tokens._values()) / self.window_duration, 0)  if self.generated_tokens._len() > 0 else "n/a"
         ttft_avg = round(np.average(self.first_token_latencies._values()), 3) if self.first_token_latencies._len() > 0 else "n/a"
         ttft_95th = round(np.percentile(self.first_token_latencies._values(), 95), 3) if self.first_token_latencies._len() > 1 else "n/a"
         tbt_avg = round(np.average(self.token_latencies._values()), 3) if self.token_latencies._len() > 0 else "n/a"
         tbt_95th = round(np.percentile(self.token_latencies._values(), 95), 3) if self.token_latencies._len() > 1 else "n/a"
         util_avg = f"{round(np.average(self.utilizations._values()), 1)}%" if self.utilizations._len() > 0 else "n/a"
         util_95th = f"{round(np.percentile(self.utilizations._values(), 95), 1)}%" if self.utilizations._len() > 1 else "n/a"
         rpm = round(60.0 * self.request_timestamps._len() / self.window_duration, 1)  if self.request_timestamps._len() > 0 else "n/a"
         if self.json_output:
            j = {
               "run_seconds": run_seconds,
               "rpm": rpm,
               "requests": self.requests_count,
               "failures": self.failed_count,
               "throttled": self.throttled_count,
               "tpm": {
                  "context": context_per_minute,
                  "gen": gen_per_minute,
               },
               "e2e": {
                  "avg": e2e_latency_avg,
                  "95th": e2e_latency_95th,
               },
               "ttft": {
                  "avg": ttft_avg,
                  "95th": ttft_95th,
               },
               "tbt": {
                  "avg": tbt_avg,
                  "95th": tbt_95th,
               },
               "util": {
                  "avg": util_avg,
                  "95th": util_95th,
               },
            }
            print(json.dumps(j), flush=True)
         else:
            print(f"time: {run_seconds:<4} rpm: {rpm:<5} requests: {self.requests_count:<5} failures: {self.failed_count:<4} throttled: {self.throttled_count:<4} ctx_tpm: {context_per_minute:<6} gen_tpm: {gen_per_minute:<6} ttft_avg: {ttft_avg:<6} ttft_95th: {ttft_95th:<6} tbt_avg: {tbt_avg:<6} tbt_95th: {tbt_95th:<6} e2e_avg: {e2e_latency_avg:<6} e2e_95th: {e2e_latency_95th:<6} util_avg: {util_avg:<6} util_95th: {util_95th:<6}", flush=True)

   def _slide_window(self):
      with self.lock:
         self.call_tries._trim_oldest(self.window_duration)
         self.request_timestamps._trim_oldest(self.window_duration)
         self.response_latencies._trim_oldest(self.window_duration)
         self.first_token_latencies._trim_oldest(self.window_duration)
         self.token_latencies._trim_oldest(self.window_duration)
         self.generated_tokens._trim_oldest(self.window_duration)
         self.utilizations._trim_oldest(self.window_duration)

class _RequestBuilder:
   """
   Wrapper iterator class to build request payloads.
   """
   def __init__(self, model:str, context_tokens:int,
                max_tokens:None, 
                completions:None, 
                frequence_penalty:None, 
                presence_penalty:None, 
                temperature:None, 
                top_p:None):
      self.model = model
      self.context_tokens = context_tokens
      self.max_tokens = max_tokens
      self.completions = completions
      self.frequency_penalty = frequence_penalty
      self.presence_penalty = presence_penalty
      self.temperature = temperature
      self.top_p = top_p

      logging.info("warming up prompt cache")
      _generate_messages(self.model, self.context_tokens, self.max_tokens)

   def __iter__(self) -> Iterator[dict]:
      return self

   def __next__(self) -> (dict, int):
      messages, messages_tokens = _generate_messages(self.model, self.context_tokens, self.max_tokens)
      body = {"messages":messages}
      if self.max_tokens is not None:
         body["max_tokens"] = self.max_tokens
      if self.completions is not None:
         body["n"] = self.completions
      if self.frequency_penalty is not None:
         body["frequency_penalty"] = self.frequency_penalty
      if self.presence_penalty is not None:
         body["presenece_penalty"] = self.presence_penalty
      if self.temperature is not None:
         body["temperature"] = self.temperature
      if self.top_p is not None:
         body["top_p"] = self.top_p
      return body, messages_tokens

def load(args):
   try:
        _validate(args)
   except ValueError as e:
       print(f"invalid argument(s): {e}")
       sys.exit(1)

   api_key = os.getenv(args.api_key_env)
   url = args.api_base_endpoint[0] + "/openai/deployments/" + args.deployment + "/chat/completions"
   url += "?api-version=" + args.api_version

   rate_limiter = NoRateLimiter()
   if args.rate is not None and args.rate > 0:
      rate_limiter = RateLimiter(args.rate, 60)

   max_tokens = args.max_tokens
   context_tokens = args.context_tokens
   if args.shape_profile == "balanced":
      context_tokens = 500
      max_tokens = 500
   elif args.shape_profile == "context":
      context_tokens = 2000
      max_tokens = 200
   elif args.shape_profile == "generation":
      context_tokens = 500
      max_tokens = 1000

   logging.info(f"using shape profile {args.shape_profile}: context tokens: {context_tokens}, max tokens: {max_tokens}")

   request_builder = _RequestBuilder("gpt-4-0613", context_tokens,
      max_tokens=max_tokens,
      completions=args.completions,
      frequence_penalty=args.frequency_penalty,
      presence_penalty=args.presence_penalty,
      temperature=args.temperature,
      top_p=args.top_p)

   logging.info("starting load...")

   _run_load(request_builder,
      max_concurrency=args.clients, 
      api_key=api_key,
      url=url,
      rate_limiter=rate_limiter,
      backoff=args.retry=="exponential",
      request_count=args.requests,
      duration=args.duration,
      aggregation_duration=args.aggregation_window,
      json_output=args.output_format=="jsonl")

def _run_load(request_builder: Iterable[dict],
              max_concurrency: int, 
              api_key: str,
              url: str,
              rate_limiter=None, 
              backoff=False,
              duration=None, 
              aggregation_duration=60,
              request_count=None,
              json_output=False):
   aggregator = _StatsAggregator(
      window_duration=aggregation_duration,
      dump_duration=1, 
      json_output=json_output)
   requester = OAIRequester(api_key, url, backoff=backoff)

   async def request_func(session:aiohttp.ClientSession):
      nonlocal aggregator
      nonlocal requester
      request_body, messages_tokens = request_builder.__next__()
      stats = await requester.call(session, request_body)
      stats.context_tokens = messages_tokens
      try:
         aggregator.aggregate_request(stats)
      except Exception as e:
         print(e)

   executer = AsyncHTTPExecuter(
      request_func, 
      rate_limiter=rate_limiter, 
      max_concurrency=max_concurrency)

   aggregator.start()
   executer.run(
      call_count=request_count, 
      duration=duration)
   aggregator.stop()

   logging.info("finished load test")

CACHED_PROMPT=""
CACHED_MESSAGES_TOKENS=0
def _generate_messages(model:str, tokens:int, max_tokens:int=None) -> ([dict], int):
   """
   Generate `messages` array based on tokens and max_tokens.
   Returns Tuple of messages array and actual context token count.
   """
   global CACHED_PROMPT
   global CACHED_MESSAGES_TOKENS
   try:
      r = wonderwords.RandomWord()
      messages = [{"role":"user", "content":str(time.time()) + " "}]
      if max_tokens is not None:
         messages.append({"role":"user", "content":str(time.time()) + f" write an essay in at least {max_tokens*3} words"})
      messages_tokens = 0

      if len(CACHED_PROMPT) > 0:
         messages[0]["content"] += CACHED_PROMPT
         messages_tokens = CACHED_MESSAGES_TOKENS
      else:
         prompt = ""
         base_prompt = messages[0]["content"]
         while True:
            messages_tokens = num_tokens_from_messages(messages, model)
            remaining_tokens = tokens - messages_tokens
            if remaining_tokens <= 0:
               break
            prompt += " ".join(r.random_words(amount=math.ceil(remaining_tokens/4))) + " "
            messages[0]["content"] = base_prompt + prompt

         CACHED_PROMPT = prompt
         CACHED_MESSAGES_TOKENS = messages_tokens

   except Exception as e:
      print (e)

   return (messages, messages_tokens)

def _validate(args):
    if len(args.api_version) == 0:
      raise ValueError("api-version is required")
    if len(args.api_key_env) == 0:
       raise ValueError("api-key-env is required")
    if os.getenv(args.api_key_env) is None:
       raise ValueError(f"api-key-env {args.api_key_env} not set")
    if args.clients < 1:
       raise ValueError("clients must be > 0")
    if args.requests is not None and args.requests < 0:
       raise ValueError("requests must be > 0")
    if args.duration is not None and args.duration != 0 and args.duration < 30:
       raise ValueError("duration must be > 30")
    if args.rate is not None and  args.rate < 0:
       raise ValueError("rate must be > 0")
    if args.shape_profile == "custom":
       if args.context_tokens < 1:
          raise ValueError("context-tokens must be specified with shape=custom")
    if args.max_tokens is not None and args.max_tokens < 0:
       raise ValueError("max-tokens must be > 0")
    if args.completions < 1:
       raise ValueError("completions must be > 0")
    if args.frequency_penalty is not None and (args.frequency_penalty < -2 or args.frequency_penalty > 2):
       raise ValueError("frequency-penalty must be between -2.0 and 2.0")
    if args.presence_penalty is not None and (args.presence_penalty < -2 or args.presence_penalty > 2):
       raise ValueError("presence-penalty must be between -2.0 and 2.0")
    if args.temperature is not None and (args.temperature < 0 or args.temperature > 2):
       raise ValueError("temperature must be between 0 and 2.0")
    