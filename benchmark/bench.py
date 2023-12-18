# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import argparse
import logging
import os
from datetime import datetime

from .loadcmd import load
from .tokenizecmd import tokenize


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
    load_parser.add_argument("-s", "--shape-profile", type=str, default="balanced", help="Shape profile of requests.", choices=["balanced", "context", "generation", "custom"])
    load_parser.add_argument("-p", "--context-tokens", type=int, help="Number of context tokens to use when --shape-profile=custom.")
    load_parser.add_argument("-m", "--max-tokens", type=int, help="Number of requested max_tokens when --shape-profile=custom. Defaults to unset.")
    load_parser.add_argument("-i", "--completions", type=int, default=1, help="Number of completion for each request.")
    load_parser.add_argument("--frequency-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--presence-penalty", type=float, help="Request frequency_penalty.")
    load_parser.add_argument("--temperature", type=float, help="Request temperature.")
    load_parser.add_argument("--top-p", type=float, help="Request top_p.")
    load_parser.add_argument("-f", "--output-format", type=str, default="human", help="Output format.", choices=["jsonl", "human"])
    load_parser.add_argument("--log-save-dir", type=str, help="If provided, will save stddout to this directory. Filename will include important run parameters.")
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

    if args.log_save_dir is not None:
        now = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        shape_str = f"context={args.context_tokens}_max_tokens={args.max_tokens}" if args.shape_profile == "custom" else args.shape_profile
        rate_str = str(int(args.rate)) if (args.rate is not None) else 'none'
        output_path = os.path.join(args.log_save_dir, f"{now}_{args.deployment}_shape-{shape_str}_clients={int(args.clients)}_rate={rate_str}.log")
        os.makedirs(args.log_save_dir, exist_ok=True)
        try:
            os.remove(output_path)
        except FileNotFoundError:
            pass
        fh = logging.FileHandler(output_path)
        logger = logging.getLogger()
        logger.addHandler(fh)

    if "func" in args:
        args.func(args)
    else:
        parser.parse_args("--help")

main()
