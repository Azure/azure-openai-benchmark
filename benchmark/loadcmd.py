# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import logging
import math
import os
import sys
import time
from typing import Iterable, Iterator

import aiohttp
import wonderwords

from .asynchttpexecuter import AsyncHTTPExecuter
from .oairequester import OAIRequester
from .oaitokenizer import num_tokens_from_messages
from .ratelimiting import NoRateLimiter, RateLimiter
from .statsaggregator import _StatsAggregator


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
                top_p:None,
                custom_prompt_file:None):
      self.model = model
      self.context_tokens = context_tokens
      self.max_tokens = max_tokens
      self.completions = completions
      self.frequency_penalty = frequence_penalty
      self.presence_penalty = presence_penalty
      self.temperature = temperature
      self.top_p = top_p
      self.custom_prompt_file = custom_prompt_file

      logging.info("warming up prompt cache")
      _generate_messages(self.model, self.context_tokens, self.max_tokens, self.custom_prompt_file)

   def __iter__(self) -> Iterator[dict]:
      return self

   def __next__(self) -> (dict, int):
      messages, messages_tokens = _generate_messages(self.model, self.context_tokens, self.max_tokens, self.custom_prompt_file)
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

   if args.custom_prompt_file=="none" :
     logging.info("No custom_prompt_file input, using random generated input prompt") 
   else:
     if not os.path.exists(args.custom_prompt_file):
        raise FileNotFoundError(f"The file '{args.custom_prompt_file}' does not exist.")
     logging.info(f"Custom_prompt_file input:{args.custom_prompt_file}") 

   request_builder = _RequestBuilder("gpt-4-0613", context_tokens,
      max_tokens=max_tokens,
      completions=args.completions,
      frequence_penalty=args.frequency_penalty,
      presence_penalty=args.presence_penalty,
      temperature=args.temperature,
      top_p=args.top_p,
      custom_prompt_file=args.custom_prompt_file
      )

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
      clients=max_concurrency,
      json_output=json_output)
   requester = OAIRequester(api_key, url, backoff=backoff)

   async def request_func(session:aiohttp.ClientSession):
      nonlocal aggregator
      nonlocal requester
      request_body, messages_tokens = request_builder.__next__()
      aggregator.record_new_request()
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

def read_input_messages(file_name: str):
    """
    Read messages from a file, each line is considered a separate message.
    Returns a list of messages.
    """
    try:
      with open(file_name, 'r', encoding='utf-8') as file:
        return file.readlines()
    except Exception as e:
        raise IOError(f"An error occurred while reading the file: {e}") 

CACHED_PROMPT=""
CACHED_MESSAGES_TOKENS=0
def _generate_random_messages(model:str, tokens:int, max_tokens:int=None) -> ([dict], int):
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
         messages.append({"role":"user", "content":str(time.time()) + f" write a long essay about life in at least {max_tokens} tokens"})
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

input_messages_cache = None

def _generate_messages(model: str, tokens: int, max_tokens: int = None, custom_prompt_file: str = None) -> ([dict], int):
    """
    Returns Tuple of messages array and actual context token count.
    """
    if custom_prompt_file=="none" :
      return _generate_random_messages(model, tokens, max_tokens)

    global input_messages_cache
    try:
        messages = []

        if input_messages_cache is None:
            input_messages_cache = read_input_messages(custom_prompt_file)

        for line_number, input_message in enumerate(input_messages_cache, start=1):
            message = f"question number: {line_number}: {input_message}"
            messages.append({"role": "user", "content": str(time.time()) + message})

        messages_tokens = num_tokens_from_messages(messages, model)
    except Exception as e:
        print(e)
        messages = []
        messages_tokens = 0

    return messages, messages_tokens
 
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
    if args.custom_prompt_file is None:
       raise ValueError("need to set the input prompt content file")
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
    