# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import argparse
import logging

from .loadcmd import load
from .tokenizecmd import tokenize


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')
    
def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    parser = argparse.ArgumentParser(description="Benchmarking tool for Azure OpenAI Provisioned Throughput Units (PTUs).")
    sub_parsers = parser.add_subparsers()

    load_parser = sub_parsers.add_parser("load", help="Run load generation tool.")
    load_parser.add_argument("-a", "--api-version", type=str, default="2023-05-15", help="Set OpenAI API version.")
    load_parser.add_argument("-k", "--api-key-env", type=str, default="OPENAI_API_KEY", help="Environment variable that contains the API KEY.")
    load_parser.add_argument("-c", "--clients", type=int, default=20, help="Set number of parallel clients to use for load generation.")
    load_parser.add_argument("-n", "--requests", type=int, help="Number of requests for the load run. Default to 'until killed'.")
    load_parser.add_argument("-d", "--duration", type=int, help="Duration of load in seconds. Defaults to 'until killed'.")
    load_parser.add_argument("-r", "--rate", type=float, help="Rate of request generation in Requests Per Minute (RPM). Default to as fast as possible.")
    load_parser.add_argument("-w", "--aggregation-window", type=float, default=60, help="Statistics aggregation sliding window duration in seconds. See README.md for more details.")
    load_parser.add_argument("--context-generation-method", type=str, default="generate", help="Source of context messages to be used during testing.", choices=["generate", "replay"])
    load_parser.add_argument("--replay-path", type=str, help="Path to JSON file containing messages for replay when using --context-message-source=replay.")
    load_parser.add_argument("-s", "--shape-profile", type=str, default="balanced", help="Shape profile of requests.", choices=["balanced", "context", "generation", "custom"])
    load_parser.add_argument("-p", "--context-tokens", type=int, help="Number of context tokens to use when --shape-profile=custom.")
    load_parser.add_argument("-m", "--max-tokens", type=int, help="Number of requested max_tokens when --shape-profile=custom. Defaults to unset.")
    load_parser.add_argument("--prevent-server-caching", type=str2bool, nargs='?', help="Adds a random prefixes to all requests in order to prevent server-side caching. Defaults to True.", const=True, default=True)
    load_parser.add_argument("-i", "--completions", type=int, default=1, help="Number of completion for each request.")
    load_parser.add_argument("--frequency-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--presence-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--temperature", type=float, help="Request temperature.")
    load_parser.add_argument("--top-p", type=float, help="Request top_p.")
    load_parser.add_argument("-f", "--output-format", type=str, default="human", help="Output format.", choices=["jsonl", "human"])
    load_parser.add_argument("-t", "--retry", type=str, default="none", help="Request retry strategy.", choices=["none", "exponential"])
    load_parser.add_argument("-e", "--deployment", type=str, help="Azure OpenAI deployment name.", required=True)
    load_parser.add_argument("api_base_endpoint", help="Azure OpenAI deployment base endpoint.", nargs=1)
    load_parser.set_defaults(func=load)

    tokenizer_parser = sub_parsers.add_parser("tokenize", help="Text tokenization tool.")
    tokenizer_parser.add_argument(
        "-m", "--model", type=str, help="Model to assume for tokenization.", 
        choices=[
            "gpt-4", "gpt-4-0314", "gpt-4-32k-0314", "gpt-4-0613", "gpt-4-32k-0613", 
            "gpt-3.5-turbo", "gpt-3.5-turbo-0613", "gpt-3.5-turbo-16k-0613"], 
        required=True)
    tokenizer_parser.add_argument("text", help="Input text or chat messages json to tokenize. Default to stdin.", nargs="?")
    tokenizer_parser.set_defaults(func=tokenize)

    args = parser.parse_args()
    if "func" in args:
        args.func(args)
    else:
        parser.parse_args("--help")

main()
