# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import logging
import sys
import json

from .oaitokenizer import num_tokens_from_text, num_tokens_from_messages

def tokenize(args):
    """
    Count number of tokens for given input and model. It attempts to decode
    input as json chat messages. Otherwise, it assumes input is just text.
    Return: number of tokens.
    """
    model = args.model
    text = args.text

    if text is None:
        logging.info("no input text given, reading starding in")
        text = sys.stdin.read()

    count = 0
    try:
        data = json.loads(text)
        count = num_tokens_from_messages(data, model)

    except json.JSONDecodeError:
        logging.info("input does not seem to be json formatted, assuming text")
        count = num_tokens_from_text(text, model)

    print(f"tokens: {count}")
